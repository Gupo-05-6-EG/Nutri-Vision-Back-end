"""Operacoes de privacidade e direitos do titular."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.alimento_personalizado import AlimentoPersonalizado
from app.models.auditoria import Auditoria
from app.models.conquista import ConquistaPaciente
from app.models.consentimento import Consentimento
from app.models.desafio import Desafio, ParticipanteDesafio
from app.models.lembrete_refeicao import DispositivoPush, LembreteRefeicao
from app.models.paciente import Paciente
from app.models.plano_alimentar import PlanoAlimentar
from app.models.refeicao import Refeicao
from app.models.usuario import Perfil, Usuario
from app.models.vinculo import Vinculo


def listar_consentimentos(db: Session, usuario_id: int) -> list[Consentimento]:
    return list(
        db.scalars(
            select(Consentimento)
            .where(Consentimento.usuario_id == usuario_id)
            .order_by(Consentimento.aceito_em, Consentimento.id)
        )
    )


def registrar_consentimento(db: Session, usuario_id: int, versao_termo: str) -> Consentimento:
    consentimento = db.scalar(
        select(Consentimento)
        .where(
            Consentimento.usuario_id == usuario_id,
            Consentimento.revogado_em.is_(None),
            Consentimento.versao_termo == versao_termo,
        )
        .order_by(Consentimento.id.desc())
    )
    if consentimento is not None:
        return consentimento

    agora = datetime.now(UTC)
    anteriores_ativos = db.scalars(
        select(Consentimento).where(
            Consentimento.usuario_id == usuario_id,
            Consentimento.revogado_em.is_(None),
        )
    )
    for anterior in anteriores_ativos:
        anterior.revogado_em = agora

    consentimento = Consentimento(usuario_id=usuario_id, versao_termo=versao_termo)
    db.add(consentimento)
    db.commit()
    db.refresh(consentimento)
    return consentimento


def revogar_consentimento(db: Session, usuario_id: int) -> Consentimento | None:
    ativos = list(
        db.scalars(
            select(Consentimento)
            .where(Consentimento.usuario_id == usuario_id, Consentimento.revogado_em.is_(None))
            .order_by(Consentimento.id.desc())
        )
    )
    if not ativos:
        return None
    agora = datetime.now(UTC)
    for item in ativos:
        item.revogado_em = agora
    db.commit()
    consentimento = ativos[0]
    db.refresh(consentimento)
    return consentimento


def exportar_dados(db: Session, usuario: Usuario) -> dict[str, object]:
    consentimentos = listar_consentimentos(db, usuario.id)
    dados: dict[str, object] = {
        "usuario": {
            "id": usuario.id,
            "nome": usuario.nome,
            "email": usuario.email,
            "perfil": usuario.perfil,
            "criado_em": usuario.criado_em,
        },
        "consentimentos": consentimentos,
    }
    if usuario.perfil == Perfil.PACIENTE:
        paciente = db.get(Paciente, usuario.id)
        dados["paciente"] = paciente
        for chave, modelo in [
            ("planos", PlanoAlimentar),
            ("lembretes", LembreteRefeicao),
            ("dispositivos", DispositivoPush),
            ("conquistas", ConquistaPaciente),
            ("participacoes_desafios", ParticipanteDesafio),
            ("auditorias", Auditoria),
        ]:
            dados[chave] = db.scalars(select(modelo).where(modelo.paciente_id == usuario.id)).all()
        dados["desafios_criados"] = db.scalars(
            select(Desafio).where(Desafio.criador_id == usuario.id)
        ).all()
        refeicoes = db.scalars(
            select(Refeicao)
            .where(Refeicao.paciente_id == usuario.id)
            .options(selectinload(Refeicao.itens))
            .order_by(Refeicao.consumida_em, Refeicao.id)
        ).all()
        dados["refeicoes"] = refeicoes
        dados["alimentos_personalizados"] = db.scalars(
            select(AlimentoPersonalizado)
            .where(AlimentoPersonalizado.paciente_id == usuario.id)
            .order_by(AlimentoPersonalizado.id)
        ).all()
        dados["vinculos"] = db.scalars(
            select(Vinculo).where(Vinculo.paciente_id == usuario.id).order_by(Vinculo.id)
        ).all()
    else:
        dados["vinculos"] = db.scalars(
            select(Vinculo).where(Vinculo.nutricionista_id == usuario.id).order_by(Vinculo.id)
        ).all()
    return dados


def excluir_conta(db: Session, usuario: Usuario) -> None:
    if usuario.perfil == Perfil.PACIENTE:
        db.query(AlimentoPersonalizado).filter(
            AlimentoPersonalizado.paciente_id == usuario.id
        ).delete(synchronize_session=False)
    db.delete(usuario)
    db.commit()
