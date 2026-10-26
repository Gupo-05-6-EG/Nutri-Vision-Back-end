"""Ajudantes para montar payloads nos testes."""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.core.security import gerar_hash_senha
from app.models.paciente import Paciente
from app.models.usuario import Perfil, Usuario

SENHA_PADRAO = "senha-forte-123"
# Calculado uma vez: bcrypt e lento de proposito, e cada teste cria pacientes.
HASH_SENHA_PADRAO = gerar_hash_senha(SENHA_PADRAO)


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
    tipo: str | None = None,
    itens: list[dict[str, Any]] | None = None,
    observacao: str | None = None,
) -> dict[str, Any]:
    momento = consumida_em or datetime.now(UTC) - timedelta(hours=1)
    payload = {
        "paciente_id": paciente_id,
        "consumida_em": momento.isoformat(),
        "observacao": observacao,
        "itens": itens if itens is not None else [item()],
    }
    if tipo is not None:
        payload["tipo"] = tipo
    return payload


def cadastro(email: str = "ana@exemplo.com", senha: str = SENHA_PADRAO, **extra: Any) -> dict:
    return {"nome": "Ana Souza", "email": email, "senha": senha, **extra}


def criar_paciente(db: Session, paciente_id: int) -> Paciente:
    """Cria usuario + paciente direto no banco, com id fixo (sem passar pela API)."""
    db.add(
        Usuario(
            id=paciente_id,
            nome=f"Paciente {paciente_id}",
            email=f"paciente{paciente_id}@exemplo.com",
            senha_hash=HASH_SENHA_PADRAO,
            perfil=Perfil.PACIENTE.value,
        )
    )
    db.flush()
    paciente = Paciente(id=paciente_id)
    db.add(paciente)
    db.commit()
    return paciente
