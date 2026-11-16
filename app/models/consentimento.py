"""Historico de consentimento para tratamento de dados pessoais (LGPD)."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Consentimento(Base):
    """Uma concessao de consentimento vinculada a uma versao do termo."""

    __tablename__ = "consentimentos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    usuario_id: Mapped[int] = mapped_column(
        ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False, index=True
    )
    versao_termo: Mapped[str] = mapped_column(String(40), nullable=False)
    aceito_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    revogado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
