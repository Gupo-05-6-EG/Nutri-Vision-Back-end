"""Regras de negocio do mecanismo de vinculacao (Task 1.4)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from secrets import randbelow
from threading import Lock

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import PerfilUsuario, UsuarioAutenticado
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


_LOCKS_POR_CODIGO: dict[str, Lock] = {}
_LOCKS_GUARD = Lock()


def _lock_do_codigo(codigo: str) -> Lock:
    with _LOCKS_GUARD:
        lock = _LOCKS_POR_CODIGO.get(codigo)
        if lock is None:
            lock = Lock()
            _LOCKS_POR_CODIGO[codigo] = lock
        return lock


def _expiracao_padrao() -> datetime:
    minutos = get_settings().LINKING_CODE_EXPIRE_MINUTES
    return _agora() + timedelta(minutes=minutos)


def _hash_codigo(codigo: str) -> str:
    segredo = get_settings().SECRET_KEY
    return sha256(f"{segredo}:{codigo}".encode("utf-8")).hexdigest()


def _em_utc(momento: datetime) -> datetime:
    if momento.tzinfo is None:
        return momento.replace(tzinfo=UTC)
    return momento.astimezone(UTC)


def _gerar_codigo() -> str:
    return f"{randbelow(1_000_000):06d}"


def gerar_codigo_vinculacao(db: Session, usuario: UsuarioAutenticado) -> CodigoVinculacao:
    if usuario.perfil != PerfilUsuario.NUTRICIONISTA:
        raise PerfilIncompativel

    # Cada nutricionista mantém um unico codigo ativo por vez; gerar um novo
    # invalida os codigos ativos anteriores daquele proprietario.
    codigos_ativos = db.execute(
        select(CodigoVinculacao).where(
            CodigoVinculacao.nutricionista_id == usuario.id,
            CodigoVinculacao.status == StatusCodigoVinculacao.ATIVO.value,
        )
    ).scalars().all()
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
            nutricionista_foto_url=usuario.foto_url,
            codigo_hash=codigo_hash,
            status=StatusCodigoVinculacao.ATIVO.value,
            expira_em=_expiracao_padrao(),
        )
        db.add(registro)
        db.commit()
        db.refresh(registro)
        registro.codigo_em_texto = codigo  # type: ignore[attr-defined]
        return registro

    raise RuntimeError("nao foi possivel gerar um codigo de vinculacao unico")


def _buscar_codigo_ativo(db: Session, codigo: str) -> CodigoVinculacao | None:
    codigo_hash = _hash_codigo(codigo)
    return db.execute(
        select(CodigoVinculacao)
        .where(CodigoVinculacao.codigo_hash == codigo_hash)
        .with_for_update()
    ).scalar_one_or_none()


def resgatar_codigo_vinculacao(
    db: Session, usuario: UsuarioAutenticado, codigo: str
) -> VinculoResgatado:
    if usuario.perfil != PerfilUsuario.PACIENTE:
        raise PerfilIncompativel

    with _lock_do_codigo(codigo):
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

        vinculo_existente = db.execute(
            select(Vinculo).where(
                Vinculo.nutricionista_id == registro.nutricionista_id,
                Vinculo.paciente_id == usuario.id,
            )
        ).scalar_one_or_none()

        if vinculo_existente is None:
            vinculo = Vinculo(nutricionista_id=registro.nutricionista_id, paciente_id=usuario.id)
            db.add(vinculo)
            try:
                db.flush()
            except IntegrityError as exc:
                db.rollback()
                raise VinculoDuplicado from exc
        else:
            vinculo = vinculo_existente

        registro.status = StatusCodigoVinculacao.RESGATADO.value
        registro.paciente_id = usuario.id
        registro.resgatado_em = agora
        db.commit()
        db.refresh(registro)
        db.refresh(vinculo)

        return VinculoResgatado(
            nutricionista_id=registro.nutricionista_id,
            nutricionista_nome=registro.nutricionista_nome,
            nutricionista_foto_url=registro.nutricionista_foto_url,
            vinculado_em=_em_utc(vinculo.criado_em),
        )