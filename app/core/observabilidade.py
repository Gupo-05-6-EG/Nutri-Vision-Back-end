"""Logs estruturados e rastreio de requisicoes (Task 7.1, RNF09).

- Cada requisicao recebe um id (`X-Request-ID`): o do cliente/proxy, se vier, ou
  um novo. Ele volta no header da resposta e vai em todas as linhas de log da
  requisicao, entao um erro reportado pelo app pode ser achado nos logs.
- Uma linha de log de acesso por requisicao, com metodo, caminho, status e
  duracao. Em producao (`LOG_JSON`), em JSON: uma linha por evento, pronta para
  um agregador (Loki, CloudWatch, Better Stack...) filtrar e alertar.
"""

import json
import logging
import time
import uuid
from contextvars import ContextVar
from datetime import UTC, datetime

from starlette.types import ASGIApp, Message, Receive, Scope, Send

request_id: ContextVar[str] = ContextVar("request_id", default="-")

logger_acesso = logging.getLogger("nutrivision.acesso")
logger_erro = logging.getLogger("nutrivision.erro")

# Campos padrao do LogRecord: o que nao esta aqui veio de `extra=` e vai pro JSON.
_CAMPOS_PADRAO = set(vars(logging.makeLogRecord({}))) | {"message", "asctime"}


class _ComRequestId(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id.get()
        return True


class FormatoJson(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        evento = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "nivel": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        evento.update({k: v for k, v in vars(record).items() if k not in _CAMPOS_PADRAO})
        if record.exc_info:
            evento["erro"] = self.formatException(record.exc_info)
        return json.dumps(evento, ensure_ascii=False, default=str)


def configurar_logs(nivel: str, json_: bool) -> None:
    """Configura o logger raiz. Idempotente (o app pode ser criado varias vezes)."""
    handler = logging.StreamHandler()
    handler.addFilter(_ComRequestId())
    handler.setFormatter(
        FormatoJson()
        if json_
        else logging.Formatter("%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s")
    )
    raiz = logging.getLogger()
    raiz.handlers = [handler]
    raiz.setLevel(nivel.upper())
    # O uvicorn ja loga cada acesso; o nosso log de acesso tem o request id.
    logging.getLogger("uvicorn.access").disabled = True


class RastreioMiddleware:
    """Middleware ASGI: request id, log de acesso e log de erro nao tratado."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope["headers"])
        recebido = headers.get(b"x-request-id", b"").decode("latin-1")[:64]
        rid = recebido if recebido.isprintable() and recebido else uuid.uuid4().hex
        token = request_id.set(rid)
        inicio = time.perf_counter()
        status = 500

        async def enviar(mensagem: Message) -> None:
            nonlocal status
            if mensagem["type"] == "http.response.start":
                status = mensagem["status"]
                mensagem.setdefault("headers", []).append((b"x-request-id", rid.encode()))
            await send(mensagem)

        try:
            await self.app(scope, receive, enviar)
        except Exception:
            logger_erro.exception("erro nao tratado em %s %s", scope["method"], scope["path"])
            raise
        finally:
            logger_acesso.info(
                "%s %s %s",
                scope["method"],
                scope["path"],
                status,
                extra={
                    "metodo": scope["method"],
                    "caminho": scope["path"],
                    "status": status,
                    "duracao_ms": round((time.perf_counter() - inicio) * 1000, 1),
                },
            )
            request_id.reset(token)
