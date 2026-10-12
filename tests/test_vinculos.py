"""Testes do mecanismo de vinculacao (Task 1.4)."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
import jwt
import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.security import Perfil, UsuarioAutenticado, create_access_token
from app.models.paciente import Paciente
from app.models.usuario import Nutricionista, Usuario
from app.models.vinculo import CodigoVinculacao, StatusCodigoVinculacao, Vinculo
from app.services.vinculos import _hash_codigo, resgatar_codigo_vinculacao

ROTA_CODIGO = "/api/v1/linking-code"
ROTA_VINCULO = "/api/v1/link"


def _headers(
    usuario_id: int, perfil: str, nome: str, foto_url: str | None = None
) -> dict[str, str]:
    token = create_access_token(
        {"sub": usuario_id, "perfil": perfil, "nome": nome, "foto_url": foto_url},
        expires_delta=timedelta(minutes=30),
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def _seed_usuarios(db: Session) -> None:
    """Garante a presenca dos usuarios padrao nos testes para integridade de FKs."""
    if db.get(Usuario, 10) is None:
        db.add(
            Usuario(
                id=10,
                nome="Dra. Ana",
                email="ana@exemplo.com",
                senha_hash="hash-bcrypt-10",
                perfil=Perfil.NUTRICIONISTA.value,
            )
        )
        db.flush()
        db.add(Nutricionista(id=10, crn="CRN-3 12345"))

    if db.get(Usuario, 11) is None:
        db.add(
            Usuario(
                id=11,
                nome="Joao",
                email="joao@exemplo.com",
                senha_hash="hash-bcrypt-11",
                perfil=Perfil.PACIENTE.value,
            )
        )
        db.flush()
        db.add(Paciente(id=11))
        # Adiciona tambem como nutricionista para viabilizar teste de proprio codigo com FK
        db.add(Nutricionista(id=11, crn="CRN-3 99999"))

    if db.get(Usuario, 12) is None:
        db.add(
            Usuario(
                id=12,
                nome="Maria",
                email="maria@exemplo.com",
                senha_hash="hash-bcrypt-12",
                perfil=Perfil.PACIENTE.value,
            )
        )
        db.flush()
        db.add(Paciente(id=12))

    db.commit()


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
    def test_paciente_consegue_resgatar_codigo_valido(
        self, client: TestClient, db: Session
    ) -> None:
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

    def test_nutricionista_nao_consegue_resgatar_codigo_de_vinculacao(
        self, client: TestClient
    ) -> None:
        codigo = _gerar_codigo(client)

        resposta = client.post(
            ROTA_VINCULO,
            json={"codigo": codigo},
            headers=_headers(10, "nutricionista", "Dra. Ana", "https://img.example/ana.png"),
        )

        assert resposta.status_code == 403

    def test_paciente_nao_pode_utilizar_o_proprio_codigo(
        self, client: TestClient, db: Session
    ) -> None:
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

    def test_vinculo_duplicado_e_tratado_de_forma_idempotente(
        self, client: TestClient, db: Session
    ) -> None:
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
        if sessao_inicial.get(Usuario, 10) is None:
            sessao_inicial.add(
                Usuario(
                    id=10,
                    nome="Dra. Ana",
                    email="ana@exemplo.com",
                    senha_hash="hash",
                    perfil=Perfil.NUTRICIONISTA.value,
                )
            )
            sessao_inicial.flush()
            sessao_inicial.add(Nutricionista(id=10, crn="CRN-3 12345"))
        if sessao_inicial.get(Usuario, 11) is None:
            sessao_inicial.add(
                Usuario(
                    id=11,
                    nome="Joao",
                    email="joao@exemplo.com",
                    senha_hash="hash",
                    perfil=Perfil.PACIENTE.value,
                )
            )
            sessao_inicial.flush()
            sessao_inicial.add(Paciente(id=11))
        if sessao_inicial.get(Usuario, 12) is None:
            sessao_inicial.add(
                Usuario(
                    id=12,
                    nome="Maria",
                    email="maria@exemplo.com",
                    senha_hash="hash",
                    perfil=Perfil.PACIENTE.value,
                )
            )
            sessao_inicial.flush()
            sessao_inicial.add(Paciente(id=12))

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
                    UsuarioAutenticado(id=paciente_id, perfil=Perfil.PACIENTE, nome="Joao"),
                    codigo,
                )
                return f"ok:{resultado.nutricionista_id}"
            except Exception as exc:  # noqa: BLE001 - teste verifica resultado agregado
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
        forjado = jwt.encode(
            {"sub": "10", "perfil": "nutricionista", "exp": datetime.now(UTC) + timedelta(days=1)},
            "chave-invalida",
            algorithm="HS256",
        )
        resposta = client.post(ROTA_CODIGO, headers={"Authorization": f"Bearer {forjado}"})
        assert resposta.status_code == 401

    def test_token_expirado_retorna_401(self, client: TestClient) -> None:
        expirado = create_access_token(
            {"sub": 10, "perfil": "nutricionista", "nome": "Dra. Ana"},
            expires_delta=timedelta(minutes=-5),
        )
        resposta = client.post(ROTA_CODIGO, headers={"Authorization": f"Bearer {expirado}"})
        assert resposta.status_code == 401

    def test_token_sem_sub_retorna_401(self, client: TestClient) -> None:
        settings = get_settings()
        sem_sub = jwt.encode(
            {
                "perfil": "nutricionista",
                "nome": "Dra. Ana",
                "exp": datetime.now(UTC) + timedelta(hours=1),
            },
            settings.SECRET_KEY,
            algorithm=settings.ALGORITHM,
        )
        resposta = client.post(ROTA_CODIGO, headers={"Authorization": f"Bearer {sem_sub}"})
        assert resposta.status_code == 401

    def test_token_com_sub_nao_numerico_retorna_401(self, client: TestClient) -> None:
        sub_invalido = create_access_token(
            {"sub": "nao-e-numero", "perfil": "nutricionista", "nome": "Dra. Ana"},
            expires_delta=timedelta(hours=1),
        )
        resposta = client.post(ROTA_CODIGO, headers={"Authorization": f"Bearer {sub_invalido}"})
        assert resposta.status_code == 401

    def test_token_sem_perfil_retorna_401(self, client: TestClient) -> None:
        settings = get_settings()
        sem_perfil = jwt.encode(
            {"sub": "10", "nome": "Dra. Ana", "exp": datetime.now(UTC) + timedelta(hours=1)},
            settings.SECRET_KEY,
            algorithm=settings.ALGORITHM,
        )
        resposta = client.post(ROTA_CODIGO, headers={"Authorization": f"Bearer {sem_perfil}"})
        assert resposta.status_code == 401

    def test_token_com_perfil_desconhecido_retorna_401(self, client: TestClient) -> None:
        perfil_estranho = create_access_token(
            {"sub": 10, "perfil": "administrador", "nome": "Admin"},
            expires_delta=timedelta(hours=1),
        )
        resposta = client.post(ROTA_CODIGO, headers={"Authorization": f"Bearer {perfil_estranho}"})
        assert resposta.status_code == 401

    def test_token_de_usuario_inexistente_retorna_401(self, client: TestClient) -> None:
        token_inexistente = create_access_token(
            {"sub": 9999, "perfil": "nutricionista", "nome": "Fantasma"},
            expires_delta=timedelta(hours=1),
        )
        resposta = client.post(
            ROTA_CODIGO, headers={"Authorization": f"Bearer {token_inexistente}"}
        )
        assert resposta.status_code == 401

    def test_token_sem_nome_utiliza_nome_do_banco(self, client: TestClient) -> None:
        """Tokens emitidos pelo login/cadastro da Task 1.2 (sem nome) sao aceitos."""
        settings = get_settings()
        token_sem_nome = jwt.encode(
            {
                "sub": "10",
                "perfil": "nutricionista",
                "exp": datetime.now(UTC) + timedelta(hours=1),
            },
            settings.SECRET_KEY,
            algorithm=settings.ALGORITHM,
        )
        resposta = client.post(
            ROTA_CODIGO, headers={"Authorization": f"Bearer {token_sem_nome}"}
        )
        assert resposta.status_code == 200


class TestIntegridadeReferencial:
    def test_vinculo_com_nutricionista_inexistente_falha(self, db: Session) -> None:
        vinculo = Vinculo(nutricionista_id=999, paciente_id=11)
        db.add(vinculo)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

    def test_vinculo_com_paciente_inexistente_falha(self, db: Session) -> None:
        vinculo = Vinculo(nutricionista_id=10, paciente_id=999)
        db.add(vinculo)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

    def test_codigo_vinculacao_com_nutricionista_inexistente_falha(self, db: Session) -> None:
        codigo = CodigoVinculacao(
            nutricionista_id=999,
            nutricionista_nome="Inexistente",
            nutricionista_foto_url=None,
            codigo_hash=_hash_codigo("999999"),
            status=StatusCodigoVinculacao.ATIVO.value,
            expira_em=datetime.now(UTC) + timedelta(minutes=30),
        )
        db.add(codigo)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

    def test_remocao_de_nutricionista_propaga_em_cascata(self, db: Session) -> None:
        u = Usuario(
            id=50,
            nome="Nutri Temp",
            email="temp50@exemplo.com",
            senha_hash="hash",
            perfil=Perfil.NUTRICIONISTA.value,
        )
        db.add(u)
        db.flush()
        nutri = Nutricionista(id=50, crn="CRN-50")
        db.add(nutri)
        cod = CodigoVinculacao(
            nutricionista_id=50,
            nutricionista_nome="Nutri Temp",
            nutricionista_foto_url=None,
            codigo_hash=_hash_codigo("505050"),
            status=StatusCodigoVinculacao.ATIVO.value,
            expira_em=datetime.now(UTC) + timedelta(minutes=30),
        )
        db.add(cod)
        vinc = Vinculo(nutricionista_id=50, paciente_id=11)
        db.add(vinc)
        db.commit()

        db.delete(nutri)
        db.commit()

        assert (
            db.query(CodigoVinculacao).filter(CodigoVinculacao.nutricionista_id == 50).count() == 0
        )
        assert db.query(Vinculo).filter(Vinculo.nutricionista_id == 50).count() == 0


class TestMigrationAlembic:
    def test_historico_alembic_possui_head_unica(self) -> None:
        config = Config("alembic.ini")
        script = ScriptDirectory.from_config(config)
        heads = script.get_heads()
        assert len(heads) == 1, f"Esperava head unica, mas foram encontradas: {heads}"
        assert heads[0] == "a1b2c3d4e5f6"
