"""Testes da criptografia de dados de saude em repouso (Task 1.6, RNF06).

Confere o que de fato vai para o banco (consulta SQL crua), nao o que o ORM devolve.
"""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core import crypto
from app.core.config import get_settings
from app.models.paciente import Paciente
from app.models.refeicao import Refeicao
from tests import factories

PREFIXO_FERNET = "gAAAA"


@pytest.fixture(autouse=True)
def _paciente(db: Session) -> None:
    factories.criar_paciente(db, 1)


def _crus(db: Session, sql: str) -> tuple:
    return tuple(db.execute(text(sql)).one())


def _triagem(client: TestClient) -> None:
    resposta = client.post(
        "/api/v1/pacientes/1/triagem",
        json={
            "peso_kg": "80.50",
            "altura_cm": "180",
            "idade": 30,
            "genero": "masculino",
            "nivel_atividade": "moderado",
        },
        headers=factories.headers_de(1),
    )
    assert resposta.status_code == 200, resposta.text


class TestTriagemCifrada:
    def test_banco_guarda_texto_cifrado(self, client: TestClient, db: Session) -> None:
        _triagem(client)

        crus = _crus(db, "SELECT peso_kg, altura_cm, idade, genero, nivel_atividade FROM pacientes")

        assert all(valor.startswith(PREFIXO_FERNET) for valor in crus)
        texto = " ".join(crus)
        assert "80.5" not in texto
        assert "masculino" not in texto
        assert "moderado" not in texto

    def test_orm_devolve_os_valores_originais(self, client: TestClient, db: Session) -> None:
        _triagem(client)

        db.expire_all()
        paciente = db.get(Paciente, 1)
        assert paciente is not None
        assert paciente.peso_kg == Decimal("80.50")
        assert paciente.altura_cm == Decimal("180.00")
        assert paciente.idade == 30
        assert paciente.genero == "masculino"
        assert paciente.nivel_atividade == "moderado"

    def test_meta_calorica_continua_em_claro(self, client: TestClient, db: Session) -> None:
        # Nao e dado de triagem: e o teto calculado, usado em regras (gamificacao).
        _triagem(client)

        # TMB = 66.47 + 13.75*80.5 + 5.003*180 - 6.755*30 = 1871.23 ; x 1.55 = 2900.42
        (meta,) = _crus(db, "SELECT meta_kcal FROM pacientes")
        assert Decimal(str(meta)) == Decimal("2900.42")

    def test_campos_vazios_ficam_nulos(self, db: Session) -> None:
        crus = _crus(db, "SELECT peso_kg, genero FROM pacientes")

        assert crus == (None, None)


class TestObservacaoCifrada:
    def test_observacao_vai_cifrada_e_volta_igual(self, client: TestClient, db: Session) -> None:
        resposta = client.post(
            "/api/v1/refeicoes",
            json=factories.refeicao(1, observacao="Dor de estomago depois do almoco"),
            headers=factories.headers_de(1),
        )
        assert resposta.status_code == 201, resposta.text
        assert resposta.json()["observacao"] == "Dor de estomago depois do almoco"

        (cru,) = _crus(db, "SELECT observacao FROM refeicoes")
        assert cru.startswith(PREFIXO_FERNET)
        assert "estomago" not in cru
        db.expire_all()
        refeicao = db.query(Refeicao).one()
        assert refeicao.observacao == "Dor de estomago depois do almoco"

    def test_sem_observacao_fica_nulo(self, client: TestClient, db: Session) -> None:
        client.post(
            "/api/v1/refeicoes", json=factories.refeicao(1), headers=factories.headers_de(1)
        )

        assert _crus(db, "SELECT observacao FROM refeicoes") == (None,)


class TestChave:
    def test_mesmo_valor_gera_textos_diferentes(self) -> None:
        # O Fernet usa IV aleatorio: dois pacientes com o mesmo peso nao ficam iguais no banco.
        assert crypto.cifrar("80.00") != crypto.cifrar("80.00")

    def test_ida_e_volta(self) -> None:
        assert crypto.decifrar(crypto.cifrar("Joao")) == "Joao"

    def test_chave_errada_nao_decifra(self, monkeypatch: pytest.MonkeyPatch) -> None:
        token = crypto.cifrar("segredo")
        outra_chave = crypto.Fernet.generate_key().decode()
        monkeypatch.setattr(get_settings(), "ENCRYPTION_KEY", outra_chave)

        with pytest.raises(crypto.ErroDeCriptografia):
            crypto.decifrar(token)

    def test_valor_adulterado_nao_decifra(self) -> None:
        token = crypto.cifrar("segredo")
        adulterado = token[:-4] + ("AAAA" if not token.endswith("AAAA") else "BBBB")

        with pytest.raises(crypto.ErroDeCriptografia):
            crypto.decifrar(adulterado)
