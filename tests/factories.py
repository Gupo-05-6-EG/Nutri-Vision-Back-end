"""Ajudantes para montar payloads nos testes."""

from datetime import UTC, datetime, timedelta
from typing import Any


def item(
    nome: str = "Arroz branco cozido",
    quantidade_g: str = "150.00",
    calorias: str = "193.50",
    proteinas: str = "3.75",
    carboidratos: str = "42.45",
    gorduras: str = "0.30",
) -> dict[str, Any]:
    return {
        "nome_alimento": nome,
        "quantidade_g": quantidade_g,
        "calorias_kcal": calorias,
        "proteinas_g": proteinas,
        "carboidratos_g": carboidratos,
        "gorduras_g": gorduras,
    }


def refeicao(
    paciente_id: int = 1,
    consumida_em: datetime | None = None,
    itens: list[dict[str, Any]] | None = None,
    observacao: str | None = None,
) -> dict[str, Any]:
    momento = consumida_em or datetime.now(UTC) - timedelta(hours=1)
    return {
        "paciente_id": paciente_id,
        "consumida_em": momento.isoformat(),
        "observacao": observacao,
        "itens": itens if itens is not None else [item()],
    }
