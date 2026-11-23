"""Testes da integracao com o servico de IA (analise de fotos -> TACO com macros).

O servico de IA e simulado com `httpx.MockTransport`: nenhum teste sai para a rede.
"""

from collections.abc import Callable, Iterator
from decimal import Decimal
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.alimento_taco import AlimentoTaco
from app.services.ia_cliente import get_cliente_ia
from tests import factories

ROTA = "/api/v1/analises"
ID = "8c839452-3b71-4c47-9e97-34f14ac7d5ea"
FOTO = {"file": ("prato.jpg", b"\xff\xd8\xff fake jpeg", "image/jpeg")}

Handler = Callable[[httpx.Request], httpx.Response]


class IAFalsa:
    """Servico de IA simulado: registra as requisicoes e responde com `handler`."""

    def __init__(self) -> None:
        self.requisicoes: list[httpx.Request] = []
        self.handler: Handler = lambda _r: httpx.Response(500)

    def __call__(self, requisicao: httpx.Request) -> httpx.Response:
        self.requisicoes.append(requisicao)
        return self.handler(requisicao)

    def responde(self, status: int = 200, json: Any = None) -> None:
        self.handler = lambda _r: httpx.Response(status, json=json)


@pytest.fixture
def ia(app: FastAPI) -> Iterator[IAFalsa]:
    falsa = IAFalsa()

    def _cliente() -> Iterator[httpx.Client]:
        with httpx.Client(
            base_url="http://ia.test", transport=httpx.MockTransport(falsa)
        ) as cliente:
            yield cliente

    app.dependency_overrides[get_cliente_ia] = _cliente
    yield falsa
    app.dependency_overrides.pop(get_cliente_ia, None)


@pytest.fixture(autouse=True)
def _logado(client: TestClient, db: Session) -> None:
    factories.criar_paciente(db, 1)
    client.headers.update(factories.headers_de(1))


def _taco(db: Session, nome: str, kcal: str, carbs: str, prot: str, gord: str) -> AlimentoTaco:
    alimento = AlimentoTaco(
        nome=nome,
        categoria="Teste",
        kcal_100g=Decimal(kcal),
        carbs_100g=Decimal(carbs),
        prot_100g=Decimal(prot),
        gord_100g=Decimal(gord),
    )
    db.add(alimento)
    db.commit()
    return alimento


def _item(food: str, grams: float, confidence: float = 0.95, **extra: Any) -> dict[str, Any]:
    return {"food": food, "grams": grams, "confidence": confidence, **extra}


class TestEnvioDaFoto:
    def test_repassa_o_tipo_de_prato_como_dica(self, client: TestClient, ia: IAFalsa) -> None:
        ia.responde(202, {"id": ID, "status": "QUEUED"})

        resposta = client.post(ROTA, files=FOTO, data={"tipo_prato": "fundo"})

        assert resposta.status_code == 202, resposta.text
        corpo = ia.requisicoes[0].read()
        assert b'name="plate_type"' in corpo
        assert b"deep" in corpo

    def test_sem_tipo_de_prato_nao_manda_dica(self, client: TestClient, ia: IAFalsa) -> None:
        ia.responde(202, {"id": ID, "status": "QUEUED"})

        client.post(ROTA, files=FOTO)

        assert b"plate_type" not in ia.requisicoes[0].read()

    def test_tipo_de_prato_invalido(self, client: TestClient, ia: IAFalsa) -> None:
        resposta = client.post(ROTA, files=FOTO, data={"tipo_prato": "travessa"})

        assert resposta.status_code == 422
        assert ia.requisicoes == []

    def test_repassa_a_foto_e_devolve_o_id(self, client: TestClient, ia: IAFalsa) -> None:
        ia.responde(202, {"id": ID, "status": "QUEUED"})

        resposta = client.post(ROTA, files=FOTO)

        assert resposta.status_code == 202, resposta.text
        assert resposta.json()["id"] == ID
        assert resposta.json()["status"] == "QUEUED"
        [requisicao] = ia.requisicoes
        assert requisicao.method == "POST"
        assert requisicao.url.path == "/api/v1/analyses"
        corpo = requisicao.read()
        assert b'name="file"' in corpo
        assert b"fake jpeg" in corpo

    def test_foto_ruim_volta_na_hora_com_motivo(self, client: TestClient, ia: IAFalsa) -> None:
        ia.responde(
            202,
            {"id": ID, "status": "NOT_ESTIMATED", "reason": "bad_photo", "issues": ["blurry"]},
        )

        corpo = client.post(ROTA, files=FOTO).json()

        assert corpo["status"] == "NOT_ESTIMATED"
        assert corpo["motivo"] == "bad_photo"
        assert corpo["problemas"] == ["blurry"]

    def test_recusa_arquivo_que_nao_e_imagem_sem_chamar_a_ia(
        self, client: TestClient, ia: IAFalsa
    ) -> None:
        resposta = client.post(ROTA, files={"file": ("nota.txt", b"ola", "text/plain")})

        assert resposta.status_code == 415
        assert ia.requisicoes == []

    def test_recusa_arquivo_vazio(self, client: TestClient, ia: IAFalsa) -> None:
        resposta = client.post(ROTA, files={"file": ("prato.jpg", b"", "image/jpeg")})

        assert resposta.status_code == 422
        assert ia.requisicoes == []

    def test_recusa_imagem_grande_demais_sem_chamar_a_ia(
        self, client: TestClient, ia: IAFalsa, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.core.config import get_settings

        monkeypatch.setattr(get_settings(), "AI_MAX_UPLOAD_BYTES", 10)

        resposta = client.post(ROTA, files={"file": ("prato.jpg", b"x" * 11, "image/jpeg")})

        assert resposta.status_code == 413
        assert ia.requisicoes == []

    def test_repassa_a_recusa_da_ia(self, client: TestClient, ia: IAFalsa) -> None:
        ia.responde(415, {"detail": "file is not a valid image"})

        resposta = client.post(ROTA, files=FOTO)

        assert resposta.status_code == 415
        assert resposta.json()["detail"] == "file is not a valid image"

    @pytest.mark.parametrize(
        "falha",
        [
            httpx.ConnectError("conexao recusada"),
            httpx.ReadTimeout("demorou"),
        ],
        ids=["fora_do_ar", "timeout"],
    )
    def test_ia_inacessivel_da_503(
        self, client: TestClient, ia: IAFalsa, falha: httpx.TransportError
    ) -> None:
        def _falha(_r: httpx.Request) -> httpx.Response:
            raise falha

        ia.handler = _falha

        resposta = client.post(ROTA, files=FOTO)

        assert resposta.status_code == 503

    def test_erro_5xx_da_ia_da_503(self, client: TestClient, ia: IAFalsa) -> None:
        ia.responde(503, {"detail": "analysis queue unavailable, try again"})

        assert client.post(ROTA, files=FOTO).status_code == 503


class TestResultado:
    def test_em_andamento_repassa_o_status(self, client: TestClient, ia: IAFalsa) -> None:
        ia.responde(200, {"id": ID, "status": "PROCESSING"})

        resposta = client.get(f"{ROTA}/{ID}")

        assert resposta.status_code == 200
        corpo = resposta.json()
        assert corpo["status"] == "PROCESSING"
        assert corpo["itens"] is None
        assert corpo["totais"] is None
        assert ia.requisicoes[0].url.path == f"/api/v1/analyses/{ID}"

    def test_concluida_liga_a_taco_e_calcula_as_macros(
        self, client: TestClient, db: Session, ia: IAFalsa
    ) -> None:
        arroz = _taco(db, "Arroz, tipo 1, cozido", "128.00", "28.10", "2.50", "0.20")
        feijao = _taco(db, "Feijão, preto, cozido", "77.00", "14.00", "4.50", "0.50")
        ia.responde(
            200,
            {
                "id": ID,
                "status": "DONE",
                "model_version": "gemini-3.8-flash",
                # o taco_id da IA nao e o nosso id: o cruzamento e pelo nome
                "items": [
                    _item("Arroz, tipo 1, cozido", 150.0, taco_id=3),
                    _item("Feijão, preto, cozido", 100.0, 0.8, taco_id=567),
                ],
            },
        )

        corpo = client.get(f"{ROTA}/{ID}").json()

        assert corpo["status"] == "DONE"
        assert corpo["versao_modelo"] == "gemini-3.8-flash"
        primeiro, segundo = corpo["itens"]
        assert primeiro["alimento_taco_id"] == arroz.id
        assert primeiro["alimento"] == "Arroz, tipo 1, cozido"
        assert primeiro["gramas"] == 150.0
        assert primeiro["confianca"] == 0.95
        # 128 kcal/100 g x 150 g = 192 kcal; 28.10 x 1.5 = 42.15 g de carboidratos
        assert primeiro["calorias_kcal"] == 192.0
        assert primeiro["carboidratos_g"] == 42.15
        assert primeiro["proteinas_g"] == 3.75
        assert primeiro["gorduras_g"] == 0.3
        assert segundo["alimento_taco_id"] == feijao.id
        assert segundo["calorias_kcal"] == 77.0
        assert corpo["totais"] == {
            "calorias_kcal": 269.0,
            "proteinas_g": 8.25,
            "carboidratos_g": 56.15,
            "gorduras_g": 0.8,
        }

    def test_nome_casa_mesmo_com_espacos_e_caixa_diferentes(
        self, client: TestClient, db: Session, ia: IAFalsa
    ) -> None:
        salmao = _taco(db, "Salmão, filé, com pele, fresco,  grelhado", "229", "0", "23.9", "14")
        ia.responde(
            200,
            {
                "id": ID,
                "status": "DONE",
                "items": [_item("salmão, filé, com pele, fresco, grelhado ", 100.0)],
            },
        )

        item = client.get(f"{ROTA}/{ID}").json()["itens"][0]

        assert item["alimento_taco_id"] == salmao.id
        assert item["calorias_kcal"] == 229.0

    def test_item_fora_da_taco_vem_sem_macros_e_fora_dos_totais(
        self, client: TestClient, db: Session, ia: IAFalsa
    ) -> None:
        _taco(db, "Arroz, tipo 1, cozido", "128.00", "28.10", "2.50", "0.20")
        ia.responde(
            200,
            {
                "id": ID,
                "status": "DONE",
                "items": [_item("Arroz, tipo 1, cozido", 100.0), _item("farofa", 30.0, 0.7)],
            },
        )

        corpo = client.get(f"{ROTA}/{ID}").json()

        farofa = corpo["itens"][1]
        assert farofa["alimento"] == "farofa"
        assert farofa["alimento_taco_id"] is None
        assert farofa["calorias_kcal"] is None
        assert farofa["gramas"] == 30.0
        assert corpo["totais"]["calorias_kcal"] == 128.0

    @pytest.mark.parametrize("motivo", ["nothing_detected", "low_confidence"])
    def test_nao_estimada_repassa_o_motivo(
        self, client: TestClient, ia: IAFalsa, motivo: str
    ) -> None:
        ia.responde(200, {"id": ID, "status": "NOT_ESTIMATED", "reason": motivo, "items": []})

        corpo = client.get(f"{ROTA}/{ID}").json()

        assert corpo["status"] == "NOT_ESTIMATED"
        assert corpo["motivo"] == motivo
        assert corpo["itens"] == []
        assert corpo["totais"]["calorias_kcal"] == 0.0

    def test_falha_da_ia_repassa_o_erro(self, client: TestClient, ia: IAFalsa) -> None:
        ia.responde(200, {"id": ID, "status": "FAILED", "error": "ServerError: 503 UNAVAILABLE"})

        corpo = client.get(f"{ROTA}/{ID}").json()

        assert corpo["status"] == "FAILED"
        assert corpo["erro"] == "ServerError: 503 UNAVAILABLE"
        assert corpo["itens"] is None

    def test_analise_inexistente_ou_expirada_da_404(self, client: TestClient, ia: IAFalsa) -> None:
        ia.responde(404, {"detail": "analysis not found"})

        assert client.get(f"{ROTA}/{ID}").status_code == 404

    def test_id_que_nao_e_uuid_da_422_sem_chamar_a_ia(
        self, client: TestClient, ia: IAFalsa
    ) -> None:
        resposta = client.get(f"{ROTA}/..%2F..%2Fhealth")

        assert resposta.status_code in (404, 422)
        assert ia.requisicoes == []
        assert client.get(f"{ROTA}/nao-e-uuid").status_code == 422

    def test_ia_fora_do_ar_na_consulta_da_503(self, client: TestClient, ia: IAFalsa) -> None:
        def _falha(_r: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("conexao recusada")

        ia.handler = _falha

        assert client.get(f"{ROTA}/{ID}").status_code == 503

    def test_resposta_inesperada_da_ia_da_503(self, client: TestClient, ia: IAFalsa) -> None:
        ia.responde(401, {"detail": "?"})

        assert client.get(f"{ROTA}/{ID}").status_code == 503
        assert client.post(ROTA, files=FOTO).status_code == 503


class TestAcesso:
    def test_exige_token(self, client: TestClient, ia: IAFalsa) -> None:
        client.headers.pop("Authorization")

        assert client.post(ROTA, files=FOTO).status_code == 401
        assert client.get(f"{ROTA}/{ID}").status_code == 401
        assert ia.requisicoes == []

    def test_so_paciente_analisa_fotos(self, client: TestClient, db: Session, ia: IAFalsa) -> None:
        factories.criar_nutricionista(db, 10)
        headers = factories.headers_de(10, "nutricionista")

        assert client.post(ROTA, files=FOTO, headers=headers).status_code == 403
        assert client.get(f"{ROTA}/{ID}", headers=headers).status_code == 403
        assert ia.requisicoes == []


def test_cliente_padrao_usa_a_url_e_o_timeout_da_configuracao() -> None:
    from app.core.config import get_settings

    settings = get_settings()
    gerador = get_cliente_ia()
    cliente = next(gerador)
    try:
        assert str(cliente.base_url).rstrip("/") == settings.AI_SERVICE_URL.rstrip("/")
        assert cliente.timeout.read == settings.AI_SERVICE_TIMEOUT_S
    finally:
        gerador.close()
