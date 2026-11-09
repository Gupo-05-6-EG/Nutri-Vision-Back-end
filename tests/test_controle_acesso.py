"""Testes de autenticacao e controle de acesso por perfil (Task 7.4, parte 1/4).

Complementa `test_auth.py` (cadastro/login) e `test_vinculos.py` (fluxo de
vinculacao) cobrindo o que fica entre os dois: o JWT em si, o esquema do header
`Authorization` e a matriz de quem pode chamar cada rota protegida.
"""

import base64
import json
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

import jwt
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import UsuarioAtual, exigir_perfil
from app.core.config import get_settings
from app.core.security import TokenInvalido, criar_token_acesso, ler_token_acesso
from app.db.session import get_db
from app.models.usuario import Perfil, Usuario
from tests import factories

ROTA_ME = "/api/v1/auth/me"
ROTA_LOGIN = "/api/v1/auth/login"
ROTA_CODIGO = "/api/v1/linking-code"
ROTA_VINCULO = "/api/v1/link"

NUTRI, PACIENTE = 20, 21


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _headers(usuario_id: int, perfil: Perfil) -> dict[str, str]:
    token, _ = criar_token_acesso(usuario_id, perfil.value)
    return _bearer(token)


def _assinar(payload: dict[str, Any], **kwargs: Any) -> str:
    settings = get_settings()
    kwargs.setdefault("key", settings.SECRET_KEY)
    kwargs.setdefault("algorithm", settings.ALGORITHM)
    return jwt.encode(payload, **kwargs)


def _b64(dados: dict[str, Any]) -> str:
    return base64.urlsafe_b64encode(json.dumps(dados).encode()).rstrip(b"=").decode()


@pytest.fixture
def usuarios(db: Session) -> None:
    factories.criar_nutricionista(db, NUTRI)
    factories.criar_paciente(db, PACIENTE)


class TestTokenDeAcesso:
    """`criar_token_acesso` / `ler_token_acesso`, sem passar pela API."""

    def test_ida_e_volta_devolve_o_id_do_usuario(self) -> None:
        token, _ = criar_token_acesso(42, Perfil.PACIENTE.value)
        assert ler_token_acesso(token) == 42

    def test_payload_traz_sub_perfil_e_datas(self) -> None:
        token, expira_em = criar_token_acesso(7, Perfil.NUTRICIONISTA.value)
        settings = get_settings()
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])

        assert payload["sub"] == "7"  # o JWT exige `sub` como string
        assert payload["perfil"] == "nutricionista"
        assert payload["exp"] == int(expira_em.timestamp())
        assert payload["iat"] < payload["exp"]

    def test_expira_em_tem_fuso_utc(self) -> None:
        _, expira_em = criar_token_acesso(1, Perfil.PACIENTE.value)
        assert expira_em.tzinfo is not None
        assert expira_em.utcoffset() == timedelta(0)

    @pytest.mark.parametrize(
        "token",
        [
            "",
            "nao-e-jwt",
            "a.b.c",
            "Bearer abc",
        ],
    )
    def test_recusa_texto_que_nao_e_jwt(self, token: str) -> None:
        with pytest.raises(TokenInvalido):
            ler_token_acesso(token)

    def test_recusa_token_sem_exp(self) -> None:
        with pytest.raises(TokenInvalido):
            ler_token_acesso(_assinar({"sub": "1"}))

    def test_recusa_token_expirado_mesmo_por_um_segundo(self) -> None:
        token = _assinar({"sub": "1", "exp": datetime.now(UTC) - timedelta(seconds=1)})
        with pytest.raises(TokenInvalido):
            ler_token_acesso(token)

    def test_recusa_algoritmo_none(self) -> None:
        """Ataque classico: token sem assinatura com `alg: none`."""
        exp = int((datetime.now(UTC) + timedelta(hours=1)).timestamp())
        token = f"{_b64({'alg': 'none', 'typ': 'JWT'})}.{_b64({'sub': '1', 'exp': exp})}."
        with pytest.raises(TokenInvalido):
            ler_token_acesso(token)

    def test_recusa_algoritmo_diferente_do_configurado(self) -> None:
        """Mesma chave, mas HS512: so o algoritmo configurado e aceito."""
        token = _assinar(
            {"sub": "1", "exp": datetime.now(UTC) + timedelta(hours=1)}, algorithm="HS512"
        )
        with pytest.raises(TokenInvalido):
            ler_token_acesso(token)

    def test_recusa_payload_adulterado(self) -> None:
        """Trocar o `sub` sem reassinar invalida o token."""
        token, _ = criar_token_acesso(1, Perfil.PACIENTE.value)
        cabecalho, _, assinatura = token.split(".")
        exp = int((datetime.now(UTC) + timedelta(hours=1)).timestamp())
        adulterado = f"{cabecalho}.{_b64({'sub': '2', 'perfil': 'nutricionista', 'exp': exp})}"
        with pytest.raises(TokenInvalido):
            ler_token_acesso(f"{adulterado}.{assinatura}")

    def test_recusa_token_assinado_com_outra_chave(self) -> None:
        token = _assinar(
            {"sub": "1", "exp": datetime.now(UTC) + timedelta(hours=1)}, key="outra-chave"
        )
        with pytest.raises(TokenInvalido):
            ler_token_acesso(token)


@pytest.mark.usefixtures("usuarios")
class TestHeaderAuthorization:
    """Formatos do header que devem ser recusados com 401 (e nao 403/500)."""

    @pytest.mark.parametrize(
        "valor",
        [
            "Basic dXN1YXJpbzpzZW5oYQ==",
            "Token {token}",
            "{token}",  # sem o esquema
            "Bearer",  # esquema sem credencial
            "Bearer ",
        ],
    )
    def test_esquema_errado_da_401(self, client: TestClient, valor: str) -> None:
        token, _ = criar_token_acesso(PACIENTE, Perfil.PACIENTE.value)
        resposta = client.get(ROTA_ME, headers={"Authorization": valor.format(token=token)})

        assert resposta.status_code == 401
        assert resposta.headers["www-authenticate"] == "Bearer"
        assert resposta.json()["detail"] == "Nao autenticado"

    def test_esquema_bearer_ignora_maiusculas(self, client: TestClient) -> None:
        token, _ = criar_token_acesso(PACIENTE, Perfil.PACIENTE.value)
        resposta = client.get(ROTA_ME, headers={"Authorization": f"bearer {token}"})
        assert resposta.status_code == 200

    def test_erro_de_autenticacao_nao_vaza_o_motivo(self, client: TestClient) -> None:
        """Expirado, adulterado ou de outra chave: a resposta e sempre a mesma."""
        expirado = _assinar({"sub": str(PACIENTE), "exp": datetime.now(UTC) - timedelta(hours=1)})
        outra_chave = _assinar(
            {"sub": str(PACIENTE), "exp": datetime.now(UTC) + timedelta(hours=1)}, key="x"
        )
        corpos = {
            client.get(ROTA_ME, headers=_bearer(token)).text
            for token in (expirado, outra_chave, "lixo")
        }
        assert len(corpos) == 1


@pytest.fixture
def app_perfis(db: Session) -> Generator[TestClient, None, None]:
    """App minima com uma rota por perfil, para testar `exigir_perfil` isolado."""
    aplicacao = FastAPI()

    @aplicacao.get("/so-paciente")
    def _paciente(
        usuario: Annotated[Usuario, Depends(exigir_perfil(Perfil.PACIENTE))],
    ) -> dict[str, int]:
        return {"id": usuario.id}

    @aplicacao.get("/so-nutricionista")
    def _nutri(
        usuario: Annotated[Usuario, Depends(exigir_perfil(Perfil.NUTRICIONISTA))],
    ) -> dict[str, int]:
        return {"id": usuario.id}

    @aplicacao.get("/qualquer-perfil")
    def _qualquer(usuario: UsuarioAtual) -> dict[str, int]:
        return {"id": usuario.id}

    aplicacao.dependency_overrides[get_db] = lambda: db
    with TestClient(aplicacao) as cliente:
        yield cliente


@pytest.mark.usefixtures("usuarios")
class TestExigirPerfil:
    @pytest.mark.parametrize(
        ("rota", "usuario_id", "perfil", "esperado"),
        [
            ("/so-paciente", PACIENTE, Perfil.PACIENTE, 200),
            ("/so-paciente", NUTRI, Perfil.NUTRICIONISTA, 403),
            ("/so-nutricionista", NUTRI, Perfil.NUTRICIONISTA, 200),
            ("/so-nutricionista", PACIENTE, Perfil.PACIENTE, 403),
            ("/qualquer-perfil", PACIENTE, Perfil.PACIENTE, 200),
            ("/qualquer-perfil", NUTRI, Perfil.NUTRICIONISTA, 200),
        ],
    )
    def test_matriz_de_perfis(
        self, app_perfis: TestClient, rota: str, usuario_id: int, perfil: Perfil, esperado: int
    ) -> None:
        resposta = app_perfis.get(rota, headers=_headers(usuario_id, perfil))

        assert resposta.status_code == esperado
        if esperado == 200:
            assert resposta.json() == {"id": usuario_id}
        else:
            assert resposta.json()["detail"] == "Perfil nao autorizado"

    @pytest.mark.parametrize("rota", ["/so-paciente", "/so-nutricionista", "/qualquer-perfil"])
    def test_sem_token_da_401_antes_de_checar_perfil(
        self, app_perfis: TestClient, rota: str
    ) -> None:
        assert app_perfis.get(rota).status_code == 401

    def test_perfil_do_token_nao_eleva_privilegio(self, app_perfis: TestClient) -> None:
        """O perfil e lido do banco: um paciente com `perfil` forjado continua barrado."""
        resposta = app_perfis.get(
            "/so-nutricionista", headers=_headers(PACIENTE, Perfil.NUTRICIONISTA)
        )
        assert resposta.status_code == 403

    def test_mudanca_de_perfil_no_banco_vale_no_proximo_request(
        self, app_perfis: TestClient, db: Session
    ) -> None:
        headers = _headers(PACIENTE, Perfil.PACIENTE)
        assert app_perfis.get("/so-paciente", headers=headers).status_code == 200

        usuario = db.get(Usuario, PACIENTE)
        usuario.perfil = Perfil.NUTRICIONISTA.value
        db.commit()

        assert app_perfis.get("/so-paciente", headers=headers).status_code == 403


@pytest.mark.usefixtures("usuarios")
class TestRotasProtegidasDaApi:
    """Matriz de acesso das rotas reais que exigem perfil (vinculacao, Task 1.4)."""

    @pytest.mark.parametrize(
        ("metodo", "rota", "corpo"),
        [
            ("post", ROTA_CODIGO, None),
            ("post", ROTA_VINCULO, {"codigo": "123456"}),
            ("get", ROTA_ME, None),
        ],
    )
    def test_anonimo_recebe_401(
        self, client: TestClient, metodo: str, rota: str, corpo: dict | None
    ) -> None:
        resposta = client.request(metodo, rota, json=corpo)
        assert resposta.status_code == 401

    def test_so_nutricionista_gera_codigo(self, client: TestClient) -> None:
        assert (
            client.post(ROTA_CODIGO, headers=_headers(PACIENTE, Perfil.PACIENTE)).status_code == 403
        )
        assert (
            client.post(ROTA_CODIGO, headers=_headers(NUTRI, Perfil.NUTRICIONISTA)).status_code
            == 200
        )

    def test_so_paciente_resgata_codigo(self, client: TestClient) -> None:
        codigo = client.post(ROTA_CODIGO, headers=_headers(NUTRI, Perfil.NUTRICIONISTA)).json()[
            "codigo"
        ]

        resposta_nutri = client.post(
            ROTA_VINCULO, json={"codigo": codigo}, headers=_headers(NUTRI, Perfil.NUTRICIONISTA)
        )
        resposta_paciente = client.post(
            ROTA_VINCULO, json={"codigo": codigo}, headers=_headers(PACIENTE, Perfil.PACIENTE)
        )

        assert resposta_nutri.status_code == 403
        assert resposta_paciente.status_code == 200


class TestTokenDoLoginNasRotasProtegidas:
    """Ponta a ponta: o token devolvido pelo login abre as rotas do perfil certo."""

    def test_nutricionista_logado_gera_codigo_e_paciente_logado_resgata(
        self, client: TestClient
    ) -> None:
        nutri = client.post(
            "/api/v1/auth/cadastro/nutricionista",
            json=factories.cadastro(email="nutri@exemplo.com", crn="CRN-3 99999"),
        )
        paciente = client.post(
            "/api/v1/auth/cadastro/paciente", json=factories.cadastro(email="pac@exemplo.com")
        )
        assert nutri.status_code == paciente.status_code == 201

        login_nutri = client.post(
            ROTA_LOGIN, json={"email": "nutri@exemplo.com", "senha": factories.SENHA_PADRAO}
        ).json()
        login_paciente = client.post(
            ROTA_LOGIN, json={"email": "pac@exemplo.com", "senha": factories.SENHA_PADRAO}
        ).json()

        codigo = client.post(ROTA_CODIGO, headers=_bearer(login_nutri["access_token"]))
        assert codigo.status_code == 200

        vinculo = client.post(
            ROTA_VINCULO,
            json={"codigo": codigo.json()["codigo"]},
            headers=_bearer(login_paciente["access_token"]),
        )
        assert vinculo.status_code == 200
        assert vinculo.json()["nutricionista"]["id"] == login_nutri["usuario"]["id"]

    def test_token_continua_valido_depois_de_novo_login(self, client: TestClient) -> None:
        """Logar de novo nao derruba o token anterior (sem revogacao por enquanto)."""
        cadastro = client.post("/api/v1/auth/cadastro/paciente", json=factories.cadastro()).json()
        client.post(ROTA_LOGIN, json={"email": "ana@exemplo.com", "senha": factories.SENHA_PADRAO})

        assert client.get(ROTA_ME, headers=_bearer(cadastro["access_token"])).status_code == 200

    def test_senha_nao_aparece_em_nenhuma_resposta(self, client: TestClient) -> None:
        cadastro = client.post("/api/v1/auth/cadastro/paciente", json=factories.cadastro())
        login = client.post(
            ROTA_LOGIN, json={"email": "ana@exemplo.com", "senha": factories.SENHA_PADRAO}
        )
        me = client.get(ROTA_ME, headers=_bearer(login.json()["access_token"]))

        for resposta in (cadastro, login, me):
            assert factories.SENHA_PADRAO not in resposta.text
            assert "senha" not in resposta.text
