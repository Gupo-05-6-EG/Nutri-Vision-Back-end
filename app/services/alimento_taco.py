"""Regras de negocio do Banco Nutricional TACO (RF02.2)."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.texto import palavras_da_busca
from app.models.alimento_taco import AlimentoTaco


def buscar_por_nome(
    db: Session,
    nome: str,
    limite: int = 20,
    deslocamento: int = 0,
) -> list[AlimentoTaco]:
    """Alimentos cujo nome contem `nome`, sem diferenciar acento nem maiusculas.

    Busca por substring: "frango" encontra "Frango, peito, sem pele, cru" e
    tambem "Frango, coxa, com pele, assada"; "feijao" encontra "Feijão".
    """
    filtros = [
        AlimentoTaco.nome_normalizado.contains(palavra, autoescape=True)
        for palavra in palavras_da_busca(nome)
    ]
    consulta = (
        select(AlimentoTaco)
        .where(*filtros)
        .order_by(AlimentoTaco.nome)
        .limit(limite)
        .offset(deslocamento)
    )
    return list(db.execute(consulta).scalars())
