"""Regras de negocio do Banco Nutricional TACO (RF02.2)."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.alimento_taco import AlimentoTaco


def buscar_por_nome(
    db: Session,
    nome: str,
    limite: int = 20,
    deslocamento: int = 0,
) -> list[AlimentoTaco]:
    """Alimentos cujo nome contem `nome` (case-insensitive), em ordem alfabetica.

    Busca por substring: "frango" encontra "Frango, peito, sem pele, cru" e
    tambem "Frango, coxa, com pele, assada".
    """
    termo = nome.strip()
    consulta = (
        select(AlimentoTaco)
        .where(AlimentoTaco.nome.ilike(f"%{termo}%"))
        .order_by(AlimentoTaco.nome)
        .limit(limite)
        .offset(deslocamento)
    )
    return list(db.execute(consulta).scalars())
