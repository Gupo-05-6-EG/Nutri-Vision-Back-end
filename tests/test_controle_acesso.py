"""Testes de autorizacao por endpoint: perfil e vinculo (Task 1.6, RNF06).

Cenario fixo:

- pacientes 1 e 2
- nutricionista 10, com vinculo com o paciente 1 (e so com ele)
- nutricionista 11, sem vinculo nenhum

Regras testadas:

- sem token valido -> 401, em todo endpoint protegido;
- leitura dos dados de um paciente: o proprio paciente ou nutricionista vinculado;
- escrita nos dados de um paciente: so o proprio paciente;
- sem acesso -> 403, mesmo que o paciente nao exista.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.alimento_taco import AlimentoTaco
from app.models.paciente import Paciente
from app.models.refeicao import ItemRefeicao, Refeicao, TipoRefeicao
from app.models.vinculo import Vinculo
from tests import factories

API = "/api/v1"
PACIENTE_1, PACIENTE_2, NUTRI_VINCULADO, NUTRI_SEM_VINCULO = 1, 2, 10, 11

TRIAGEM = {
    "peso_kg": 80,
    "altura_cm": 180,
    "idade": 30,
    "genero": "masculino",
    "nivel_atividade": "moderado",
}
LEMBRETES = {"lembretes": [{"tipo": "almoco", "horario": "12:00"}]}
DIA = (datetime.now(UTC) - timedelta(hours=2)).date().isoformat()


def como(usuario_id: int) -> dict[str, str]:
    perfil = "nutricionista" if usuario_id >= NUTRI_VINCULADO else "paciente"
    return factories.headers_de(usuario_id, perfil)


@pytest.fixture(autouse=True)
def _cenario(db: Session) -> None:
    factories.criar_paciente(db, PACIENTE_1)
    factories.criar_paciente(db, PACIENTE_2)
    factories.criar_nutricionista(db, NUTRI_VINCULADO)
    factories.criar_nutricionista(db, NUTRI_SEM_VINCULO)
    db.add(Vinculo(status="ativo", nutricionista_id=NUTRI_VINCULADO, paciente_id=PACIENTE_1))
    db.add(
        AlimentoTaco(
            nome="Bolo de teste",
            categoria="Teste",
            kcal_100g=Decimal("300"),
            carbs_100g=Decimal("50"),
            prot_100g=Decimal("5"),
            gord_100g=Decimal("10"),
        )
    )
    db.commit()


@pytest.fixture
def refeicao_id(db: Session) -> int:
    """Refeicao do paciente 1, criada direto no banco."""
    refeicao = Refeicao(
        paciente_id=PACIENTE_1,
        consumida_em=datetime.now(UTC) - timedelta(hours=1),
        tipo=TipoRefeicao.ALMOCO.value,
        itens=[
            ItemRefeicao(
                nome_alimento="Arroz",
                quantidade_g=Decimal("100"),
                calorias_kcal=Decimal("128"),
                proteinas_g=Decimal("2.5"),
                carboidratos_g=Decimal("28"),
                gorduras_g=Decimal("0.2"),
            )
        ],
    )
    db.add(refeicao)
    db.commit()
    return refeicao.id


def _status(client: TestClient, metodo: str, rota: str, usuario_id: int | None, **kw: Any) -> int:
    headers = como(usuario_id) if usuario_id is not None else {}
    return client.request(metodo, API + rota, headers=headers, **kw).status_code


# ---------------------------------------------------------------- sem autenticacao


def _requisicoes_protegidas(refeicao_id: int) -> list[tuple[str, str, dict[str, Any]]]:
    return [
        ("POST", "/linking-code", {}),
        ("POST", "/link", {"json": {"codigo": "123456"}}),
        ("GET", "/auth/me", {}),
        ("POST", f"/pacientes/{PACIENTE_1}/triagem", {"json": TRIAGEM}),
        ("GET", f"/pacientes/{PACIENTE_1}/lembretes-refeicao", {}),
        ("PUT", f"/pacientes/{PACIENTE_1}/lembretes-refeicao", {"json": LEMBRETES}),
        ("PUT", f"/pacientes/{PACIENTE_1}/dispositivos-push", {"json": {"token": "abc"}}),
        ("POST", "/refeicoes", {"json": factories.refeicao(PACIENTE_1)}),
        ("GET", "/refeicoes", {"params": {"paciente_id": PACIENTE_1}}),
        ("GET", "/refeicoes/consumo-diario", {"params": {"paciente_id": 1, "data": DIA}}),
        ("GET", f"/refeicoes/{refeicao_id}", {}),
        ("PUT", f"/refeicoes/{refeicao_id}", {"json": {"observacao": "x"}}),
        ("DELETE", f"/refeicoes/{refeicao_id}", {}),
        ("POST", "/alimentos-personalizados", {"json": _alimento_personalizado(PACIENTE_1)}),
        ("GET", "/alimentos", {"params": {"nome": "bolo"}}),
        ("GET", "/alimentos-taco", {"params": {"nome": "bolo"}}),
        ("POST", "/calculo-nutricional", {"json": {"itens": []}}),
    ]


def _alimento_personalizado(paciente_id: int) -> dict[str, Any]:
    return {
        "paciente_id": paciente_id,
        "nome": f"Receita do paciente {paciente_id}",
        "kcal_100g": "200",
        "carbs_100g": "20",
        "prot_100g": "10",
        "gord_100g": "5",
    }


def test_endpoints_protegidos_exigem_token(client: TestClient, refeicao_id: int) -> None:
    for metodo, rota, kwargs in _requisicoes_protegidas(refeicao_id):
        resposta = client.request(metodo, API + rota, **kwargs)
        assert resposta.status_code == 401, f"{metodo} {rota} -> {resposta.status_code}"
        assert resposta.headers["www-authenticate"] == "Bearer"


def test_endpoints_publicos_seguem_abertos(client: TestClient) -> None:
    assert client.get(f"{API}/health").status_code == 200
    login = client.post(f"{API}/auth/login", json={"email": "x@x.com", "senha": "qualquer"})
    assert login.status_code == 401  # credencial errada, nao falta de token


def test_perfil_vem_do_banco_e_nao_do_token(client: TestClient) -> None:
    """Paciente com token dizendo `nutricionista` nao ganha acesso a dados de outro."""
    headers = factories.headers_de(PACIENTE_2, "nutricionista")

    resposta = client.get(f"{API}/refeicoes", params={"paciente_id": PACIENTE_1}, headers=headers)

    assert resposta.status_code == 403


# ---------------------------------------------------------------- triagem e lembretes
# Escrita: so o proprio paciente.

ESCRITAS_DO_PACIENTE: list[tuple[str, str, dict[str, Any]]] = [
    ("POST", "/pacientes/{id}/triagem", {"json": TRIAGEM}),
    ("GET", "/pacientes/{id}/lembretes-refeicao", {}),
    ("PUT", "/pacientes/{id}/lembretes-refeicao", {"json": LEMBRETES}),
    ("PUT", "/pacientes/{id}/dispositivos-push", {"json": {"token": "abc"}}),
]


@pytest.mark.parametrize(("metodo", "rota", "kwargs"), ESCRITAS_DO_PACIENTE)
class TestSoOProprioPaciente:
    def test_proprio_paciente_passa(
        self, client: TestClient, metodo: str, rota: str, kwargs: dict[str, Any]
    ) -> None:
        status = _status(client, metodo, rota.format(id=PACIENTE_1), PACIENTE_1, **kwargs)

        assert status in (200, 204)

    @pytest.mark.parametrize(
        "usuario_id", [PACIENTE_2, NUTRI_VINCULADO, NUTRI_SEM_VINCULO], ids=["outro", "vinc", "sem"]
    )
    def test_outros_levam_403(
        self,
        client: TestClient,
        metodo: str,
        rota: str,
        kwargs: dict[str, Any],
        usuario_id: int,
    ) -> None:
        assert _status(client, metodo, rota.format(id=PACIENTE_1), usuario_id, **kwargs) == 403

    def test_paciente_inexistente_tambem_leva_403(
        self, client: TestClient, metodo: str, rota: str, kwargs: dict[str, Any]
    ) -> None:
        assert _status(client, metodo, rota.format(id=999), PACIENTE_1, **kwargs) == 403

    def test_id_invalido_continua_422(
        self, client: TestClient, metodo: str, rota: str, kwargs: dict[str, Any]
    ) -> None:
        assert _status(client, metodo, rota.format(id=0), PACIENTE_1, **kwargs) == 422


def test_triagem_negada_nao_altera_o_paciente(client: TestClient, db: Session) -> None:
    _status(client, "POST", f"/pacientes/{PACIENTE_1}/triagem", NUTRI_VINCULADO, json=TRIAGEM)

    db.expire_all()
    assert db.get(Paciente, PACIENTE_1).meta_kcal is None


# ---------------------------------------------------------------- refeicoes


class TestRefeicoesLeitura:
    """Leitura: o proprio paciente ou nutricionista vinculado."""

    def _rotas(self, refeicao_id: int) -> list[tuple[str, dict[str, Any]]]:
        return [
            ("/refeicoes", {"params": {"paciente_id": PACIENTE_1}}),
            ("/refeicoes/consumo-diario", {"params": {"paciente_id": 1, "data": DIA}}),
            (f"/refeicoes/{refeicao_id}", {}),
        ]

    @pytest.mark.parametrize("usuario_id", [PACIENTE_1, NUTRI_VINCULADO], ids=["dono", "vinc"])
    def test_dono_e_nutricionista_vinculado_leem(
        self, client: TestClient, refeicao_id: int, usuario_id: int
    ) -> None:
        for rota, kwargs in self._rotas(refeicao_id):
            assert _status(client, "GET", rota, usuario_id, **kwargs) == 200, rota

    @pytest.mark.parametrize("usuario_id", [PACIENTE_2, NUTRI_SEM_VINCULO], ids=["outro", "sem"])
    def test_outros_levam_403(self, client: TestClient, refeicao_id: int, usuario_id: int) -> None:
        for rota, kwargs in self._rotas(refeicao_id):
            assert _status(client, "GET", rota, usuario_id, **kwargs) == 403, rota

    def test_vinculo_com_um_paciente_nao_vale_para_outro(self, client: TestClient) -> None:
        params = {"paciente_id": PACIENTE_2}

        assert _status(client, "GET", "/refeicoes", NUTRI_VINCULADO, params=params) == 403

    def test_403_nao_vaza_dados(self, client: TestClient, refeicao_id: int) -> None:
        resposta = client.get(f"{API}/refeicoes/{refeicao_id}", headers=como(PACIENTE_2))

        assert resposta.status_code == 403
        assert "Arroz" not in resposta.text

    def test_refeicao_inexistente_segue_404_para_quem_esta_logado(self, client: TestClient) -> None:
        assert _status(client, "GET", "/refeicoes/99999", PACIENTE_1) == 404


class TestRefeicoesEscrita:
    """Escrita: so o proprio paciente (nutricionista, mesmo vinculado, so le)."""

    def test_paciente_registra_a_propria_refeicao(self, client: TestClient) -> None:
        corpo = factories.refeicao(PACIENTE_1)

        assert _status(client, "POST", "/refeicoes", PACIENTE_1, json=corpo) == 201

    @pytest.mark.parametrize(
        "usuario_id", [PACIENTE_2, NUTRI_VINCULADO, NUTRI_SEM_VINCULO], ids=["outro", "vinc", "sem"]
    )
    def test_ninguem_registra_refeicao_de_outro_paciente(
        self, client: TestClient, db: Session, usuario_id: int
    ) -> None:
        corpo = factories.refeicao(PACIENTE_1)

        assert _status(client, "POST", "/refeicoes", usuario_id, json=corpo) == 403
        assert db.query(Refeicao).count() == 0

    def test_paciente_edita_e_remove_a_propria_refeicao(
        self, client: TestClient, refeicao_id: int
    ) -> None:
        rota = f"/refeicoes/{refeicao_id}"

        assert _status(client, "PUT", rota, PACIENTE_1, json={"observacao": "ok"}) == 200
        assert _status(client, "DELETE", rota, PACIENTE_1) == 204

    @pytest.mark.parametrize(
        "usuario_id", [PACIENTE_2, NUTRI_VINCULADO, NUTRI_SEM_VINCULO], ids=["outro", "vinc", "sem"]
    )
    def test_ninguem_edita_ou_remove_refeicao_de_outro_paciente(
        self, client: TestClient, db: Session, refeicao_id: int, usuario_id: int
    ) -> None:
        rota = f"/refeicoes/{refeicao_id}"

        assert _status(client, "PUT", rota, usuario_id, json={"observacao": "x"}) == 403
        assert _status(client, "DELETE", rota, usuario_id) == 403
        db.expire_all()
        refeicao = db.get(Refeicao, refeicao_id)
        assert refeicao is not None
        assert refeicao.observacao is None


# ---------------------------------------------------------------- alimentos


class TestAlimentos:
    def test_paciente_cadastra_o_proprio_alimento(self, client: TestClient) -> None:
        corpo = _alimento_personalizado(PACIENTE_1)

        assert _status(client, "POST", "/alimentos-personalizados", PACIENTE_1, json=corpo) == 201

    @pytest.mark.parametrize(
        "usuario_id", [PACIENTE_2, NUTRI_VINCULADO, NUTRI_SEM_VINCULO], ids=["outro", "vinc", "sem"]
    )
    def test_ninguem_cadastra_alimento_para_outro_paciente(
        self, client: TestClient, usuario_id: int
    ) -> None:
        corpo = _alimento_personalizado(PACIENTE_1)

        assert _status(client, "POST", "/alimentos-personalizados", usuario_id, json=corpo) == 403

    @pytest.mark.parametrize("usuario_id", [PACIENTE_1, NUTRI_VINCULADO], ids=["dono", "vinc"])
    def test_busca_com_paciente_id_para_dono_e_vinculado(
        self, client: TestClient, usuario_id: int
    ) -> None:
        params = {"nome": "bolo", "paciente_id": PACIENTE_1}

        assert _status(client, "GET", "/alimentos", usuario_id, params=params) == 200

    @pytest.mark.parametrize("usuario_id", [PACIENTE_2, NUTRI_SEM_VINCULO], ids=["outro", "sem"])
    def test_busca_com_paciente_id_de_outro_leva_403(
        self, client: TestClient, usuario_id: int
    ) -> None:
        params = {"nome": "bolo", "paciente_id": PACIENTE_1}

        assert _status(client, "GET", "/alimentos", usuario_id, params=params) == 403

    @pytest.mark.parametrize("usuario_id", [PACIENTE_1, NUTRI_VINCULADO, NUTRI_SEM_VINCULO])
    def test_busca_so_na_taco_vale_para_qualquer_usuario_logado(
        self, client: TestClient, usuario_id: int
    ) -> None:
        assert _status(client, "GET", "/alimentos", usuario_id, params={"nome": "bolo"}) == 200
        assert _status(client, "GET", "/alimentos-taco", usuario_id, params={"nome": "bolo"}) == 200

    @pytest.mark.parametrize("usuario_id", [PACIENTE_1, NUTRI_VINCULADO])
    def test_calculo_nutricional_vale_para_qualquer_perfil(
        self, client: TestClient, usuario_id: int
    ) -> None:
        # Corpo vazio de itens e invalido (422), mas so chega na validacao quem esta logado.
        assert (
            _status(client, "POST", "/calculo-nutricional", usuario_id, json={"itens": []}) == 422
        )
