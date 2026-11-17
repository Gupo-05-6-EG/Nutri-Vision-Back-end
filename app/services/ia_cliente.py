"""Cliente HTTP do servico de IA (Nutri-Vision-IA).

O servico analisa a foto de uma refeicao de forma assincrona:
`POST /api/v1/analyses` recebe a foto e devolve um id, e
`GET /api/v1/analyses/{id}` devolve o andamento e, no fim, os alimentos da TACO
com as gramas estimadas. Este modulo so fala HTTP e traduz as falhas para
excecoes do dominio; quem monta a resposta da nossa API e `analise_ia`.
"""

from collections.abc import Iterator
from typing import Any
from uuid import UUID

import httpx

from app.core.config import get_settings

ROTA_ANALISES = "/api/v1/analyses"


class ServicoIAIndisponivel(Exception):
    """O servico de IA esta fora do ar, demorou demais ou respondeu com erro 5xx."""


class AnaliseNaoEncontrada(Exception):
    """Nao existe analise com esse id, ou o resultado ja expirou (24 h)."""


class FotoRecusada(Exception):
    """O servico de IA recusou a foto (tamanho, formato ou arquivo vazio)."""

    def __init__(self, status_code: int, detalhe: str) -> None:
        super().__init__(detalhe)
        self.status_code = status_code
        self.detalhe = detalhe


def get_cliente_ia() -> Iterator[httpx.Client]:
    """Dependencia FastAPI: um cliente HTTP para o servico de IA por requisicao."""
    settings = get_settings()
    with httpx.Client(
        base_url=settings.AI_SERVICE_URL, timeout=settings.AI_SERVICE_TIMEOUT_S
    ) as cliente:
        yield cliente


def _detalhe(resposta: httpx.Response) -> str:
    try:
        corpo = resposta.json()
    except ValueError:
        return resposta.text or resposta.reason_phrase
    if isinstance(corpo, dict) and isinstance(corpo.get("detail"), str):
        return corpo["detail"]
    return resposta.reason_phrase


def _requisitar(cliente: httpx.Client, metodo: str, url: str, **kwargs: Any) -> httpx.Response:
    try:
        resposta = cliente.request(metodo, url, **kwargs)
    except httpx.TransportError as erro:  # conexao recusada, timeout, DNS...
        raise ServicoIAIndisponivel(str(erro)) from erro
    if resposta.status_code >= 500:
        raise ServicoIAIndisponivel(_detalhe(resposta))
    return resposta


def enviar_foto(
    cliente: httpx.Client, conteudo: bytes, nome_arquivo: str, content_type: str
) -> dict[str, Any]:
    """Envia a foto para analise. Devolve `{id, status}` (e `reason`/`issues` se a
    foto ja for recusada na checagem de qualidade)."""
    resposta = _requisitar(
        cliente,
        "POST",
        ROTA_ANALISES,
        files={"file": (nome_arquivo, conteudo, content_type)},
    )
    if resposta.status_code in (413, 415, 422):
        raise FotoRecusada(resposta.status_code, _detalhe(resposta))
    if resposta.status_code not in (200, 201, 202):
        raise ServicoIAIndisponivel(f"resposta inesperada: {resposta.status_code}")
    return resposta.json()


def consultar_analise(cliente: httpx.Client, analise_id: UUID) -> dict[str, Any]:
    """Andamento ou resultado da analise."""
    resposta = _requisitar(cliente, "GET", f"{ROTA_ANALISES}/{analise_id}")
    if resposta.status_code == 404:
        raise AnaliseNaoEncontrada
    if resposta.status_code != 200:
        raise ServicoIAIndisponivel(f"resposta inesperada: {resposta.status_code}")
    return resposta.json()
