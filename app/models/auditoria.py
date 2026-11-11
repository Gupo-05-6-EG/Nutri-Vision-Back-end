"""Trilha de auditoria das alteracoes em planos e dados clinicos (Task 5.3, RNF08).

Cada linha registra uma alteracao: quem fez (`autor_id`), quando (`criado_em`) e
os valores `antes` e `depois`. A tabela so recebe linhas novas: nenhuma rota edita
ou apaga auditoria.

`antes` e `depois` guardam copias dos dados de saude do paciente, entao ficam
cifrados em repouso como o resto (ver `app.core.crypto`).
"""

from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.crypto import JsonCifrado
from app.db.base import Base


class EntidadeAuditada(StrEnum):
    PLANO_ALIMENTAR = "plano_alimentar"
    DADOS_CLINICOS = "dados_clinicos"


class AcaoAuditoria(StrEnum):
    """`criacao`: nao havia valor antes (`antes` e nulo). `atualizacao`: havia."""

    CRIACAO = "criacao"
    ATUALIZACAO = "atualizacao"


class Auditoria(Base):
    __tablename__ = "auditorias"
    __table_args__ = (Index("ix_auditorias_paciente_criado_em", "paciente_id", "criado_em"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # CASCADE: apagar o paciente apaga os dados de saude dele, inclusive as copias.
    paciente_id: Mapped[int] = mapped_column(
        ForeignKey("pacientes.id", ondelete="CASCADE"), nullable=False
    )
    # SET NULL: a auditoria sobrevive a remocao da conta de quem fez a alteracao.
    autor_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True
    )
    entidade: Mapped[str] = mapped_column(String(30), nullable=False)
    # Id do registro alterado: o plano (versao nova) ou o proprio paciente.
    registro_id: Mapped[int] = mapped_column(Integer, nullable=False)
    acao: Mapped[str] = mapped_column(String(20), nullable=False)
    antes: Mapped[dict[str, Any] | None] = mapped_column(JsonCifrado, nullable=True)
    depois: Mapped[dict[str, Any]] = mapped_column(JsonCifrado, nullable=False)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
