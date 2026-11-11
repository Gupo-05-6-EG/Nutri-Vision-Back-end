"""Hash de senha (bcrypt) e token de acesso (JWT) - RF13.

Usa a lib `bcrypt` direto, sem passlib: o passlib esta sem manutencao e quebra
com as versoes atuais do bcrypt.
"""

from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.core.config import get_settings

# O bcrypt so considera os primeiros 72 bytes da senha e recusa o resto. O
# schema de entrada limita a senha a isso, para nao truncar em silencio.
BCRYPT_MAX_BYTES = 72


class TokenInvalido(Exception):
    """Token ausente, malformado, com assinatura invalida ou expirado."""


def gerar_hash_senha(senha: str) -> str:
    return bcrypt.hashpw(senha.encode(), bcrypt.gensalt()).decode()


def verificar_senha(senha: str, senha_hash: str) -> bool:
    return bcrypt.checkpw(senha.encode(), senha_hash.encode())


# Hash de uma senha qualquer, usado no login quando o email nao existe: comparar
# contra ele leva o mesmo tempo de um email existente, entao o tempo de resposta
# nao revela quais emails estao cadastrados.
HASH_FICTICIO = gerar_hash_senha("senha-ficticia-para-tempo-constante")


def criar_token_acesso(usuario_id: int, perfil: str) -> tuple[str, datetime]:
    """Gera o JWT de acesso. Devolve o token e o instante em que ele expira."""
    settings = get_settings()
    agora = datetime.now(UTC)
    expira_em = agora + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": str(usuario_id), "perfil": perfil, "iat": agora, "exp": expira_em}
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return token, expira_em


def ler_token_acesso(token: str) -> int:
    """Valida o JWT e devolve o id do usuario (`sub`)."""
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            options={"require": ["sub", "exp"]},
        )
        return int(payload["sub"])
    except (jwt.PyJWTError, ValueError) as erro:
        raise TokenInvalido from erro
