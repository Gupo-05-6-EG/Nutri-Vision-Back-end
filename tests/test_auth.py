"""Testes do cadastro e login (RF13)."""

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.security import criar_token_acesso, gerar_hash_senha, verificar_senha
from app.models.paciente import Paciente
from app.models.usuario import Nutricionista, Usuario
from tests import factories

ROTA_PACIENTE = "/api/v1/auth/cadastro/paciente"
ROTA_NUTRI = "/api/v1/auth/cadastro/nutricionista"
ROTA_LOGIN = "/api/v1/auth/login"
ROTA_ME = "/api/v1/auth/me"


def _cadastrar_paciente(client: TestClient, **kwargs: Any) -> dict[str, Any]:
    resposta = client.post(ROTA_PACIENTE, json=factories.cadastro(**kwargs))
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


def _cadastrar_nutri(client: TestClient, **kwargs: Any) -> dict[str, Any]:
    kwargs.setdefault("email", "nutri@exemplo.com")
    kwargs.setdefault("crn", "CRN-3 12345")
    resposta = client.post(ROTA_NUTRI, json=factories.cadastro(**kwargs))
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class TestSenha:
    def test_hash_bcrypt_e_verificacao(self) -> None:
        senha_hash = gerar_hash_senha("senha-forte-123")

        assert senha_hash.startswith("$2b$")
        assert senha_hash != "senha-forte-123"
        assert verificar_senha("senha-forte-123", senha_hash)
        assert not verificar_senha("senha-errada", senha_hash)

    def test_mesma_senha_gera_hashes_diferentes(self) -> None:
        assert gerar_hash_senha("senha-forte-123") != gerar_hash_senha("senha-forte-123")


class TestCadastroPaciente:
    def test_cria_usuario_e_paciente_e_devolve_token(self, client: TestClient, db: Session) -> None:
        corpo = _cadastrar_paciente(client)

        assert corpo["token_type"] == "bearer"
        assert corpo["access_token"]
        usuario = corpo["usuario"]
        assert usuario["nome"] == "Ana Souza"
        assert usuario["email"] == "ana@exemplo.com"
        assert usuario["perfil"] == "paciente"
        assert usuario["crn"] is None
        assert "senha" not in usuario
        assert "senha_hash" not in usuario

        db.expire_all()
        paciente = db.get(Paciente, usuario["id"])
        assert paciente is not None
        assert paciente.meta_kcal is None, "a triagem vem depois"

    def test_senha_e_gravada_como_hash(self, client: TestClient, db: Session) -> None:
        corpo = _cadastrar_paciente(client)

        usuario = db.get(Usuario, corpo["usuario"]["id"])
        assert usuario is not None
        assert usuario.senha_hash != factories.SENHA_PADRAO
        assert verificar_senha(factories.SENHA_PADRAO, usuario.senha_hash)

    def test_expiracao_padrao_e_7_dias(self) -> None:
        # _env_file=None: o padrao do codigo, sem o .env de quem roda o teste.
        assert Settings(_env_file=None).ACCESS_TOKEN_EXPIRE_MINUTES == 7 * 24 * 60

    def test_token_expira_conforme_configuracao(self, client: TestClient, monkeypatch) -> None:
        monkeypatch.setattr(get_settings(), "ACCESS_TOKEN_EXPIRE_MINUTES", 7 * 24 * 60)
        corpo = _cadastrar_paciente(client)

        settings = get_settings()
        payload = jwt.decode(
            corpo["access_token"], settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        assert payload["exp"] - payload["iat"] == 7 * 24 * 60 * 60
        assert payload["sub"] == str(corpo["usuario"]["id"])
        assert payload["perfil"] == "paciente"

        expira_em = datetime.fromisoformat(corpo["expira_em"])
        assert expira_em.tzinfo is not None
        assert expira_em - datetime.now(UTC) > timedelta(days=6, hours=23)

    def test_email_e_normalizado(self, client: TestClient) -> None:
        corpo = _cadastrar_paciente(client, email="  Ana@Exemplo.COM ")

        assert corpo["usuario"]["email"] == "ana@exemplo.com"

    def test_email_duplicado_da_409(self, client: TestClient) -> None:
        _cadastrar_paciente(client)

        resposta = client.post(ROTA_PACIENTE, json=factories.cadastro(email="ANA@exemplo.com"))

        assert resposta.status_code == 409
        assert resposta.json()["detail"] == "Email ja cadastrado"

    @pytest.mark.parametrize(
        "alteracao",
        [
            {"email": "nao-e-email"},
            {"email": ""},
            {"senha": "curta"},
            {"senha": "a" * 73},  # passa do limite de 72 bytes do bcrypt
            {"senha": "é" * 37},  # 37 caracteres, mas 74 bytes em UTF-8
            {"nome": " "},
            {"nome": "a" * 121},
        ],
    )
    def test_recusa_dados_invalidos(
        self, client: TestClient, db: Session, alteracao: dict[str, Any]
    ) -> None:
        resposta = client.post(ROTA_PACIENTE, json={**factories.cadastro(), **alteracao})

        assert resposta.status_code == 422
        assert db.query(Usuario).count() == 0

    @pytest.mark.parametrize("campo", ["nome", "email", "senha"])
    def test_campos_obrigatorios(self, client: TestClient, campo: str) -> None:
        corpo = factories.cadastro()
        del corpo[campo]

        assert client.post(ROTA_PACIENTE, json=corpo).status_code == 422


class TestCadastroNutricionista:
    def test_cria_usuario_e_nutricionista(self, client: TestClient, db: Session) -> None:
        corpo = _cadastrar_nutri(client, crn="crn-3   12345")

        usuario = corpo["usuario"]
        assert usuario["perfil"] == "nutricionista"
        assert usuario["crn"] == "CRN-3 12345"

        nutricionista = db.get(Nutricionista, usuario["id"])
        assert nutricionista is not None
        assert db.get(Paciente, usuario["id"]) is None, "nutricionista nao vira paciente"

    def test_exige_crn(self, client: TestClient) -> None:
        resposta = client.post(ROTA_NUTRI, json=factories.cadastro(email="nutri@exemplo.com"))

        assert resposta.status_code == 422

    def test_crn_duplicado_da_409(self, client: TestClient, db: Session) -> None:
        _cadastrar_nutri(client)

        resposta = client.post(
            ROTA_NUTRI, json=factories.cadastro(email="outra@exemplo.com", crn="CRN-3 12345")
        )

        assert resposta.status_code == 409
        assert resposta.json()["detail"] == "CRN ja cadastrado"
        assert db.query(Usuario).count() == 1

    def test_email_de_paciente_nao_pode_ser_reusado(self, client: TestClient) -> None:
        _cadastrar_paciente(client, email="ana@exemplo.com")

        resposta = client.post(
            ROTA_NUTRI, json=factories.cadastro(email="ana@exemplo.com", crn="CRN-1 999")
        )

        assert resposta.status_code == 409


class TestLogin:
    def test_login_devolve_token_e_usuario(self, client: TestClient) -> None:
        cadastro = _cadastrar_paciente(client)

        resposta = client.post(
            ROTA_LOGIN, json={"email": "ana@exemplo.com", "senha": factories.SENHA_PADRAO}
        )

        assert resposta.status_code == 200, resposta.text
        corpo = resposta.json()
        assert corpo["access_token"]
        assert corpo["usuario"]["id"] == cadastro["usuario"]["id"]

    def test_login_de_nutricionista_traz_crn(self, client: TestClient) -> None:
        _cadastrar_nutri(client)

        corpo = client.post(
            ROTA_LOGIN, json={"email": "nutri@exemplo.com", "senha": factories.SENHA_PADRAO}
        ).json()

        assert corpo["usuario"]["perfil"] == "nutricionista"
        assert corpo["usuario"]["crn"] == "CRN-3 12345"

    def test_email_ignora_maiusculas(self, client: TestClient) -> None:
        _cadastrar_paciente(client)

        resposta = client.post(
            ROTA_LOGIN, json={"email": "ANA@exemplo.com", "senha": factories.SENHA_PADRAO}
        )

        assert resposta.status_code == 200

    @pytest.mark.parametrize(
        ("email", "senha"),
        [
            ("ana@exemplo.com", "senha-errada"),
            ("ninguem@exemplo.com", factories.SENHA_PADRAO),
        ],
    )
    def test_credenciais_invalidas_dao_401_sem_dizer_qual(
        self, client: TestClient, email: str, senha: str
    ) -> None:
        _cadastrar_paciente(client)

        resposta = client.post(ROTA_LOGIN, json={"email": email, "senha": senha})

        assert resposta.status_code == 401
        assert resposta.json()["detail"] == "Email ou senha invalidos"


class TestMe:
    def test_devolve_o_usuario_do_token(self, client: TestClient) -> None:
        cadastro = _cadastrar_paciente(client)

        resposta = client.get(ROTA_ME, headers=_auth(cadastro["access_token"]))

        assert resposta.status_code == 200
        assert resposta.json() == cadastro["usuario"]

    def test_sem_token_da_401(self, client: TestClient) -> None:
        resposta = client.get(ROTA_ME)

        assert resposta.status_code == 401
        assert resposta.headers["www-authenticate"] == "Bearer"

    def test_token_invalido_da_401(self, client: TestClient) -> None:
        assert client.get(ROTA_ME, headers=_auth("nao.e.jwt")).status_code == 401

    def test_token_com_outra_chave_da_401(self, client: TestClient) -> None:
        cadastro = _cadastrar_paciente(client)
        forjado = jwt.encode(
            {"sub": str(cadastro["usuario"]["id"]), "exp": datetime.now(UTC) + timedelta(days=1)},
            "outra-chave",
            algorithm="HS256",
        )

        assert client.get(ROTA_ME, headers=_auth(forjado)).status_code == 401

    def test_token_expirado_da_401(self, client: TestClient, monkeypatch) -> None:
        cadastro = _cadastrar_paciente(client)
        monkeypatch.setattr(get_settings(), "ACCESS_TOKEN_EXPIRE_MINUTES", -1)
        token, _ = criar_token_acesso(cadastro["usuario"]["id"], "paciente")

        assert client.get(ROTA_ME, headers=_auth(token)).status_code == 401

    def test_token_de_usuario_removido_da_401(self, client: TestClient, db: Session) -> None:
        cadastro = _cadastrar_paciente(client)
        db.delete(db.get(Usuario, cadastro["usuario"]["id"]))
        db.commit()

        assert client.get(ROTA_ME, headers=_auth(cadastro["access_token"])).status_code == 401


class TestFluxoCompleto:
    def test_cadastro_triagem_e_refeicao(self, client: TestClient) -> None:
        """O paciente cadastrado ja pode fazer a triagem e registrar refeicoes."""
        paciente_id = _cadastrar_paciente(client)["usuario"]["id"]

        triagem = client.post(
            f"/api/v1/pacientes/{paciente_id}/triagem",
            json={
                "peso_kg": 80,
                "altura_cm": 180,
                "idade": 30,
                "genero": "masculino",
                "nivel_atividade": "moderado",
            },
        )
        refeicao = client.post("/api/v1/refeicoes", json=factories.refeicao(paciente_id))

        assert triagem.status_code == 200, triagem.text
        assert refeicao.status_code == 201, refeicao.text
