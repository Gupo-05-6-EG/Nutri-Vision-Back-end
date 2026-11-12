"""Auditoria de planos e dados clinicos (Task 5.3, RNF08).

Confere a trilha gravada (autor, data/hora, valores antes/depois) e que ela vai
cifrada para o banco, ja que guarda copias de dados de saude.
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from app.models.auditoria import AcaoAuditoria, Auditoria, EntidadeAuditada
from app.models.usuario import Usuario
from app.models.vinculo import Vinculo
from tests import factories

NUTRI, PACIENTE = 10, 11
API = "/api/v1/pacientes"

NUTRI_HEADERS = factories.headers_de(NUTRI, "nutricionista")
PACIENTE_HEADERS = factories.headers_de(PACIENTE, "paciente")
PREFIXO_FERNET = "gAAAA"


@pytest.fixture(autouse=True)
def _usuarios(db: Session) -> None:
    factories.criar_nutricionista(db, NUTRI)
    factories.criar_paciente(db, PACIENTE)
    db.add(Vinculo(status="ativo", nutricionista_id=NUTRI, paciente_id=PACIENTE))
    db.commit()


def _plano(titulo: str, meta_kcal: int = 600) -> dict[str, Any]:
    return {
        "titulo": titulo,
        "refeicoes": [
            {
                "nome": "Almoco",
                "meta_kcal": meta_kcal,
                "meta_proteinas_g": 40,
                "alimentos": [{"nome_alimento": "Arroz", "quantidade_g": 150}],
            }
        ],
    }


def _salvar_plano(client: TestClient, titulo: str, meta_kcal: int = 600) -> dict[str, Any]:
    resposta = client.post(
        f"{API}/{PACIENTE}/planos", json=_plano(titulo, meta_kcal), headers=NUTRI_HEADERS
    )
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


TRIAGEM = {
    "peso_kg": "80.00",
    "altura_cm": "180.00",
    "idade": 30,
    "genero": "masculino",
    "nivel_atividade": "moderado",
}


def _triagem(client: TestClient, **alteracoes: Any) -> None:
    resposta = client.post(
        f"{API}/{PACIENTE}/triagem", json={**TRIAGEM, **alteracoes}, headers=PACIENTE_HEADERS
    )
    assert resposta.status_code == 200, resposta.text


def _auditorias(db: Session, entidade: EntidadeAuditada) -> list[Auditoria]:
    db.expire_all()
    consulta = select(Auditoria).where(Auditoria.entidade == entidade.value).order_by(Auditoria.id)
    return list(db.execute(consulta).scalars())


class TestAuditoriaDoPlano:
    def test_primeiro_plano_e_uma_criacao_sem_valor_anterior(
        self, client: TestClient, db: Session
    ) -> None:
        plano = _salvar_plano(client, "Plano 1")

        (registro,) = _auditorias(db, EntidadeAuditada.PLANO_ALIMENTAR)

        assert registro.acao == AcaoAuditoria.CRIACAO
        assert registro.antes is None
        assert registro.depois["titulo"] == "Plano 1"
        assert registro.depois["versao"] == 1
        assert registro.paciente_id == PACIENTE
        assert registro.autor_id == NUTRI
        assert registro.registro_id == plano["id"]
        assert registro.criado_em is not None

    def test_edicao_guarda_os_valores_de_antes_e_depois(
        self, client: TestClient, db: Session
    ) -> None:
        primeiro = _salvar_plano(client, "Plano 1", meta_kcal=600)
        segundo = _salvar_plano(client, "Plano 2", meta_kcal=750)

        _, edicao = _auditorias(db, EntidadeAuditada.PLANO_ALIMENTAR)

        assert edicao.acao == AcaoAuditoria.ATUALIZACAO
        assert edicao.registro_id == segundo["id"]
        assert edicao.antes["id"] == primeiro["id"]
        assert edicao.antes["titulo"] == "Plano 1"
        assert edicao.antes["totais"]["meta_kcal"] == 600.0
        assert edicao.depois["titulo"] == "Plano 2"
        assert edicao.depois["totais"]["meta_kcal"] == 750.0
        assert edicao.depois["refeicoes"][0]["alimentos"][0]["nome_alimento"] == "Arroz"

    def test_um_registro_por_versao_salva(self, client: TestClient, db: Session) -> None:
        for n in range(3):
            _salvar_plano(client, f"Plano {n}")

        assert len(_auditorias(db, EntidadeAuditada.PLANO_ALIMENTAR)) == 3

    def test_plano_recusado_nao_deixa_auditoria(self, client: TestClient, db: Session) -> None:
        invalido = _plano("Invalido")
        invalido["refeicoes"][0]["alimentos"][0]["alimento_taco_id"] = 999999

        resposta = client.post(f"{API}/{PACIENTE}/planos", json=invalido, headers=NUTRI_HEADERS)

        assert resposta.status_code == 422
        assert _auditorias(db, EntidadeAuditada.PLANO_ALIMENTAR) == []

    def test_acesso_negado_nao_deixa_auditoria(self, client: TestClient, db: Session) -> None:
        db.execute(delete(Vinculo))
        db.commit()

        resposta = client.post(
            f"{API}/{PACIENTE}/planos", json=_plano("Sem vinculo"), headers=NUTRI_HEADERS
        )

        assert resposta.status_code == 403
        assert _auditorias(db, EntidadeAuditada.PLANO_ALIMENTAR) == []

    def test_banco_guarda_antes_e_depois_cifrados(self, client: TestClient, db: Session) -> None:
        _salvar_plano(client, "Titulo secreto do plano")
        _salvar_plano(client, "Outro titulo secreto")

        linhas = db.execute(text("SELECT antes, depois FROM auditorias ORDER BY id")).all()

        assert linhas[0].antes is None
        for antes, depois in linhas:
            for valor in (antes, depois):
                if valor is not None:
                    assert valor.startswith(PREFIXO_FERNET)
                    assert "secreto" not in valor
        assert linhas[1].antes.startswith(PREFIXO_FERNET)


class TestAuditoriaDosDadosClinicos:
    def test_primeira_triagem_e_uma_criacao_feita_pelo_paciente(
        self, client: TestClient, db: Session
    ) -> None:
        _triagem(client)

        (registro,) = _auditorias(db, EntidadeAuditada.DADOS_CLINICOS)

        assert registro.acao == AcaoAuditoria.CRIACAO
        assert registro.antes is None
        assert registro.depois == {
            "peso_kg": 80.0,
            "altura_cm": 180.0,
            "idade": 30,
            "genero": "masculino",
            "nivel_atividade": "moderado",
            "meta_kcal": 2889.76,
            "origem_meta": "harris_benedict",
        }
        assert registro.autor_id == PACIENTE
        assert registro.paciente_id == PACIENTE
        assert registro.registro_id == PACIENTE

    def test_nova_triagem_guarda_os_valores_de_antes_e_depois(
        self, client: TestClient, db: Session
    ) -> None:
        _triagem(client)
        _triagem(client, peso_kg="75.50", nivel_atividade="leve")

        _, atualizacao = _auditorias(db, EntidadeAuditada.DADOS_CLINICOS)

        assert atualizacao.acao == AcaoAuditoria.ATUALIZACAO
        assert atualizacao.antes["peso_kg"] == 80.0
        assert atualizacao.antes["nivel_atividade"] == "moderado"
        assert atualizacao.antes["meta_kcal"] == 2889.76
        assert atualizacao.depois["peso_kg"] == 75.5
        assert atualizacao.depois["nivel_atividade"] == "leve"
        assert atualizacao.depois["meta_kcal"] != atualizacao.antes["meta_kcal"]

    def test_repetir_a_triagem_sem_mudar_nada_nao_gera_registro(
        self, client: TestClient, db: Session
    ) -> None:
        _triagem(client)
        _triagem(client)

        assert len(_auditorias(db, EntidadeAuditada.DADOS_CLINICOS)) == 1

    def test_triagem_invalida_nao_deixa_auditoria(self, client: TestClient, db: Session) -> None:
        resposta = client.post(
            f"{API}/{PACIENTE}/triagem",
            json={**TRIAGEM, "peso_kg": "-1"},
            headers=PACIENTE_HEADERS,
        )

        assert resposta.status_code == 422
        assert _auditorias(db, EntidadeAuditada.DADOS_CLINICOS) == []

    def test_banco_nao_guarda_dado_clinico_em_claro_na_auditoria(
        self, client: TestClient, db: Session
    ) -> None:
        _triagem(client, peso_kg="81.25")

        (depois,) = db.execute(text("SELECT depois FROM auditorias")).one()

        assert depois.startswith(PREFIXO_FERNET)
        assert "81.25" not in depois
        assert "masculino" not in depois


class TestTrilha:
    def test_auditoria_sobrevive_a_remocao_da_conta_do_autor(
        self, client: TestClient, db: Session
    ) -> None:
        _salvar_plano(client, "Plano 1")
        db.execute(delete(Usuario).where(Usuario.id == NUTRI))
        db.commit()

        (registro,) = _auditorias(db, EntidadeAuditada.PLANO_ALIMENTAR)

        assert registro.autor_id is None
        assert registro.depois["titulo"] == "Plano 1"

    def test_plano_e_dados_clinicos_ficam_na_mesma_trilha_do_paciente(
        self, client: TestClient, db: Session
    ) -> None:
        _triagem(client)
        _salvar_plano(client, "Plano 1")

        db.expire_all()
        registros = db.execute(select(Auditoria).order_by(Auditoria.id)).scalars().all()

        assert [r.entidade for r in registros] == ["dados_clinicos", "plano_alimentar"]
        assert {r.paciente_id for r in registros} == {PACIENTE}
