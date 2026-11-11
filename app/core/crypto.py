"""Criptografia de dados sensiveis em repouso (Task 1.6, RNF06).

Os dados de saude do paciente (triagem e observacao das refeicoes) sao gravados
cifrados com Fernet (AES-128-CBC + HMAC-SHA256, da lib `cryptography`). A cifra e
a decifragem acontecem nos tipos de coluna abaixo, entao o resto do codigo segue
lendo e gravando `Decimal`, `int` e `str` normalmente.

Consequencia: o banco guarda texto opaco, entao nao da para filtrar, ordenar ou
somar essas colunas em SQL. Nenhuma query faz isso hoje; se precisar, a conta
tem que ser feita em Python.

A chave vem de `ENCRYPTION_KEY`. Perder a chave = perder os dados cifrados.
"""

from collections.abc import Callable
from decimal import Decimal
from functools import lru_cache
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import Text
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator

from app.core.config import get_settings


class ErroDeCriptografia(Exception):
    """Valor cifrado que nao abre com a chave atual (chave trocada ou dado adulterado)."""


@lru_cache
def _fernet(chave: str) -> Fernet:
    return Fernet(chave.encode())


def cifrar(texto: str) -> str:
    return _fernet(get_settings().ENCRYPTION_KEY).encrypt(texto.encode()).decode()


def decifrar(token: str) -> str:
    try:
        return _fernet(get_settings().ENCRYPTION_KEY).decrypt(token.encode()).decode()
    except InvalidToken as erro:
        raise ErroDeCriptografia(
            "nao foi possivel decifrar o valor com a ENCRYPTION_KEY atual"
        ) from erro


class _ColunaCifrada(TypeDecorator[Any]):
    """Coluna TEXT que guarda o valor cifrado e devolve o tipo Python original."""

    impl = Text
    cache_ok = True

    # Cada subclasse diz como virar texto antes de cifrar e como voltar depois.
    para_texto: Callable[[Any], str] = staticmethod(str)
    de_texto: Callable[[str], Any] = staticmethod(str)

    def process_bind_param(self, value: Any, dialect: Dialect) -> str | None:
        if value is None:
            return None
        return cifrar(self.para_texto(value))

    def process_result_value(self, value: str | None, dialect: Dialect) -> Any:
        if value is None:
            return None
        return self.de_texto(decifrar(value))


class TextoCifrado(_ColunaCifrada):
    """`str` cifrada."""


class InteiroCifrado(_ColunaCifrada):
    """`int` cifrado."""

    de_texto = staticmethod(int)


class DecimalCifrado(_ColunaCifrada):
    """`Decimal` cifrado (guardado como texto, sem perder casas decimais)."""

    de_texto = staticmethod(Decimal)
