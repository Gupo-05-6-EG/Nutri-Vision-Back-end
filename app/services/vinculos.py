"""Regras de negocio do mecanismo de vinculacao (Task 1.4)."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from secrets import randbelow

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.usuario import Perfil, Usuario
from app.models.vinculo import CodigoVinculacao, StatusCodigoVinculacao, Vinculo


class CodigoVinculacaoNaoEncontrado(Exception):
    pass


class CodigoVinculacaoExpirado(Exception):
    pass


class CodigoVinculacaoJaUtilizado(Exception):
    pass


class PerfilIncompativel(Exception):
    pass


class VinculoDuplicado(Exception):
    pass


@dataclass(slots=True)
class VinculoResgatado:
    nutricionista_id: int
    nutricionista_nome: str
    nutricionista_foto_url: str | None
    vinculado_em: datetime


def _agora() -> datetime:
    return datetime.now(UTC)


def _expiracao_padrao() -> datetime:
    minutos = get_settings().LINKING_CODE_EXPIRE_MINUTES
    return _agora() + timedelta(minutes=minutos)


def _hash_codigo(codigo: str) -> str:
    segredo = get_settings().SECRET_KEY
    return sha256(f"{segredo}:{codigo}".encode()).hexdigest()


def _em_utc(momento: datetime) -> datetime:
    if momento.tzinfo is None:
        return momento.replace(tzinfo=UTC)
    return momento.astimezone(UTC)


def _gerar_codigo() -> str:
    return f"{randbelow(1_000_000):06d}"


def gerar_codigo_vinculacao(db: Session, usuario: Usuario) -> CodigoVinculacao:
    if usuario.perfil != Perfil.NUTRICIONISTA:
        raise PerfilIncompativel

    # Cada nutricionista mantem um unico codigo ativo por vez; gerar um novo
    # invalida os codigos ativos anteriores daquele proprietario.
    codigos_ativos = (
        db.execute(
            select(CodigoVinculacao).where(
                CodigoVinculacao.nutricionista_id == usuario.id,
                CodigoVinculacao.status == StatusCodigoVinculacao.ATIVO.value,
            )
        )
        .scalars()
        .all()
    )
    for codigo_ativo in codigos_ativos:
        codigo_ativo.status = StatusCodigoVinculacao.EXPIRADO.value

    for _ in range(10):
        codigo = _gerar_codigo()
        codigo_hash = _hash_codigo(codigo)
        ja_existe = db.execute(
            select(CodigoVinculacao).where(CodigoVinculacao.codigo_hash == codigo_hash)
        ).scalar_one_or_none()
        if ja_existe is not None:
            continue

        registro = CodigoVinculacao(
            nutricionista_id=usuario.id,
            nutricionista_nome=usuario.nome,
            # `usuarios` ainda nao tem foto; a coluna ja existe para quando tiver.
            nutricionista_foto_url=None,
            codigo_hash=codigo_hash,
            status=StatusCodigoVinculacao.ATIVO.value,
            expira_em=_expiracao_padrao(),
        )
        db.add(registro)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            continue
        db.refresh(registro)
        registro.codigo_em_texto = codigo  # type: ignore[attr-defined]
        return registro

    raise RuntimeError("nao foi possivel gerar um codigo de vinculacao unico")


def _buscar_codigo_ativo(db: Session, codigo: str) -> CodigoVinculacao | None:
    codigo_hash = _hash_codigo(codigo)
    stmt = select(CodigoVinculacao).where(CodigoVinculacao.codigo_hash == codigo_hash)
    try:
        bind = db.get_bind()
        if bind.dialect.name == "postgresql":
            stmt = stmt.with_for_update()
    except Exception:
        pass
    return db.execute(stmt).scalar_one_or_none()


def resgatar_codigo_vinculacao(db: Session, usuario: Usuario, codigo: str) -> VinculoResgatado:
    if usuario.perfil != Perfil.PACIENTE:
        raise PerfilIncompativel

    registro = _buscar_codigo_ativo(db, codigo)
    if registro is None:
        raise CodigoVinculacaoNaoEncontrado

    agora = _agora()
    expira_em = _em_utc(registro.expira_em)
    if registro.status == StatusCodigoVinculacao.EXPIRADO.value or expira_em <= agora:
        registro.status = StatusCodigoVinculacao.EXPIRADO.value
        db.commit()
        raise CodigoVinculacaoExpirado

    if registro.status != StatusCodigoVinculacao.ATIVO.value:
        raise CodigoVinculacaoJaUtilizado

    if registro.nutricionista_id == usuario.id:
        raise PerfilIncompativel

    # Atualizacao condicional atomica para concorrencia multi-processo/worker
    stmt = (
        update(CodigoVinculacao)
        .where(
            CodigoVinculacao.id == registro.id,
            CodigoVinculacao.status == StatusCodigoVinculacao.ATIVO.value,
        )
        .values(
            status=StatusCodigoVinculacao.RESGATADO.value,
            paciente_id=usuario.id,
            resgatado_em=agora,
        )
    )
    res_upd = db.execute(stmt)
    if res_upd.rowcount == 0:
        db.rollback()
        raise CodigoVinculacaoJaUtilizado

    registro.status = StatusCodigoVinculacao.RESGATADO.value
    registro.paciente_id = usuario.id
    registro.resgatado_em = agora

    vinculo_existente = db.execute(
        select(Vinculo).where(
            Vinculo.nutricionista_id == registro.nutricionista_id,
            Vinculo.paciente_id == usuario.id,
        )
    ).scalar_one_or_none()

    if vinculo_existente is None:
        vinculo = Vinculo(
            nutricionista_id=registro.nutricionista_id,
            paciente_id=usuario.id,
        )
        db.add(vinculo)
        try:
            db.flush()
        except IntegrityError as exc:
            db.rollback()
            vinculo_recarregado = db.execute(
                select(Vinculo).where(
                    Vinculo.nutricionista_id == registro.nutricionista_id,
                    Vinculo.paciente_id == usuario.id,
                )
            ).scalar_one_or_none()
            if vinculo_recarregado is None:
                raise VinculoDuplicado from exc
            vinculo = vinculo_recarregado
    else:
        vinculo = vinculo_existente

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise VinculoDuplicado from exc

    vinculado_em = _em_utc(vinculo.criado_em or agora)

    return VinculoResgatado(
        nutricionista_id=registro.nutricionista_id,
        nutricionista_nome=registro.nutricionista_nome,
        nutricionista_foto_url=registro.nutricionista_foto_url,
        vinculado_em=vinculado_em,
    )
