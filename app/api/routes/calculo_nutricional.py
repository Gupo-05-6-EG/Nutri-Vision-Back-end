"""Endpoint de calculo nutricional por porcao (RF03, RF20, RF21).

Recebe as classes reconhecidas pelo modelo de IA com o metodo de preparo e as
gramas, mapeia cada uma para a TACO e devolve kcal, proteinas, carboidratos e
gorduras por item e da refeicao. Nao grava nada: o registro da refeicao
continua em `POST /refeicoes`.
"""

from fastapi import APIRouter, HTTPException, status

from app.db.deps import DbSession
from app.schemas.calculo_nutricional import CalculoNutricionalIn, CalculoNutricionalOut
from app.services import calculo_nutricional as servico

router = APIRouter(prefix="/calculo-nutricional", tags=["calculo-nutricional"])


@router.post(
    "",
    response_model=CalculoNutricionalOut,
    summary="Calcula a tabela nutricional da refeicao a partir das classes da IA",
)
def calcular(dados: CalculoNutricionalIn, db: DbSession) -> CalculoNutricionalOut:
    try:
        resultado = servico.calcular_refeicao(db, dados.itens)
    except servico.SemMapeamento as erro:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Sem mapeamento TACO para a classe '{erro.classe}' "
            f"com preparo '{erro.metodo_preparo}'",
        ) from None
    except servico.AlimentoTacoAusente as erro:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"Alimento '{erro.nome}' nao encontrado na tabela TACO (rode scripts/importar_taco.py)",
        ) from None
    return CalculoNutricionalOut.model_validate(resultado)
