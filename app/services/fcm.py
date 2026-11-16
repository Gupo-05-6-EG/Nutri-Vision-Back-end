"""Envio de push via Firebase Cloud Messaging (Task 2.8, RF26).

O `firebase_admin` e importado so na hora de enviar, entao o resto da app (e os
testes, que usam um envio falso) nao depende dele nem de credenciais.
"""

import logging
from enum import StrEnum
from functools import lru_cache
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class FcmNaoConfigurado(RuntimeError):
    """`FCM_CREDENTIALS_FILE` nao foi definido."""


class ResultadoPush(StrEnum):
    ENVIADO = "enviado"
    # O FCM disse que o token nao existe mais (app desinstalado, token trocado).
    TOKEN_INVALIDO = "token_invalido"
    # Falha que pode se resolver sozinha (rede, indisponibilidade); tenta de novo.
    FALHA = "falha"


@lru_cache
def _app_firebase() -> Any:
    import firebase_admin
    from firebase_admin import credentials

    caminho = get_settings().FCM_CREDENTIALS_FILE
    if not caminho:
        raise FcmNaoConfigurado("Defina FCM_CREDENTIALS_FILE com o JSON da conta de servico")
    return firebase_admin.initialize_app(credentials.Certificate(caminho))


def enviar_push_fcm(token: str, titulo: str, corpo: str, dados: dict[str, str]) -> ResultadoPush:
    """Envia uma notificacao para um token FCM."""
    from firebase_admin import exceptions, messaging

    app = _app_firebase()
    mensagem = messaging.Message(
        token=token,
        notification=messaging.Notification(title=titulo, body=corpo),
        data=dados,
    )
    try:
        messaging.send(mensagem, app=app)
    except (messaging.UnregisteredError, messaging.SenderIdMismatchError):
        return ResultadoPush.TOKEN_INVALIDO
    except (exceptions.FirebaseError, ValueError):
        logger.exception("Falha ao enviar push FCM")
        return ResultadoPush.FALHA
    return ResultadoPush.ENVIADO
