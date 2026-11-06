"""Schemas de cadastro, login e token (RF13)."""

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_serializer, field_validator

from app.core.security import BCRYPT_MAX_BYTES
from app.models.usuario import Perfil

SENHA_MIN = 8


def _normalizar_email(valor: str) -> str:
    return valor.strip().lower()


class _CadastroBase(BaseModel):
    nome: str = Field(min_length=2, max_length=120)
    email: EmailStr = Field(max_length=254)
    senha: str = Field(min_length=SENHA_MIN, description=f"Minimo de {SENHA_MIN} caracteres")

    @field_validator("nome")
    @classmethod
    def _nome_sem_espacos_nas_pontas(cls, valor: str) -> str:
        limpo = valor.strip()
        if len(limpo) < 2:
            raise ValueError("nome deve ter pelo menos 2 caracteres")
        return limpo

    @field_validator("email")
    @classmethod
    def _email_minusculo(cls, valor: str) -> str:
        return _normalizar_email(valor)

    @field_validator("senha")
    @classmethod
    def _senha_cabe_no_bcrypt(cls, valor: str) -> str:
        if len(valor.encode()) > BCRYPT_MAX_BYTES:
            raise ValueError(f"senha deve ter no maximo {BCRYPT_MAX_BYTES} bytes")
        return valor


class CadastroPacienteIn(_CadastroBase):
    """Cadastro do paciente. Peso, altura etc. vem depois, na triagem (RF14)."""


class CadastroNutricionistaIn(_CadastroBase):
    crn: str = Field(min_length=3, max_length=20, description="Registro no CRN, ex.: 'CRN-3 12345'")

    @field_validator("crn")
    @classmethod
    def _crn_normalizado(cls, valor: str) -> str:
        # Maiusculas e espacos colapsados: "crn-3  12345" e "CRN-3 12345" sao o mesmo.
        limpo = " ".join(valor.split()).upper()
        if len(limpo) < 3:
            raise ValueError("crn invalido")
        return limpo


class LoginIn(BaseModel):
    email: EmailStr
    senha: str = Field(min_length=1, max_length=256)

    @field_validator("email")
    @classmethod
    def _email_minusculo(cls, valor: str) -> str:
        return _normalizar_email(valor)


class UsuarioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nome: str
    email: str
    perfil: Perfil
    crn: str | None = Field(default=None, description="So para nutricionistas")
    criado_em: datetime

    @field_serializer("criado_em")
    def _sempre_com_fuso(self, valor: datetime) -> datetime:
        return valor if valor.tzinfo else valor.replace(tzinfo=UTC)


class TokenOut(BaseModel):
    """Resposta do cadastro e do login: o token ja vem pronto para uso."""

    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expira_em: datetime
    usuario: UsuarioOut
