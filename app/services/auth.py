"""Regras de negocio do cadastro e do login (RF13)."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import HASH_FICTICIO, gerar_hash_senha, verificar_senha
from app.models.paciente import Paciente
from app.models.usuario import Nutricionista, Perfil, Usuario
from app.schemas.auth import CadastroNutricionistaIn, CadastroPacienteIn


class EmailJaCadastrado(Exception):
    """Ja existe usuario com esse email."""


class CrnJaCadastrado(Exception):
    """Ja existe nutricionista com esse CRN."""


class CredenciaisInvalidas(Exception):
    """Email inexistente ou senha errada (de proposito, sem dizer qual)."""


def _email_em_uso(db: Session, email: str) -> bool:
    return db.scalar(select(Usuario.id).where(Usuario.email == email)) is not None


def _novo_usuario(db: Session, dados: CadastroPacienteIn, perfil: Perfil) -> Usuario:
    if _email_em_uso(db, dados.email):
        raise EmailJaCadastrado
    usuario = Usuario(
        nome=dados.nome,
        email=dados.email,
        senha_hash=gerar_hash_senha(dados.senha),
        perfil=perfil.value,
    )
    db.add(usuario)
    db.flush()  # gera o id, usado como PK da tabela do perfil
    return usuario


def _salvar(db: Session, usuario: Usuario) -> Usuario:
    try:
        db.commit()
    except IntegrityError:
        # Corrida entre dois cadastros com o mesmo email passando pela checagem
        # ao mesmo tempo: o unique do banco barra o segundo.
        db.rollback()
        raise EmailJaCadastrado from None
    db.refresh(usuario)
    return usuario


def cadastrar_paciente(db: Session, dados: CadastroPacienteIn) -> Usuario:
    """Cria o usuario e o paciente vazio (a triagem preenche depois)."""
    usuario = _novo_usuario(db, dados, Perfil.PACIENTE)
    db.add(Paciente(id=usuario.id))
    return _salvar(db, usuario)


def cadastrar_nutricionista(db: Session, dados: CadastroNutricionistaIn) -> Usuario:
    if db.scalar(select(Nutricionista.id).where(Nutricionista.crn == dados.crn)) is not None:
        raise CrnJaCadastrado
    usuario = _novo_usuario(db, dados, Perfil.NUTRICIONISTA)
    db.add(Nutricionista(id=usuario.id, crn=dados.crn))
    return _salvar(db, usuario)


def autenticar(db: Session, email: str, senha: str) -> Usuario:
    usuario = db.scalar(select(Usuario).where(Usuario.email == email))
    if usuario is None:
        verificar_senha(senha, HASH_FICTICIO)  # mesmo custo de um email existente
        raise CredenciaisInvalidas
    if not verificar_senha(senha, usuario.senha_hash):
        raise CredenciaisInvalidas
    return usuario


def buscar_usuario(db: Session, usuario_id: int) -> Usuario | None:
    return db.get(Usuario, usuario_id)


def crn_do_usuario(db: Session, usuario: Usuario) -> str | None:
    if usuario.perfil != Perfil.NUTRICIONISTA:
        return None
    nutricionista = db.get(Nutricionista, usuario.id)
    return nutricionista.crn if nutricionista else None
