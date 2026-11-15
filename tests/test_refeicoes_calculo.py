"""Testes de refeicoes e calculo nutricional (Task 7.4, parte 2/4).

Complementa `test_refeicoes.py`, `test_alimentos_taco.py`, `test_triagem.py` e
`test_calculo_nutricional.py` com:

- casos de borda do registro/edicao de refeicoes (fuso, PUT parcial, limites);
- regras do calculo por porcao direto no service (arredondamento, totais);
- propriedades do calculo basal (monotonia, teto = TMB x fator);
- testes de integracao dos endpoints com a TACO real (`data/taco.csv`):
  busca -> calculo por porcao -> registro da refeicao -> consumo diario.

Valores esperados calculados a mao a partir da TACO 4a edicao:

  Arroz, tipo 1, cozido    128 kcal | 28.10 carb | 2.50 prot | 0.20 gord (por 100 g)
  Feijao, carioca, cozido   76 kcal | 13.60 carb | 4.80 prot | 0.50 gord (por 100 g)
"""

import csv
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.alimento_taco import AlimentoTaco
from app.models.paciente import Genero, NivelAtividade
from app.schemas.calculo_nutricional import ItemCalculoIn, MetodoPreparo
from app.services import calculo_nutricional
from app.services.calculo_basal import FATORES_ATIVIDADE, calcular_teto_calorico, calcular_tmb
from tests import factories

ROTA_REFEICOES = "/api/v1/refeicoes"
ROTA_CALCULO = "/api/v1/calculo-nutricional"
ROTA_TACO = "/api/v1/alimentos-taco"
TACO_CSV = Path(__file__).resolve().parent.parent / "data" / "taco.csv"

PACIENTE = 1


@pytest.fixture
def paciente(db: Session, client: TestClient) -> None:
    """Paciente 1 existe e as requisicoes saem autenticadas como ele (Task 1.6)."""
    factories.criar_paciente(db, PACIENTE)
    client.headers.update(factories.headers_de(PACIENTE))


@pytest.fixture
def taco_real(db: Session) -> None:
    """Carrega a TACO completa no banco de teste, como o `scripts/importar_taco.py`."""
    with TACO_CSV.open(encoding="utf-8") as arquivo:
        db.add_all(
            AlimentoTaco(
                nome=linha["nome"],
                categoria=linha["categoria"],
                kcal_100g=Decimal(linha["kcal_100g"]),
                carbs_100g=Decimal(linha["carbs_100g"]),
                prot_100g=Decimal(linha["prot_100g"]),
                gord_100g=Decimal(linha["gord_100g"]),
            )
            for linha in csv.DictReader(arquivo)
        )
    db.commit()


def _criar_refeicao(client: TestClient, **kwargs: Any) -> dict[str, Any]:
    resposta = client.post(ROTA_REFEICOES, json=factories.refeicao(**kwargs))
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


# --------------------------------------------------------------------------- #
# Refeicoes: casos de borda
# --------------------------------------------------------------------------- #


@pytest.mark.usefixtures("paciente")
class TestRefeicaoFusoHorario:
    def test_horario_sem_fuso_e_tratado_como_utc(self, client: TestClient) -> None:
        resposta = client.post(
            ROTA_REFEICOES,
            json={**factories.refeicao(), "consumida_em": "2026-01-10T12:30:00"},
        )

        assert resposta.status_code == 201, resposta.text
        assert resposta.json()["consumida_em"].startswith("2026-01-10T12:30:00")
        assert resposta.json()["consumida_em"].endswith(("Z", "+00:00"))

    def test_horario_com_offset_e_convertido_para_utc(self, client: TestClient) -> None:
        """21h em Brasilia (-03:00) ja e o dia seguinte em UTC."""
        refeicao = client.post(
            ROTA_REFEICOES,
            json={**factories.refeicao(), "consumida_em": "2026-01-10T21:00:00-03:00"},
        ).json()

        assert refeicao["consumida_em"].startswith("2026-01-11T00:00:00")
        dia_11 = client.get(
            f"{ROTA_REFEICOES}/consumo-diario",
            params={"paciente_id": PACIENTE, "data": "2026-01-11"},
        ).json()
        dia_10 = client.get(
            f"{ROTA_REFEICOES}/consumo-diario",
            params={"paciente_id": PACIENTE, "data": "2026-01-10"},
        ).json()
        assert dia_11["quantidade_refeicoes"] == 1
        assert dia_10["quantidade_refeicoes"] == 0

    def test_tipo_sugerido_usa_a_hora_em_utc(self, client: TestClient) -> None:
        """09h em -03:00 = 12h UTC: cai na janela do almoco (regra atual da API)."""
        refeicao = client.post(
            ROTA_REFEICOES,
            json={**factories.refeicao(), "consumida_em": "2026-01-10T09:00:00-03:00"},
        ).json()
        assert refeicao["tipo"] == "almoco"

    def test_aceita_ate_um_minuto_no_futuro(self, client: TestClient) -> None:
        """Folga para relogio de celular levemente adiantado."""
        momento = datetime.now(UTC) + timedelta(seconds=30)
        resposta = client.post(ROTA_REFEICOES, json=factories.refeicao(consumida_em=momento))
        assert resposta.status_code == 201


@pytest.mark.usefixtures("paciente")
class TestEdicaoParcial:
    def test_put_so_com_observacao_mantem_itens_tipo_e_horario(self, client: TestClient) -> None:
        criada = _criar_refeicao(client, tipo="jantar")

        resposta = client.put(f"{ROTA_REFEICOES}/{criada['id']}", json={"observacao": "sem sal"})

        assert resposta.status_code == 200
        atualizada = resposta.json()
        assert atualizada["observacao"] == "sem sal"
        assert atualizada["tipo"] == "jantar"
        assert atualizada["consumida_em"] == criada["consumida_em"]
        assert [i["nome_alimento"] for i in atualizada["itens"]] == [
            i["nome_alimento"] for i in criada["itens"]
        ]

    def test_put_troca_horario_e_move_a_refeicao_de_dia(self, client: TestClient) -> None:
        criada = _criar_refeicao(client, consumida_em=datetime(2026, 1, 10, 12, tzinfo=UTC))

        client.put(
            f"{ROTA_REFEICOES}/{criada['id']}",
            json={"consumida_em": "2026-01-09T12:00:00+00:00"},
        )

        params = {"paciente_id": PACIENTE}
        assert client.get(ROTA_REFEICOES, params={**params, "data": "2026-01-10"}).json() == []
        assert len(client.get(ROTA_REFEICOES, params={**params, "data": "2026-01-09"}).json()) == 1

    def test_put_recalcula_totais_ao_trocar_itens(self, client: TestClient) -> None:
        criada = _criar_refeicao(client)

        atualizada = client.put(
            f"{ROTA_REFEICOES}/{criada['id']}",
            json={
                "itens": [
                    factories.item(calorias="100.10", proteinas="1.00"),
                    factories.item(nome="Feijao", calorias="50.05", proteinas="2.50"),
                ]
            },
        ).json()

        assert atualizada["totais"]["calorias_kcal"] == 150.15
        assert atualizada["totais"]["proteinas_g"] == 3.5

    def test_put_em_refeicao_inexistente_da_404(self, client: TestClient) -> None:
        resposta = client.put(f"{ROTA_REFEICOES}/9999", json={"observacao": "x"})
        assert resposta.status_code == 404
        assert resposta.json()["detail"] == "Refeicao nao encontrada"

    def test_put_com_horario_no_futuro_da_422_e_nao_altera(self, client: TestClient) -> None:
        criada = _criar_refeicao(client)
        futuro = (datetime.now(UTC) + timedelta(days=1)).isoformat()

        resposta = client.put(f"{ROTA_REFEICOES}/{criada['id']}", json={"consumida_em": futuro})

        assert resposta.status_code == 422
        detalhe = client.get(f"{ROTA_REFEICOES}/{criada['id']}").json()
        assert detalhe["consumida_em"] == criada["consumida_em"]

    def test_put_com_lista_de_itens_vazia_da_422(self, client: TestClient) -> None:
        criada = _criar_refeicao(client)
        resposta = client.put(f"{ROTA_REFEICOES}/{criada['id']}", json={"itens": []})
        assert resposta.status_code == 422


@pytest.mark.usefixtures("paciente")
class TestLimitesDeEntrada:
    @pytest.mark.parametrize(
        "alteracao",
        [
            {"quantidade_g": "10.123"},  # mais de 2 casas decimais
            {"calorias_kcal": "100000.01"},  # acima do limite
            {"nome_alimento": "a" * 161},
        ],
    )
    def test_recusa_item_fora_dos_limites(
        self, client: TestClient, alteracao: dict[str, str]
    ) -> None:
        resposta = client.post(
            ROTA_REFEICOES, json=factories.refeicao(itens=[{**factories.item(), **alteracao}])
        )
        assert resposta.status_code == 422

    def test_aceita_valores_no_limite(self, client: TestClient) -> None:
        item = factories.item(quantidade_g="100000.00", calorias="0.00")
        resposta = client.post(ROTA_REFEICOES, json=factories.refeicao(itens=[item]))
        assert resposta.status_code == 201

    def test_recusa_observacao_longa(self, client: TestClient) -> None:
        resposta = client.post(ROTA_REFEICOES, json=factories.refeicao(observacao="x" * 501))
        assert resposta.status_code == 422

    @pytest.mark.parametrize(
        "params",
        [
            {"paciente_id": 0},
            {"paciente_id": PACIENTE, "limite": 0},
            {"paciente_id": PACIENTE, "limite": 201},
            {"paciente_id": PACIENTE, "deslocamento": -1},
            {"paciente_id": PACIENTE, "data": "10/01/2026"},
            {"paciente_id": PACIENTE, "tipo": "ceia"},
        ],
    )
    def test_recusa_parametros_de_listagem_invalidos(
        self, client: TestClient, params: dict[str, Any]
    ) -> None:
        assert client.get(ROTA_REFEICOES, params=params).status_code == 422

    def test_consumo_diario_exige_data(self, client: TestClient) -> None:
        resposta = client.get(f"{ROTA_REFEICOES}/consumo-diario", params={"paciente_id": PACIENTE})
        assert resposta.status_code == 422

    def test_remover_duas_vezes_da_404_na_segunda(self, client: TestClient) -> None:
        criada = _criar_refeicao(client)
        assert client.delete(f"{ROTA_REFEICOES}/{criada['id']}").status_code == 204
        assert client.delete(f"{ROTA_REFEICOES}/{criada['id']}").status_code == 404


# --------------------------------------------------------------------------- #
# Calculo por porcao: service
# --------------------------------------------------------------------------- #


def _taco(nome: str, kcal: str, carbs: str = "0", prot: str = "0", gord: str = "0") -> AlimentoTaco:
    return AlimentoTaco(
        nome=nome,
        categoria="Teste",
        kcal_100g=Decimal(kcal),
        carbs_100g=Decimal(carbs),
        prot_100g=Decimal(prot),
        gord_100g=Decimal(gord),
    )


class TestPorPorcao:
    @pytest.mark.parametrize(
        ("valor_100g", "gramas", "esperado"),
        [
            ("128.00", "150", "192.00"),
            ("128.00", "100", "128.00"),
            ("128.00", "33.33", "42.66"),  # 42.6624
            ("0.05", "50", "0.03"),  # 0.025: meio para cima, nao para o par
            ("0.15", "10", "0.02"),  # 0.015
            ("0.00", "500", "0.00"),
            ("884.00", "0.01", "0.09"),  # 0.0884
        ],
    )
    def test_formula_e_arredondamento(self, valor_100g: str, gramas: str, esperado: str) -> None:
        resultado = calculo_nutricional._por_porcao(Decimal(valor_100g), Decimal(gramas))
        assert resultado == Decimal(esperado)


class TestCalcularRefeicaoService:
    @pytest.fixture(autouse=True)
    def _alimentos(self, db: Session) -> None:
        db.add_all(
            [
                _taco("Arroz, tipo 1, cozido", "128.00", "28.10", "2.50", "0.20"),
                _taco("Feijão, carioca, cozido", "76.00", "13.60", "4.80", "0.50"),
            ]
        )
        db.commit()

    def _item(self, classe: str, gramas: str) -> ItemCalculoIn:
        return ItemCalculoIn(classe=classe, metodo_preparo=MetodoPreparo.COZIDO, gramas=gramas)

    def test_totais_somam_as_linhas_ja_arredondadas(
        self, db: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Duas porcoes de 0.005 kcal: cada linha vira 0.01, o total 0.02 (nao 0.01)."""
        db.add(_taco("Teste, quase sem caloria", "0.01"))
        db.commit()
        mapeamento = {("teste", "cru"): "Teste, quase sem caloria"}
        monkeypatch.setattr(calculo_nutricional, "carregar_mapeamento", lambda: mapeamento)
        item = ItemCalculoIn(classe="teste", metodo_preparo=MetodoPreparo.CRU, gramas="50")

        resultado = calculo_nutricional.calcular_refeicao(db, [item, item])

        assert [linha["calorias_kcal"] for linha in resultado["itens"]] == [
            Decimal("0.01"),
            Decimal("0.01"),
        ]
        assert resultado["totais"]["calorias_kcal"] == Decimal("0.02")

    def test_mesmo_alimento_duas_vezes_gera_duas_linhas(self, db: Session) -> None:
        resultado = calculo_nutricional.calcular_refeicao(
            db, [self._item("arroz", "100"), self._item("arroz", "50")]
        )
        assert [linha["calorias_kcal"] for linha in resultado["itens"]] == [
            Decimal("128.00"),
            Decimal("64.00"),
        ]
        assert resultado["totais"]["calorias_kcal"] == Decimal("192.00")

    def test_preserva_a_ordem_dos_itens(self, db: Session) -> None:
        resultado = calculo_nutricional.calcular_refeicao(
            db, [self._item("feijao_carioca", "80"), self._item("arroz", "150")]
        )
        assert [linha["classe"] for linha in resultado["itens"]] == ["feijao_carioca", "arroz"]

    def test_erro_de_mapeamento_vem_antes_de_consultar_o_banco(self, db: Session) -> None:
        with pytest.raises(calculo_nutricional.SemMapeamento) as erro:
            calculo_nutricional.calcular_refeicao(
                db, [self._item("arroz", "100"), self._item("pizza_de_marte", "100")]
            )
        assert erro.value.classe == "pizza_de_marte"
        assert erro.value.metodo_preparo == "cozido"


# --------------------------------------------------------------------------- #
# Calculo basal: propriedades
# --------------------------------------------------------------------------- #


def _tmb(**kwargs: Any) -> Decimal:
    base: dict[str, Any] = {
        "peso_kg": Decimal("70"),
        "altura_cm": Decimal("170"),
        "idade": 30,
        "genero": Genero.FEMININO,
    }
    return calcular_tmb(**{**base, **kwargs})


class TestPropriedadesCalculoBasal:
    @pytest.mark.parametrize("genero", list(Genero))
    def test_mais_peso_aumenta_a_tmb(self, genero: Genero) -> None:
        assert _tmb(genero=genero, peso_kg=Decimal("71")) > _tmb(genero=genero)

    @pytest.mark.parametrize("genero", list(Genero))
    def test_mais_altura_aumenta_a_tmb(self, genero: Genero) -> None:
        assert _tmb(genero=genero, altura_cm=Decimal("171")) > _tmb(genero=genero)

    @pytest.mark.parametrize("genero", list(Genero))
    def test_mais_idade_diminui_a_tmb(self, genero: Genero) -> None:
        assert _tmb(genero=genero, idade=31) < _tmb(genero=genero)

    def test_fatores_crescem_com_o_nivel_de_atividade(self) -> None:
        ordem = [
            NivelAtividade.SEDENTARIO,
            NivelAtividade.LEVE,
            NivelAtividade.MODERADO,
            NivelAtividade.INTENSO,
            NivelAtividade.MUITO_INTENSO,
        ]
        fatores = [FATORES_ATIVIDADE[nivel] for nivel in ordem]
        assert fatores == sorted(fatores)
        assert len(set(fatores)) == len(fatores)

    @pytest.mark.parametrize("nivel", list(NivelAtividade))
    def test_endpoint_devolve_teto_igual_a_tmb_vezes_fator(
        self, client: TestClient, db: Session, nivel: NivelAtividade
    ) -> None:
        factories.criar_paciente(db, PACIENTE)
        resposta = client.post(
            f"/api/v1/pacientes/{PACIENTE}/triagem",
            json={
                "peso_kg": "65.50",
                "altura_cm": "168.00",
                "idade": 41,
                "genero": "feminino",
                "nivel_atividade": nivel.value,
            },
            headers=factories.headers_de(PACIENTE),
        )

        assert resposta.status_code == 200, resposta.text
        corpo = resposta.json()
        tmb = Decimal(str(corpo["tmb_kcal"]))
        assert Decimal(str(corpo["fator_atividade"])) == FATORES_ATIVIDADE[nivel]
        assert Decimal(str(corpo["teto_calorico_kcal"])) == calcular_teto_calorico(tmb, nivel)


# --------------------------------------------------------------------------- #
# Integracao dos endpoints com a TACO real
# --------------------------------------------------------------------------- #


@pytest.mark.usefixtures("taco_real")
class TestIntegracaoComTacoReal:
    @pytest.fixture(autouse=True)
    def _logado(self, db: Session, client: TestClient) -> None:
        """A API exige token (Task 1.6): por padrao entra como o paciente 1."""
        factories.criar_paciente(db, PACIENTE)
        client.headers.update(factories.headers_de(PACIENTE))

    def test_tabela_completa_foi_carregada(self, db: Session) -> None:
        assert db.query(AlimentoTaco).count() > 500

    def test_busca_por_trecho_encontra_alimentos_reais(self, client: TestClient) -> None:
        resposta = client.get(ROTA_TACO, params={"nome": "arroz, tipo 1"})

        assert resposta.status_code == 200
        nomes = [alimento["nome"] for alimento in resposta.json()]
        assert "Arroz, tipo 1, cozido" in nomes
        assert nomes == sorted(nomes)

    def test_busca_com_espacos_nas_pontas(self, client: TestClient) -> None:
        resposta = client.get(ROTA_TACO, params={"nome": "  feijão, carioca  "})
        assert {a["nome"] for a in resposta.json()} >= {
            "Feijão, carioca, cozido",
            "Feijão, carioca, cru",
        }

    def test_todo_mapeamento_da_ia_calcula_sem_erro(self, client: TestClient) -> None:
        """Cada linha do de-para resolve para um alimento da TACO carregada."""
        mapeamento = calculo_nutricional.carregar_mapeamento()
        itens = [
            {"classe": classe, "metodo_preparo": preparo, "gramas": "100"}
            for classe, preparo in mapeamento
        ]

        resposta = client.post(ROTA_CALCULO, json={"itens": itens})

        assert resposta.status_code == 200, resposta.text
        assert len(resposta.json()["itens"]) == len(mapeamento)

    def test_fluxo_foto_calculo_registro_e_consumo_diario(
        self, client: TestClient, db: Session
    ) -> None:
        # 1. Paciente se cadastra e faz a triagem (teto calorico)
        cadastro = client.post("/api/v1/auth/cadastro/paciente", json=factories.cadastro())
        assert cadastro.status_code == 201
        paciente_id = cadastro.json()["usuario"]["id"]
        # A partir daqui as chamadas saem como o paciente recem-cadastrado.
        client.headers["Authorization"] = f"Bearer {cadastro.json()['access_token']}"
        triagem = client.post(
            f"/api/v1/pacientes/{paciente_id}/triagem",
            json={
                "peso_kg": "80.00",
                "altura_cm": "180.00",
                "idade": 30,
                "genero": "masculino",
                "nivel_atividade": "moderado",
            },
        ).json()
        assert triagem["tmb_kcal"] == 1864.36
        assert triagem["teto_calorico_kcal"] == 2889.76

        # 2. A IA reconheceu arroz (150 g) e feijao (80 g): calculo por porcao
        calculo = client.post(
            ROTA_CALCULO,
            json={
                "itens": [
                    {"classe": "arroz", "metodo_preparo": "cozido", "gramas": "150"},
                    {"classe": "feijao_carioca", "metodo_preparo": "cozido", "gramas": "80"},
                ]
            },
        )
        assert calculo.status_code == 200, calculo.text
        tabela = calculo.json()
        assert tabela["itens"][0]["calorias_kcal"] == 192.0
        assert tabela["itens"][1]["calorias_kcal"] == 60.8
        assert tabela["totais"] == {
            "calorias_kcal": 252.8,
            "proteinas_g": 7.59,
            "carboidratos_g": 53.03,
            "gorduras_g": 0.7,
        }

        # 3. O app confirma e registra a refeicao com os valores calculados
        consumida_em = datetime.combine(date(2026, 1, 10), datetime.min.time(), tzinfo=UTC)
        itens = [
            {
                "nome_alimento": linha["alimento_taco"],
                "quantidade_g": str(linha["gramas"]),
                "calorias_kcal": str(linha["calorias_kcal"]),
                "proteinas_g": str(linha["proteinas_g"]),
                "carboidratos_g": str(linha["carboidratos_g"]),
                "gorduras_g": str(linha["gorduras_g"]),
            }
            for linha in tabela["itens"]
        ]
        almoco = client.post(
            ROTA_REFEICOES,
            json=factories.refeicao(
                paciente_id=paciente_id,
                consumida_em=consumida_em.replace(hour=12),
                itens=itens,
            ),
        )
        assert almoco.status_code == 201, almoco.text
        assert almoco.json()["tipo"] == "almoco"
        assert almoco.json()["totais"] == tabela["totais"]

        # 4. Um segundo registro no mesmo dia entra na soma do consumo diario
        client.post(
            ROTA_REFEICOES,
            json=factories.refeicao(
                paciente_id=paciente_id,
                consumida_em=consumida_em.replace(hour=20),
                itens=itens[:1],
            ),
        )
        consumo = client.get(
            f"{ROTA_REFEICOES}/consumo-diario",
            params={"paciente_id": paciente_id, "data": "2026-01-10"},
        ).json()

        assert consumo["quantidade_refeicoes"] == 2
        assert consumo["totais"]["calorias_kcal"] == pytest.approx(252.8 + 192.0)
        assert [r["tipo"] for r in consumo["refeicoes"]] == ["jantar", "almoco"]
        assert consumo["totais"]["calorias_kcal"] < triagem["teto_calorico_kcal"]

    def test_metodos_de_preparo_diferentes_dao_valores_diferentes(self, client: TestClient) -> None:
        resposta = client.post(
            ROTA_CALCULO,
            json={
                "itens": [
                    {"classe": "arroz", "metodo_preparo": "cru", "gramas": "100"},
                    {"classe": "arroz", "metodo_preparo": "cozido", "gramas": "100"},
                ]
            },
        ).json()

        cru, cozido = resposta["itens"]
        assert cru["alimento_taco"] == "Arroz, tipo 1, cru"
        assert cozido["alimento_taco"] == "Arroz, tipo 1, cozido"
        assert cru["calorias_kcal"] > cozido["calorias_kcal"]
