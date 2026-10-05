from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.core.security import PerfilUsuario, UsuarioAutenticado, create_access_token
from app.models.vinculo import CodigoVinculacao, StatusCodigoVinculacao, Vinculo
from app.services.vinculos import _hash_codigo, resgatar_codigo_vinculacao

ROTA_CODIGO = "/api/v1/linking-code"
ROTA_VINCULO = "/api/v1/link"


def _headers(usuario_id: int, perfil: str, nome: str, foto_url: str | None = None) -> dict[str, str]:
    token = create_access_token(
        {"sub": usuario_id, "perfil": perfil, "nome": nome, "foto_url": foto_url},
        expires_delta=timedelta(minutes=30),
    )
    return {"Authorization": f"Bearer {token}"}


def _gerar_codigo(client: TestClient) -> str:
    resposta = client.post(
        ROTA_CODIGO,
        headers=_headers(10, "nutricionista", "Dra. Ana", "https://img.example/ana.png"),
    )
    assert resposta.status_code == 200, resposta.text
    return resposta.json()["codigo"]


class TestGeracaoCodigo:
    def test_nutricionista_consegue_gerar_codigo(self, client: TestClient) -> None:
        resposta = client.post(
            ROTA_CODIGO,
            headers=_headers(10, "nutricionista", "Dra. Ana", "https://img.example/ana.png"),
        )

        assert resposta.status_code == 200, resposta.text
        corpo = resposta.json()
        assert corpo["codigo"].isdigit()
        assert len(corpo["codigo"]) == 6
        assert corpo["status"] == "ativo"

    def test_paciente_nao_consegue_gerar_codigo(self, client: TestClient) -> None:
        resposta = client.post(ROTA_CODIGO, headers=_headers(11, "paciente", "Joao"))

        assert resposta.status_code == 403

    def test_codigo_tem_seis_digitos(self, client: TestClient) -> None:
        codigo = _gerar_codigo(client)

        assert codigo.isdigit()
        assert len(codigo) == 6


class TestResgateCodigo:
    def test_paciente_consegue_resgatar_codigo_valido(self, client: TestClient, db) -> None:
        codigo = _gerar_codigo(client)

        resposta = client.post(
            ROTA_VINCULO,
            json={"codigo": codigo},
            headers=_headers(11, "paciente", "Joao"),
        )

        assert resposta.status_code == 200, resposta.text
        corpo = resposta.json()
        assert corpo["nutricionista"]["nome"] == "Dra. Ana"
        assert corpo["nutricionista"]["foto_url"] == "https://img.example/ana.png"

        db.expire_all()
        assert db.query(Vinculo).count() == 1

    def test_codigo_invalido_retorna_erro(self, client: TestClient) -> None:
        resposta = client.post(
            ROTA_VINCULO,
            json={"codigo": "123456"},
            headers=_headers(11, "paciente", "Joao"),
        )

        assert resposta.status_code == 404

    def test_codigo_expirado_retorna_erro(self, client: TestClient, db) -> None:
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
            headers=_headers(11, "paciente", "Joao"),
        )

        assert resposta.status_code == 410

    def test_codigo_ja_utilizado_retorna_erro(self, client: TestClient) -> None:
        codigo = _gerar_codigo(client)
        resposta_1 = client.post(
            ROTA_VINCULO,
            json={"codigo": codigo},
            headers=_headers(11, "paciente", "Joao"),
        )
        assert resposta_1.status_code == 200

        resposta_2 = client.post(
            ROTA_VINCULO,
            json={"codigo": codigo},
            headers=_headers(12, "paciente", "Maria"),
        )

        assert resposta_2.status_code == 409

    def test_nutricionista_nao_consegue_resgatar_codigo_de_vinculacao(self, client: TestClient) -> None:
        codigo = _gerar_codigo(client)

        resposta = client.post(
            ROTA_VINCULO,
            json={"codigo": codigo},
            headers=_headers(10, "nutricionista", "Dra. Ana", "https://img.example/ana.png"),
        )

        assert resposta.status_code == 403

    def test_paciente_nao_pode_utilizar_o_proprio_codigo(self, client: TestClient, db) -> None:
        codigo = "222222"
        db.add(
            CodigoVinculacao(
                nutricionista_id=11,
                nutricionista_nome="Joao",
                nutricionista_foto_url=None,
                codigo_hash=_hash_codigo(codigo),
                status=StatusCodigoVinculacao.ATIVO.value,
                expira_em=datetime.now(UTC) + timedelta(minutes=30),
            )
        )
        db.commit()

        resposta = client.post(
            ROTA_VINCULO,
            json={"codigo": codigo},
            headers=_headers(11, "paciente", "Joao"),
        )

        assert resposta.status_code == 403

    def test_vinculo_duplicado_e_tratado_de_forma_idempotente(self, client: TestClient, db) -> None:
        codigo_1 = _gerar_codigo(client)
        resposta_1 = client.post(
            ROTA_VINCULO,
            json={"codigo": codigo_1},
            headers=_headers(11, "paciente", "Joao"),
        )
        assert resposta_1.status_code == 200

        codigo_2 = _gerar_codigo(client)
        resposta_2 = client.post(
            ROTA_VINCULO,
            json={"codigo": codigo_2},
            headers=_headers(11, "paciente", "Joao"),
        )

        assert resposta_2.status_code == 200
        db.expire_all()
        assert db.query(Vinculo).filter(Vinculo.nutricionista_id == 10, Vinculo.paciente_id == 11).count() == 1

    def test_resposta_nao_expoe_dados_sensiveis(self, client: TestClient) -> None:
        codigo = _gerar_codigo(client)
        resposta = client.post(
            ROTA_VINCULO,
            json={"codigo": codigo},
            headers=_headers(11, "paciente", "Joao"),
        )

        assert resposta.status_code == 200
        corpo = resposta.json()
        assert "hash" not in corpo
        assert "token" not in corpo
        assert "senha" not in resposta.text.lower()

    def test_duas_tentativas_simultaneas_nao_criam_vinculos_inconsistentes(self, engine) -> None:
        codigo = "777777"
        SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

        sessao_inicial = SessionLocal()
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

        def _resgatar(paciente_id: int) -> str:
            sessao = SessionLocal()
            try:
                resultado = resgatar_codigo_vinculacao(
                    sessao,
                    UsuarioAutenticado(id=paciente_id, perfil=PerfilUsuario.PACIENTE, nome="Joao"),
                    codigo,
                )
                return f"ok:{resultado.nutricionista_id}"
            except Exception as exc:  # noqa: BLE001 - o teste só precisa do resultado agregado
                return exc.__class__.__name__
            finally:
                sessao.close()

        with ThreadPoolExecutor(max_workers=2) as executor:
            resultados = list(executor.map(_resgatar, [11, 12]))

        assert resultados.count("ok:10") == 1
        sessao_verificacao = SessionLocal()
        try:
            assert sessao_verificacao.query(Vinculo).count() == 1
        finally:
            sessao_verificacao.close()
