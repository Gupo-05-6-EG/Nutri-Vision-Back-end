"""Testes do calculo basal (RF14): formula pura e endpoint de triagem.

Os valores esperados foram calculados a mao, direto da equacao de
Harris-Benedict, e nao a partir do proprio codigo:

  homem, 30 anos, 80 kg, 180 cm:
    TMB = 66.47 + 13.75*80 + 5.003*180 - 6.755*30 = 1864.36
  mulher, 25 anos, 60 kg, 165 cm:
    TMB = 655.1 + 9.563*60 + 1.850*165 - 4.676*25 = 1417.23
"""

from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.paciente import Genero, NivelAtividade, Paciente
from app.schemas.paciente import (
    ALTURA_MAX_CM,
    IDADE_MIN,
    PESO_MAX_KG,
)
from app.services.calculo_basal import (
    FATORES_ATIVIDADE,
    calcular_teto_calorico,
    calcular_tmb,
)

MAX_NUMERIC_6_2 = Decimal("9999.99")


def _payload(**alteracoes: Any) -> dict[str, Any]:
    """Triagem valida (homem, 30 anos, 80 kg, 180 cm, atividade moderada)."""
    corpo: dict[str, Any] = {
        "peso_kg": "80.00",
        "altura_cm": "180.00",
        "idade": 30,
        "genero": "masculino",
        "nivel_atividade": "moderado",
    }
    corpo.update(alteracoes)
    return corpo


def _rota(paciente_id: int | str = 1) -> str:
    return f"/api/v1/pacientes/{paciente_id}/triagem"


class TestFormula:
    def test_tmb_de_homem(self) -> None:
        tmb = calcular_tmb(
            peso_kg=Decimal("80"), altura_cm=Decimal("180"), idade=30, genero=Genero.MASCULINO
        )

        assert tmb == Decimal("1864.36")

    def test_tmb_de_mulher(self) -> None:
        tmb = calcular_tmb(
            peso_kg=Decimal("60"), altura_cm=Decimal("165"), idade=25, genero=Genero.FEMININO
        )

        assert tmb == Decimal("1417.23")

    @pytest.mark.parametrize(
        ("nivel", "fator", "esperado"),
        [
            (NivelAtividade.SEDENTARIO, "1.2", "2237.23"),
            (NivelAtividade.LEVE, "1.375", "2563.50"),
            (NivelAtividade.MODERADO, "1.55", "2889.76"),
            (NivelAtividade.INTENSO, "1.725", "3216.02"),
            (NivelAtividade.MUITO_INTENSO, "1.9", "3542.28"),
        ],
    )
    def test_teto_aplica_o_fator_de_atividade(
        self, nivel: NivelAtividade, fator: str, esperado: str
    ) -> None:
        assert FATORES_ATIVIDADE[nivel] == Decimal(fator)
        assert calcular_teto_calorico(Decimal("1864.36"), nivel) == Decimal(esperado)

    def test_arredonda_meio_para_cima_sem_erro_de_float(self) -> None:
        # 1864.36 x 1.375 = 2563.495 exato. Com float, isso cairia em 2563.49.
        teto = calcular_teto_calorico(Decimal("1864.36"), NivelAtividade.LEVE)

        assert teto == Decimal("2563.50")

    def test_todos_os_niveis_tem_fator(self) -> None:
        assert set(FATORES_ATIVIDADE) == set(NivelAtividade)


class TestEndpoint:
    def test_devolve_tmb_fator_e_teto(self, client: TestClient) -> None:
        resposta = client.post(_rota(7), json=_payload())

        assert resposta.status_code == 200, resposta.text
        assert resposta.json() == {
            "paciente_id": 7,
            "tmb_kcal": 1864.36,
            "fator_atividade": 1.55,
            "teto_calorico_kcal": 2889.76,
            "origem_meta": "harris_benedict",
        }

    def test_valores_saem_como_numero_no_json(self, client: TestClient) -> None:
        corpo = client.post(_rota(), json=_payload()).json()

        assert isinstance(corpo["tmb_kcal"], float)
        assert isinstance(corpo["fator_atividade"], float)
        assert isinstance(corpo["teto_calorico_kcal"], float)

    def test_calcula_para_mulher(self, client: TestClient) -> None:
        corpo = client.post(
            _rota(),
            json=_payload(
                peso_kg="60", altura_cm="165", idade=25, genero="feminino", nivel_atividade="leve"
            ),
        ).json()

        assert corpo["tmb_kcal"] == 1417.23
        assert corpo["teto_calorico_kcal"] == 1948.69

    def test_aceita_numeros_no_json(self, client: TestClient) -> None:
        # O app manda peso/altura como numero, nao como string.
        resposta = client.post(_rota(), json=_payload(peso_kg=80.5, altura_cm=180))

        assert resposta.status_code == 200, resposta.text

    def test_salva_triagem_e_teto_no_paciente(self, client: TestClient, db: Session) -> None:
        client.post(_rota(7), json=_payload())

        db.expire_all()
        paciente = db.get(Paciente, 7)
        assert paciente is not None
        assert paciente.peso_kg == Decimal("80.00")
        assert paciente.altura_cm == Decimal("180.00")
        assert paciente.idade == 30
        assert paciente.genero == "masculino"
        assert paciente.nivel_atividade == "moderado"
        assert paciente.meta_kcal == Decimal("2889.76")
        assert paciente.origem_meta == "harris_benedict"

    def test_refazer_a_triagem_atualiza_sem_duplicar(self, client: TestClient, db: Session) -> None:
        client.post(_rota(7), json=_payload())
        resposta = client.post(_rota(7), json=_payload(peso_kg="70", nivel_atividade="sedentario"))

        assert resposta.status_code == 200, resposta.text
        # 66.47 + 13.75*70 + 5.003*180 - 6.755*30 = 1726.86 ; x 1.2 = 2072.232
        assert resposta.json()["teto_calorico_kcal"] == 2072.23

        db.expire_all()
        assert db.query(Paciente).filter(Paciente.id == 7).count() == 1
        paciente = db.get(Paciente, 7)
        assert paciente is not None
        assert paciente.peso_kg == Decimal("70.00")
        assert paciente.meta_kcal == Decimal("2072.23")

    def test_pacientes_diferentes_nao_se_misturam(self, client: TestClient, db: Session) -> None:
        client.post(_rota(1), json=_payload())
        client.post(_rota(2), json=_payload(genero="feminino", nivel_atividade="intenso"))

        db.expire_all()
        um, dois = db.get(Paciente, 1), db.get(Paciente, 2)
        assert um is not None
        assert dois is not None
        assert um.meta_kcal == Decimal("2889.76")
        assert dois.genero == "feminino"
        assert dois.meta_kcal != um.meta_kcal


class TestValidacao:
    @pytest.mark.parametrize(
        "alteracao",
        [
            {"genero": "outro"},
            {"nivel_atividade": "atleta"},
            {"peso_kg": "0"},
            {"peso_kg": "-70"},
            {"peso_kg": "19.99"},
            {"peso_kg": str(PESO_MAX_KG + 1)},
            {"peso_kg": "80.123"},
            {"peso_kg": "abc"},
            {"altura_cm": "99.99"},
            {"altura_cm": str(ALTURA_MAX_CM + 1)},
            {"altura_cm": "1.80"},  # metros em vez de centimetros
            {"idade": IDADE_MIN - 1},
            {"idade": 121},
            {"idade": 30.5},
        ],
    )
    def test_recusa_valores_invalidos(
        self, client: TestClient, db: Session, alteracao: dict[str, Any]
    ) -> None:
        resposta = client.post(_rota(), json=_payload(**alteracao))

        assert resposta.status_code == 422
        assert db.get(Paciente, 1) is None, "nada deve ser salvo quando a triagem e invalida"

    @pytest.mark.parametrize(
        "campo", ["peso_kg", "altura_cm", "idade", "genero", "nivel_atividade"]
    )
    def test_todos_os_campos_sao_obrigatorios(self, client: TestClient, campo: str) -> None:
        corpo = _payload()
        del corpo[campo]

        resposta = client.post(_rota(), json=corpo)

        assert resposta.status_code == 422

    @pytest.mark.parametrize("paciente_id", ["0", "-1", "abc"])
    def test_recusa_paciente_id_invalido(self, client: TestClient, paciente_id: str) -> None:
        resposta = client.post(_rota(paciente_id), json=_payload())

        assert resposta.status_code == 422

    def test_teto_maximo_da_faixa_valida_cabe_no_banco(self, client: TestClient) -> None:
        """O pior caso aceito (numeric(6,2) em `meta_kcal`) nao pode estourar a coluna."""
        resposta = client.post(
            _rota(),
            json=_payload(
                peso_kg=str(PESO_MAX_KG),
                altura_cm=str(ALTURA_MAX_CM),
                idade=IDADE_MIN,
                nivel_atividade="muito_intenso",
            ),
        )

        assert resposta.status_code == 200, resposta.text
        assert Decimal(str(resposta.json()["teto_calorico_kcal"])) <= MAX_NUMERIC_6_2
