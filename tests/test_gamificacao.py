"""Testes do fechamento diario de streak/XP e Leaderboard Semanal (RF05, RF16, RF29)."""

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.amizade import Amizade, StatusAmizade
from app.models.historico_xp import HistoricoXP
from app.models.paciente import Paciente
from app.models.refeicao import ItemRefeicao, Refeicao, TipoRefeicao
from app.services.gamificacao import (
    FUSO_HORARIO,
    XP_POR_DIA,
    PacienteNaoEncontrado,
    conceder_xp,
    janela_semanal,
    processar_gamificacao_diaria,
)
from tests import factories

DIA = date(2026, 10, 12)


def _criar_paciente_social(
    db: Session, pid: int, username: str, streak: int = 0, xp: int = 0
) -> Paciente:
    p = factories.criar_paciente(db, pid)
    p.username = username
    p.streak = streak
    p.xp = xp
    db.commit()
    db.refresh(p)
    return p


@pytest.fixture
def paciente_principal(db: Session) -> Paciente:
    return _criar_paciente_social(db, 10, "heroi_nutri", streak=7, xp=0)


class TestJanelaSemanal:
    def test_calcula_segunda_a_domingo_no_fuso_local(self) -> None:
        # 2026-10-28 e uma quarta-feira
        quarta = datetime(2026, 10, 28, 14, 30, tzinfo=UTC)
        inicio, fim = janela_semanal(quarta)

        # Segunda 2026-10-26 00:00 e domingo 2026-11-01 23:59:59 em Sao Paulo
        assert inicio.astimezone(FUSO_HORARIO) == datetime(2026, 10, 26, tzinfo=FUSO_HORARIO)
        assert inicio.tzinfo == UTC
        fim_local = fim.astimezone(FUSO_HORARIO)
        assert (fim_local.date(), fim_local.hour, fim_local.minute) == (date(2026, 11, 1), 23, 59)

    def test_domingo_a_noite_ainda_e_a_mesma_semana(self) -> None:
        # Domingo 22h em Sao Paulo ja e segunda em UTC (B5)
        domingo = datetime(2026, 11, 1, 22, 0, tzinfo=FUSO_HORARIO)
        inicio, _ = janela_semanal(domingo)
        assert inicio.astimezone(FUSO_HORARIO).date() == date(2026, 10, 26)


class TestConcessaoXP:
    def test_concede_xp_e_acumula_saldo(self, db: Session, paciente_principal: Paciente) -> None:
        registro = conceder_xp(db, paciente_principal.id, 50, "meta_diaria")

        assert registro.quantidade == 50
        assert registro.motivo == "meta_diaria"
        db.expire_all()
        paciente_atualizado = db.get(Paciente, paciente_principal.id)
        assert paciente_atualizado is not None
        assert paciente_atualizado.xp == 50

    def test_paciente_inexistente(self, db: Session) -> None:
        with pytest.raises(PacienteNaoEncontrado):
            conceder_xp(db, 9999, 50, "teste")

    def test_historico_e_do_paciente_autenticado(
        self, client: TestClient, db: Session, paciente_principal: Paciente
    ) -> None:
        outro = _criar_paciente_social(db, 20, "outro")
        conceder_xp(db, paciente_principal.id, 30, "refeicao")
        conceder_xp(db, outro.id, 99, "refeicao")

        resposta = client.get(
            "/api/v1/gamificacao/historico-xp?paciente_id=20",
            headers=factories.headers_de(paciente_principal.id),
        )

        assert resposta.status_code == 200
        assert [r["quantidade"] for r in resposta.json()] == [30]


class TestLeaderboardSemanal:
    def test_leaderboard_usuario_solitario(
        self, client: TestClient, paciente_principal: Paciente
    ) -> None:
        resposta = client.get(
            "/api/v1/gamificacao/leaderboard", headers=factories.headers_de(paciente_principal.id)
        )
        assert resposta.status_code == 200
        dados = resposta.json()
        assert dados["total_participantes"] == 1
        assert dados["posicao_solicitante"] == 1
        assert len(dados["ranking"]) == 1
        item = dados["ranking"][0]
        assert item["posicao"] == 1
        assert item["paciente_id"] == paciente_principal.id
        assert item["username"] == "heroi_nutri"
        assert item["xp_semanal"] == 0
        assert item["e_voce"] is True

    def test_leaderboard_ordena_amigos_por_ganho_semanal_e_desempata_por_streak(
        self, client: TestClient, db: Session, paciente_principal: Paciente
    ) -> None:
        # Cria 3 amigos
        amigo1 = _criar_paciente_social(db, 11, "amigo_ouro", streak=15, xp=0)
        amigo2 = _criar_paciente_social(db, 12, "amigo_prata", streak=5, xp=0)
        amigo3 = _criar_paciente_social(db, 13, "amigo_bronze", streak=10, xp=0)

        # Cria amizades com status 'aceito'
        db.add_all(
            [
                Amizade(
                    pac_id=paciente_principal.id,
                    amigo_id=amigo1.id,
                    status=StatusAmizade.ACEITO,
                ),
                Amizade(
                    pac_id=paciente_principal.id,
                    amigo_id=amigo2.id,
                    status=StatusAmizade.ACEITO,
                ),
                Amizade(
                    pac_id=paciente_principal.id,
                    amigo_id=amigo3.id,
                    status=StatusAmizade.ACEITO,
                ),
            ]
        )
        db.commit()

        agora = datetime.now(UTC)
        inicio_semana, _ = janela_semanal(agora)

        # amigo1 ganha 100 XP esta semana
        # paciente_principal ganha 80 XP esta semana
        # amigo2 ganha 50 XP esta semana
        # amigo3 ganha 50 XP esta semana (empata em XP, mas streak 10 > 5 de amigo2)
        # amigo2 também tem 200 XP de duas semanas atrás (não deve contar nesta semana)
        duas_semanas_atras = inicio_semana - timedelta(days=14)

        db.add_all(
            [
                HistoricoXP(
                    paciente_id=amigo1.id,
                    quantidade=100,
                    motivo="desafio",
                    criado_em=agora,
                ),
                HistoricoXP(
                    paciente_id=paciente_principal.id,
                    quantidade=80,
                    motivo="meta_diaria",
                    criado_em=agora,
                ),
                HistoricoXP(
                    paciente_id=amigo2.id,
                    quantidade=50,
                    motivo="registro",
                    criado_em=agora,
                ),
                HistoricoXP(
                    paciente_id=amigo2.id,
                    quantidade=200,
                    motivo="xp_antigo",
                    criado_em=duas_semanas_atras,
                ),
                HistoricoXP(
                    paciente_id=amigo3.id,
                    quantidade=50,
                    motivo="registro",
                    criado_em=agora,
                ),
            ]
        )
        db.commit()

        resp = client.get(
            "/api/v1/gamificacao/leaderboard", headers=factories.headers_de(paciente_principal.id)
        )
        assert resp.status_code == 200
        dados = resp.json()
        assert dados["total_participantes"] == 4
        assert dados["posicao_solicitante"] == 2

        ranking = dados["ranking"]
        assert len(ranking) == 4

        # 1o lugar: amigo1 (100 XP)
        assert ranking[0]["paciente_id"] == amigo1.id
        assert ranking[0]["posicao"] == 1
        assert ranking[0]["xp_semanal"] == 100

        # 2o lugar: paciente_principal (80 XP)
        assert ranking[1]["paciente_id"] == paciente_principal.id
        assert ranking[1]["posicao"] == 2
        assert ranking[1]["xp_semanal"] == 80
        assert ranking[1]["e_voce"] is True

        # 3o lugar: amigo3 (50 XP, streak 10 desempata na frente de amigo2 com streak 5)
        assert ranking[2]["paciente_id"] == amigo3.id
        assert ranking[2]["posicao"] == 3
        assert ranking[2]["xp_semanal"] == 50
        assert ranking[2]["streak"] == 10

        # 4o lugar: amigo2 (50 XP, streak 5)
        assert ranking[3]["paciente_id"] == amigo2.id
        assert ranking[3]["posicao"] == 4
        assert ranking[3]["xp_semanal"] == 50
        assert ranking[3]["streak"] == 5

    def test_ignora_amizades_pendentes_ou_recusadas(
        self, client: TestClient, db: Session, paciente_principal: Paciente
    ) -> None:
        amigo_pendente = _criar_paciente_social(db, 21, "amigo_pendente", streak=10, xp=0)
        amigo_recusado = _criar_paciente_social(db, 22, "amigo_recusado", streak=10, xp=0)
        db.add_all(
            [
                Amizade(
                    pac_id=paciente_principal.id,
                    amigo_id=amigo_pendente.id,
                    status=StatusAmizade.PENDENTE,
                ),
                Amizade(
                    pac_id=paciente_principal.id,
                    amigo_id=amigo_recusado.id,
                    status=StatusAmizade.RECUSADO,
                ),
            ]
        )
        db.commit()

        # Dá XP ao pendente
        db.add(
            HistoricoXP(
                paciente_id=amigo_pendente.id,
                quantidade=500,
                motivo="teste",
                criado_em=datetime.now(UTC),
            )
        )
        db.commit()

        resp = client.get(
            "/api/v1/gamificacao/leaderboard", headers=factories.headers_de(paciente_principal.id)
        )
        assert resp.status_code == 200
        dados = resp.json()
        # Apenas paciente_principal deve estar no ranking
        assert dados["total_participantes"] == 1
        assert dados["ranking"][0]["paciente_id"] == paciente_principal.id

    def test_limite_top_10(
        self, client: TestClient, db: Session, paciente_principal: Paciente
    ) -> None:
        # Cria 15 amigos aceitos
        agora = datetime.now(UTC)
        for i in range(1, 16):
            amigo = _criar_paciente_social(db, 100 + i, f"amigo_{i}", streak=i, xp=0)
            db.add(
                Amizade(
                    pac_id=paciente_principal.id,
                    amigo_id=amigo.id,
                    status=StatusAmizade.ACEITO,
                )
            )
            db.add(
                HistoricoXP(
                    paciente_id=amigo.id,
                    quantidade=i * 10,
                    motivo="teste",
                    criado_em=agora,
                )
            )
        db.commit()

        resp = client.get(
            "/api/v1/gamificacao/leaderboard", headers=factories.headers_de(paciente_principal.id)
        )
        assert resp.status_code == 200
        dados = resp.json()
        assert dados["total_participantes"] == 16  # 15 amigos + 1 principal
        assert len(dados["ranking"]) == 10  # Top 10 respeitado por padrão

    def test_conformidade_lgpd_rf29_nao_expoe_dados_sensiveis(
        self, client: TestClient, db: Session, paciente_principal: Paciente
    ) -> None:
        """RF-29: O placar deve restringir exposicao a dados nao sensiveis (pontos, streak)."""
        resp = client.get(
            "/api/v1/gamificacao/leaderboard", headers=factories.headers_de(paciente_principal.id)
        )
        assert resp.status_code == 200
        item = resp.json()["ranking"][0]

        # Campos autorizados
        assert set(item.keys()) == {
            "posicao",
            "paciente_id",
            "username",
            "xp_semanal",
            "streak",
            "e_voce",
        }

        # Garante que dados clínicos ou sensíveis não vazam
        assert "peso_kg" not in item
        assert "altura_cm" not in item
        assert "idade" not in item
        assert "meta_kcal" not in item
        assert "refeicoes" not in item


def _paciente(db: Session, paciente_id: int = 1, meta: str | None = "2000") -> Paciente:
    paciente = factories.criar_paciente(db, paciente_id)
    paciente.meta_kcal = Decimal(meta) if meta is not None else None
    db.commit()
    return paciente


def _refeicao(db: Session, paciente_id: int, hora: int, kcal: str, dia: date = DIA) -> None:
    db.add(
        Refeicao(
            paciente_id=paciente_id,
            consumida_em=datetime.combine(dia, time(hora), tzinfo=FUSO_HORARIO),
            tipo=TipoRefeicao.LANCHE.value,
            itens=[
                ItemRefeicao(
                    nome_alimento="Item",
                    quantidade_g=Decimal("100"),
                    calorias_kcal=Decimal(kcal),
                    proteinas_g=Decimal("0"),
                    carboidratos_g=Decimal("0"),
                    gorduras_g=Decimal("0"),
                )
            ],
        )
    )
    db.commit()


def test_dia_valido_soma_streak_e_xp(db: Session) -> None:
    paciente = _paciente(db)
    _refeicao(db, 1, 8, "900")
    _refeicao(db, 1, 12, "1000")  # 1900 kcal: dentro de 30% da meta de 2000

    assert processar_gamificacao_diaria(db, DIA) == 1

    assert paciente.streak == 1
    assert paciente.xp == XP_POR_DIA
    assert paciente.gamificacao_processada_em == DIA


def test_uma_refeicao_so_zera_streak_e_mantem_xp(db: Session) -> None:
    paciente = _paciente(db)
    paciente.streak, paciente.xp = 3, 150
    db.commit()
    _refeicao(db, 1, 8, "200")

    processar_gamificacao_diaria(db, DIA)

    assert paciente.streak == 0
    assert paciente.xp == 150


def test_acima_do_limite_da_meta_zera_streak(db: Session) -> None:
    paciente = _paciente(db)
    paciente.streak = 2
    db.commit()
    _refeicao(db, 1, 8, "1500")
    _refeicao(db, 1, 12, "1300")  # 2800 kcal > 2600 (meta + 30%)

    processar_gamificacao_diaria(db, DIA)

    assert paciente.streak == 0


def test_abaixo_do_limite_da_meta_zera_streak(db: Session) -> None:
    """Comer muito menos que a meta tambem nao e dia dentro da meta."""
    paciente = _paciente(db)
    paciente.streak = 2
    db.commit()
    _refeicao(db, 1, 8, "200")
    _refeicao(db, 1, 12, "300")  # 500 kcal < 1400 (meta - 30%)

    processar_gamificacao_diaria(db, DIA)

    assert paciente.streak == 0


def test_dia_valido_grava_historico_de_xp(db: Session) -> None:
    paciente = _paciente(db)
    _refeicao(db, 1, 8, "1000")
    _refeicao(db, 1, 12, "1000")

    processar_gamificacao_diaria(db, DIA)

    historico = db.query(HistoricoXP).filter_by(paciente_id=paciente.id).all()
    assert [(h.quantidade, h.motivo) for h in historico] == [(XP_POR_DIA, f"meta_diaria:{DIA}")]


def test_paciente_sem_meta_nao_cumpre(db: Session) -> None:
    paciente = _paciente(db, meta=None)
    _refeicao(db, 1, 8, "100")
    _refeicao(db, 1, 12, "100")

    processar_gamificacao_diaria(db, DIA)

    assert paciente.streak == 0
    assert paciente.xp == 0


def test_considera_o_dia_no_fuso_de_sao_paulo(db: Session) -> None:
    paciente = _paciente(db)
    # 22h em Sao Paulo ja e o dia seguinte em UTC, mas conta para DIA.
    _refeicao(db, 1, 21, "1000")
    _refeicao(db, 1, 22, "1000")

    processar_gamificacao_diaria(db, DIA)

    assert paciente.streak == 1


def test_rodar_duas_vezes_no_mesmo_dia_nao_credita_de_novo(db: Session) -> None:
    paciente = _paciente(db)
    _refeicao(db, 1, 8, "1000")
    _refeicao(db, 1, 12, "1000")

    processar_gamificacao_diaria(db, DIA)
    assert processar_gamificacao_diaria(db, DIA) == 0

    assert paciente.streak == 1
    assert paciente.xp == XP_POR_DIA


def test_resgate_e_consumo_no_fechamento(client: TestClient, db: Session) -> None:
    paciente = _paciente(db)
    paciente.streak, paciente.xp = 3, 100
    db.commit()
    headers = factories.headers_de(paciente.id)
    url = "/api/v1/gamificacao"

    compra = client.post(f"{url}/bloqueios", headers=headers)
    assert compra.status_code == 200
    assert compra.json() == {"streak": 3, "xp": 0, "bloqueios_perda": 1, "custo_bloqueio_xp": 100}
    assert client.post(f"{url}/bloqueios", headers=headers).status_code == 409
    assert client.get(url, headers=headers).json() == compra.json()

    assert processar_gamificacao_diaria(db, DIA) == 1
    assert processar_gamificacao_diaria(db, DIA) == 0
    assert (paciente.streak, paciente.xp, paciente.bloqueios_perda) == (3, 0, 0)


def test_dia_valido_nao_consume_bloqueio(db: Session) -> None:
    paciente = _paciente(db)
    paciente.streak, paciente.bloqueios_perda = 2, 1
    db.commit()
    _refeicao(db, 1, 8, "1000")
    _refeicao(db, 1, 12, "1000")

    processar_gamificacao_diaria(db, DIA)

    assert (paciente.streak, paciente.xp, paciente.bloqueios_perda) == (3, XP_POR_DIA, 1)


def test_falha_sem_ofensiva_nao_consome_bloqueio(db: Session) -> None:
    paciente = _paciente(db)
    paciente.bloqueios_perda = 1
    db.commit()

    processar_gamificacao_diaria(db, DIA)

    assert (paciente.streak, paciente.xp, paciente.bloqueios_perda) == (0, 0, 1)


def test_resgate_exige_paciente_autenticado(client: TestClient, db: Session) -> None:
    nutri = factories.criar_nutricionista(db, 2)
    url = "/api/v1/gamificacao/bloqueios"
    assert client.post(url).status_code == 401
    assert (
        client.post(url, headers=factories.headers_de(nutri.id, "nutricionista")).status_code == 403
    )
