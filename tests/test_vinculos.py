"""Testes do mecanismo de vinculacao (Task 1.4)."""

from datetime import UTC, datetime, timedelta

import jwt
import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from alembic.config import Config
from alembic.script import ScriptDirectory
from app.core.config import get_settings
from app.core.security import criar_token_acesso
from app.models.paciente import Paciente
from app.models.usuario import Nutricionista, Usuario
from app.models.vinculo import CodigoVinculacao, StatusCodigoVinculacao, Vinculo
from app.services.vinculos import (
    CodigoVinculacaoJaUtilizado,
    _hash_codigo,
    resgatar_codigo_vinculacao,
)
from tests import factories

ROTA_CODIGO = "/api/v1/linking-code"
ROTA_VINCULO = "/api/v1/link"


# Usuarios fixos dos testes: 10 e nutricionista, 11 e 12 sao pacientes.
NUTRI, JOAO, MARIA = 10, 11, 12


def _criar_usuarios(db: Session) -> None:
    factories.criar_nutricionista(db, NUTRI, nome="Dra. Ana")
    factories.criar_paciente(db, JOAO)
    factories.criar_paciente(db, MARIA)


@pytest.fixture
def usuarios(db: Session) -> None:
    _criar_usuarios(db)


def _headers(usuario_id: int, perfil: str) -> dict[str, str]:
    token, _ = criar_token_acesso(usuario_id, perfil)
    return {"Authorization": f"Bearer {token}"}


def _token_com(payload: dict, segredo: str | None = None) -> dict[str, str]:
    settings = get_settings()
    token = jwt.encode(payload, segredo or settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return {"Authorization": f"Bearer {token}"}


def _gerar_codigo(client: TestClient) -> str:
    resposta = client.post(ROTA_CODIGO, headers=_headers(NUTRI, "nutricionista"))
    assert resposta.status_code == 200, resposta.text
    return resposta.json()["codigo"]


@pytest.mark.usefixtures("usuarios")
class TestGeracaoCodigo:
    def test_nutricionista_consegue_gerar_codigo(self, client: TestClient) -> None:
        resposta = client.post(
            ROTA_CODIGO,
            headers=_headers(NUTRI, "nutricionista"),
        )

        assert resposta.status_code == 200, resposta.text
        corpo = resposta.json()
        assert corpo["codigo"].isdigit()
        assert len(corpo["codigo"]) == 6
        assert corpo["status"] == "ativo"

    def test_paciente_nao_consegue_gerar_codigo(self, client: TestClient) -> None:
        resposta = client.post(ROTA_CODIGO, headers=_headers(JOAO, "paciente"))

        assert resposta.status_code == 403

    def test_codigo_tem_seis_digitos(self, client: TestClient) -> None:
        codigo = _gerar_codigo(client)

        assert codigo.isdigit()
        assert len(codigo) == 6


@pytest.mark.usefixtures("usuarios")
class TestResgateCodigo:
    def test_paciente_consegue_resgatar_codigo_valido(
        self, client: TestClient, db: Session
    ) -> None:
        codigo = _gerar_codigo(client)

        resposta = client.post(
            ROTA_VINCULO,
            json={"codigo": codigo},
            headers=_headers(JOAO, "paciente"),
        )

        assert resposta.status_code == 200, resposta.text
        corpo = resposta.json()
        assert corpo["nutricionista"]["nome"] == "Dra. Ana"
        assert corpo["nutricionista"]["id"] == NUTRI
        assert corpo["nutricionista"]["foto_url"] is None

        db.expire_all()
        assert db.query(Vinculo).count() == 1

    def test_codigo_invalido_retorna_erro(self, client: TestClient) -> None:
        resposta = client.post(
            ROTA_VINCULO,
            json={"codigo": "123456"},
            headers=_headers(JOAO, "paciente"),
        )

        assert resposta.status_code == 404

    def test_codigo_expirado_retorna_erro(self, client: TestClient, db: Session) -> None:
        codigo = "654321"
        db.add(
            CodigoVinculacao(
                nutricionista_id=10,
                nutricionista_nome="Dra. Ana",
                nutricionista_foto_url=None,
                codigo_hash=_hash_codigo(codigo),
                status=StatusCodigoVinculacao.ATIVO.value,
                expira_em=datetime.now(UTC) - timedelta(minutes=1),
            )
        )
        db.commit()

        resposta = client.post(
            ROTA_VINCULO,
            json={"codigo": codigo},
            headers=_headers(JOAO, "paciente"),
        )

        assert resposta.status_code == 410

    def test_codigo_ja_utilizado_retorna_erro(self, client: TestClient) -> None:
        codigo = _gerar_codigo(client)
        resposta_1 = client.post(
            ROTA_VINCULO,
            json={"codigo": codigo},
            headers=_headers(JOAO, "paciente"),
        )
        assert resposta_1.status_code == 200

        resposta_2 = client.post(
            ROTA_VINCULO,
            json={"codigo": codigo},
            headers=_headers(MARIA, "paciente"),
        )

        assert resposta_2.status_code == 409

    def test_nutricionista_nao_consegue_resgatar_codigo_de_vinculacao(
        self, client: TestClient
    ) -> None:
        codigo = _gerar_codigo(client)

        resposta = client.post(
            ROTA_VINCULO,
            json={"codigo": codigo},
            headers=_headers(NUTRI, "nutricionista"),
        )

        assert resposta.status_code == 403

    def test_vinculo_duplicado_e_tratado_de_forma_idempotente(
        self, client: TestClient, db: Session
    ) -> None:
        codigo_1 = _gerar_codigo(client)
        resposta_1 = client.post(
            ROTA_VINCULO,
            json={"codigo": codigo_1},
            headers=_headers(JOAO, "paciente"),
        )
        assert resposta_1.status_code == 200

        codigo_2 = _gerar_codigo(client)
        resposta_2 = client.post(
            ROTA_VINCULO,
            json={"codigo": codigo_2},
            headers=_headers(JOAO, "paciente"),
        )

        assert resposta_2.status_code == 200
        db.expire_all()
        assert (
            db.query(Vinculo)
            .filter(Vinculo.nutricionista_id == 10, Vinculo.paciente_id == 11)
            .count()
            == 1
        )

    def test_resposta_nao_expoe_dados_sensiveis(self, client: TestClient) -> None:
        codigo = _gerar_codigo(client)
        resposta = client.post(
            ROTA_VINCULO,
            json={"codigo": codigo},
            headers=_headers(JOAO, "paciente"),
        )

        assert resposta.status_code == 200
        corpo = resposta.json()
        assert "hash" not in corpo
        assert "token" not in corpo
        assert "senha" not in resposta.text.lower()


# Sem a fixture `usuarios`: este teste usa sessoes proprias do engine e commita
# de verdade, entao cria e apaga os proprios dados.
class TestConcorrencia:
    def test_duas_tentativas_simultaneas_nao_criam_vinculos_inconsistentes(
        self, engine, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Simula a corrida de forma deterministica, sem threads.

        O engine de teste (SQLite em memoria + StaticPool) usa uma unica
        conexao, entao threads de verdade se atrapalhariam e o resultado
        mudaria a cada execucao. Aqui o segundo paciente le o codigo ainda
        ATIVO, o primeiro o resgata, e so entao o segundo tenta resgatar: o
        UPDATE condicional atomico precisa barrar a segunda tentativa.
        """
        codigo = "777777"
        SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

        sessao_inicial = SessionLocal()
        _criar_usuarios(sessao_inicial)
        sessao_inicial.add(
            CodigoVinculacao(
                nutricionista_id=10,
                nutricionista_nome="Dra. Ana",
                nutricionista_foto_url=None,
                codigo_hash=_hash_codigo(codigo),
                status=StatusCodigoVinculacao.ATIVO.value,
                expira_em=datetime.now(UTC) + timedelta(minutes=30),
            )
        )
        sessao_inicial.commit()
        sessao_inicial.close()

        sessao_a = SessionLocal()
        sessao_b = SessionLocal()
        try:
            # B le o codigo antes de A resgatar: B enxerga o registro como ATIVO.
            registro_desatualizado = (
                sessao_b.query(CodigoVinculacao)
                .filter(CodigoVinculacao.codigo_hash == _hash_codigo(codigo))
                .one()
            )
            assert registro_desatualizado.status == StatusCodigoVinculacao.ATIVO.value

            resultado_a = resgatar_codigo_vinculacao(
                sessao_a,
                sessao_a.get(Usuario, JOAO),
                codigo,
            )
            assert resultado_a.nutricionista_id == 10

            # Forca B a trabalhar com a leitura antiga, como numa corrida real.
            monkeypatch.setattr(
                "app.services.vinculos._buscar_codigo_ativo",
                lambda db, codigo_informado: registro_desatualizado,
            )
            with pytest.raises(CodigoVinculacaoJaUtilizado):
                resgatar_codigo_vinculacao(
                    sessao_b,
                    sessao_b.get(Usuario, MARIA),
                    codigo,
                )

            vinculos = (
                sessao_a.query(Vinculo)
                .filter(
                    Vinculo.nutricionista_id == 10,
                    Vinculo.paciente_id.in_([11, 12]),
                )
                .all()
            )
            assert [v.paciente_id for v in vinculos] == [11]
        finally:
            sessao_a.close()
            sessao_b.close()
            # Esses dados foram commitados fora da transacao isolada dos testes.
            limpeza = SessionLocal()
            limpeza.query(Vinculo).filter(Vinculo.nutricionista_id == 10).delete()
            limpeza.query(CodigoVinculacao).filter(
                CodigoVinculacao.codigo_hash == _hash_codigo(codigo)
            ).delete()
            ids = [NUTRI, JOAO, MARIA]
            limpeza.query(Paciente).filter(Paciente.id.in_(ids)).delete()
            limpeza.query(Nutricionista).filter(Nutricionista.id.in_(ids)).delete()
            limpeza.query(Usuario).filter(Usuario.id.in_(ids)).delete()
            limpeza.commit()
            limpeza.close()


@pytest.mark.usefixtures("usuarios")
class TestValidacaoJWT:
    def test_requisicao_sem_token_retorna_401(self, client: TestClient) -> None:
        resposta = client.post(ROTA_CODIGO)
        assert resposta.status_code == 401
        assert resposta.headers["www-authenticate"] == "Bearer"

    def test_token_malformado_retorna_401(self, client: TestClient) -> None:
        resposta = client.post(ROTA_CODIGO, headers={"Authorization": "Bearer nao-e-jwt"})
        assert resposta.status_code == 401
        assert resposta.headers["www-authenticate"] == "Bearer"

    def test_token_com_assinatura_invalida_retorna_401(self, client: TestClient) -> None:
        headers = _token_com(
            {"sub": str(NUTRI), "exp": datetime.now(UTC) + timedelta(days=1)},
            segredo="chave-invalida",
        )
        resposta = client.post(ROTA_CODIGO, headers=headers)
        assert resposta.status_code == 401

    def test_token_expirado_retorna_401(self, client: TestClient) -> None:
        headers = _token_com({"sub": str(NUTRI), "exp": datetime.now(UTC) - timedelta(minutes=5)})
        resposta = client.post(ROTA_CODIGO, headers=headers)
        assert resposta.status_code == 401

    def test_token_sem_sub_retorna_401(self, client: TestClient) -> None:
        headers = _token_com({"exp": datetime.now(UTC) + timedelta(hours=1)})
        resposta = client.post(ROTA_CODIGO, headers=headers)
        assert resposta.status_code == 401

    def test_token_com_sub_nao_numerico_retorna_401(self, client: TestClient) -> None:
        headers = _token_com({"sub": "nao-e-numero", "exp": datetime.now(UTC) + timedelta(hours=1)})
        resposta = client.post(ROTA_CODIGO, headers=headers)
        assert resposta.status_code == 401

    def test_token_de_usuario_inexistente_retorna_401(self, client: TestClient) -> None:
        resposta = client.post(ROTA_CODIGO, headers=_headers(999, "nutricionista"))
        assert resposta.status_code == 401

    def test_perfil_vem_do_banco_e_nao_do_token(self, client: TestClient) -> None:
        """Um paciente com `perfil` adulterado no token continua sendo paciente."""
        resposta = client.post(ROTA_CODIGO, headers=_headers(JOAO, "nutricionista"))
        assert resposta.status_code == 403

    def test_nome_do_nutricionista_vem_do_cadastro(self, client: TestClient) -> None:
        codigo = _gerar_codigo(client)
        resposta = client.post(
            ROTA_VINCULO, json={"codigo": codigo}, headers=_headers(JOAO, "paciente")
        )
        assert resposta.status_code == 200
        assert resposta.json()["nutricionista"]["nome"] == "Dra. Ana"


class TestIntegridadeReferencial:
    def test_foreign_keys_rejeitam_ids_inexistentes(self, engine) -> None:
        with engine.connect() as conn:
            conn.execute(sa.text("PRAGMA foreign_keys = ON"))
            with pytest.raises(IntegrityError):
                conn.execute(
                    sa.text(
                        "INSERT INTO vinculos (nutricionista_id, paciente_id) " "VALUES (999, 888)"
                    )
                )


class TestMigrationAlembic:
    def test_historico_alembic_possui_head_unica(self) -> None:
        config = Config("alembic.ini")
        script = ScriptDirectory.from_config(config)
        heads = script.get_heads()
        assert len(heads) == 1, f"Esperava head unica, mas foram encontradas: {heads}"
        assert heads[0] == "95a3f50655d5"
