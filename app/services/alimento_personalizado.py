"""Regras de negocio dos alimentos personalizados e da busca unificada (RF22)."""

from sqlalchemy import func, literal, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.alimento_personalizado import AlimentoPersonalizado
from app.models.alimento_taco import AlimentoTaco
from app.schemas.alimento_personalizado import (
    CATEGORIA_PERSONALIZADO,
    AlimentoBuscaOut,
    AlimentoPersonalizadoCreate,
    OrigemAlimento,
)


class AlimentoJaCadastrado(Exception):
    """O paciente ja tem um alimento personalizado com esse nome."""


def criar_alimento(db: Session, dados: AlimentoPersonalizadoCreate) -> AlimentoPersonalizado:
    ja_existe = db.execute(
        select(AlimentoPersonalizado.id).where(
            AlimentoPersonalizado.paciente_id == dados.paciente_id,
            func.lower(AlimentoPersonalizado.nome) == dados.nome.lower(),
        )
    ).first()
    if ja_existe is not None:
        raise AlimentoJaCadastrado

    alimento = AlimentoPersonalizado(**dados.model_dump())
    db.add(alimento)
    try:
        db.commit()
    except IntegrityError:  # corrida entre dois cadastros iguais
        db.rollback()
        raise AlimentoJaCadastrado from None
    db.refresh(alimento)
    return alimento


def buscar_alimentos(
    db: Session,
    nome: str,
    paciente_id: int | None = None,
    limite: int = 20,
    deslocamento: int = 0,
) -> list[AlimentoBuscaOut]:
    """Busca por nome na TACO e nos alimentos personalizados, numa lista so.

    Sem `paciente_id` a busca cobre apenas a TACO: um alimento personalizado
    so aparece para o paciente que o cadastrou. Ordem alfabetica, com paginacao
    aplicada sobre a uniao das duas tabelas.
    """
    padrao = f"%{nome.strip()}%"

    taco = select(
        literal(OrigemAlimento.TACO.value).label("origem"),
        AlimentoTaco.id.label("id"),
        AlimentoTaco.nome.label("nome"),
        AlimentoTaco.categoria.label("categoria"),
        AlimentoTaco.kcal_100g.label("kcal_100g"),
        AlimentoTaco.carbs_100g.label("carbs_100g"),
        AlimentoTaco.prot_100g.label("prot_100g"),
        AlimentoTaco.gord_100g.label("gord_100g"),
    ).where(AlimentoTaco.nome.ilike(padrao))

    fontes = [taco]
    if paciente_id is not None:
        fontes.append(
            select(
                literal(OrigemAlimento.PERSONALIZADO.value).label("origem"),
                AlimentoPersonalizado.id.label("id"),
                AlimentoPersonalizado.nome.label("nome"),
                literal(CATEGORIA_PERSONALIZADO).label("categoria"),
                AlimentoPersonalizado.kcal_100g.label("kcal_100g"),
                AlimentoPersonalizado.carbs_100g.label("carbs_100g"),
                AlimentoPersonalizado.prot_100g.label("prot_100g"),
                AlimentoPersonalizado.gord_100g.label("gord_100g"),
            ).where(
                AlimentoPersonalizado.paciente_id == paciente_id,
                AlimentoPersonalizado.nome.ilike(padrao),
            )
        )

    uniao = fontes[0].union_all(*fontes[1:]).subquery()
    consulta = (
        select(uniao)
        .order_by(uniao.c.nome, uniao.c.origem, uniao.c.id)
        .limit(limite)
        .offset(deslocamento)
    )
    return [AlimentoBuscaOut.model_validate(linha._mapping) for linha in db.execute(consulta)]
