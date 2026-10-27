"""Testes do Modulo de Privacidade e Conformidade LGPD (Item 51 - RF29, RNF06, RNF07).

Valida que:
1. DTOs publicos de ranking e desafio expoem APENAS nome, avatar, pontos e streak.
2. Insercao de campos extras/sensiveis e barrada nos DTOs (extra='forbid').
3. Endpoints publicos de ranking e desafio nunca retornam calorias, peso ou refeicoes a terceiros.
4. Historicos de refeicoes e consumos de um paciente nao sao acessiveis a outros usuarios.
5. Listagem de amizades e redes sociais nao vaza metricas de saude.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.models.amizade import Amizade, StatusAmizade
from app.models.historico_xp import HistoricoXP
from app.models.paciente import Paciente
from app.models.refeicao import ItemRefeicao, Refeicao, TipoRefeicao
from app.schemas.privacidade import DesafioPublicoItem, RankingPublicoItem


@pytest.fixture
def paciente_com_dados_clinicos(db: Session) -> Paciente:
    """Paciente completo contendo triagem (peso, altura, idade, meta_kcal) e refeicoes privadas."""
    paciente = Paciente(
        id=77,
        nome="Lucas Silva",
        avatar="https://cdn.nutrivision.app/avatars/lucas.png",
        username="lucas_fit",
        streak=12,
        xp=450,
        peso_kg=Decimal("78.50"),
        altura_cm=Decimal("176.00"),
        idade=29,
        genero="masculino",
        nivel_atividade="moderado",
        meta_kcal=Decimal("2350.00"),
        origem_meta="harris_benedict",
    )
    db.add(paciente)

    # Registra refeicao com calorias detalhadas
    agora = datetime.now(UTC)
    refeicao = Refeicao(
        paciente_id=paciente.id,
        tipo=TipoRefeicao.ALMOCO,
        consumida_em=agora - timedelta(hours=3),
        criada_em=agora,
    )
    db.add(refeicao)
    db.flush()

    item1 = ItemRefeicao(
        refeicao_id=refeicao.id,
        nome_alimento="Frango Grelhado",
        quantidade_g=Decimal("180.00"),
        calorias_kcal=Decimal("297.00"),
        proteinas_g=Decimal("56.00"),
        carboidratos_g=Decimal("0.00"),
        gorduras_g=Decimal("5.50"),
    )
    item2 = ItemRefeicao(
        refeicao_id=refeicao.id,
        nome_alimento="Arroz Integral",
        quantidade_g=Decimal("120.00"),
        calorias_kcal=Decimal("150.00"),
        proteinas_g=Decimal("3.00"),
        carboidratos_g=Decimal("30.00"),
        gorduras_g=Decimal("1.20"),
    )
    db.add_all([item1, item2])

    # Concede XP na semana
    xp1 = HistoricoXP(
        paciente_id=paciente.id,
        quantidade=100,
        motivo="Meta diaria cumprida",
        criado_em=agora,
    )
    db.add(xp1)
    db.commit()
    db.refresh(paciente)
    return paciente


@pytest.fixture
def amigo_terceiro(db: Session, paciente_com_dados_clinicos: Paciente) -> Paciente:
    """Outro usuario (amigo/terceiro) que consulta o ranking ou desafio."""
    amigo = Paciente(
        id=88,
        nome="Camila Souza",
        avatar="https://cdn.nutrivision.app/avatars/camila.png",
        username="camila_run",
        streak=8,
        xp=200,
        peso_kg=Decimal("62.00"),
        altura_cm=Decimal("165.00"),
        idade=26,
        meta_kcal=Decimal("1800.00"),
    )
    db.add(amigo)

    # Vinculo de amizade aceita
    amizade = Amizade(
        pac_id=paciente_com_dados_clinicos.id,
        amigo_id=amigo.id,
        status=StatusAmizade.ACEITO,
    )
    db.add(amizade)

    agora = datetime.now(UTC)
    db.add(HistoricoXP(paciente_id=amigo.id, quantidade=60, motivo="Refeicoes", criado_em=agora))
    db.commit()
    db.refresh(amigo)
    return amigo


class TestDTOsPublicosLGPD:
    """Valida o contrato restrito dos DTOs publicos (Item 51 - RF29)."""

    def test_ranking_publico_item_expoe_estritamente_quatro_campos(self) -> None:
        """DTO de item de ranking deve conter apenas nome, avatar, pontos e streak."""
        item = RankingPublicoItem(
            nome="Arthur Conrado",
            avatar="https://nutrivision.app/avatar/arthur.jpg",
            pontos=350,
            streak=14,
        )
        dados = item.model_dump()

        # Garante exata paridade com os campos especificados
        assert set(dados.keys()) == {"nome", "avatar", "pontos", "streak"}
        assert dados["nome"] == "Arthur Conrado"
        assert dados["avatar"] == "https://nutrivision.app/avatar/arthur.jpg"
        assert dados["pontos"] == 350
        assert dados["streak"] == 14

    def test_ranking_publico_item_rejeita_campos_sensiveis_extras(self) -> None:
        """Tentativa de incluir dados sensiveis (peso, calorias) falha na validacao."""
        with pytest.raises(ValidationError):
            RankingPublicoItem(
                nome="Arthur",
                avatar=None,
                pontos=100,
                streak=5,
                peso_kg=75.0,  # Campo clinico proibido
            )

        with pytest.raises(ValidationError):
            RankingPublicoItem(
                nome="Arthur",
                avatar=None,
                pontos=100,
                streak=5,
                calorias_kcal=2000,  # Campo proibido
            )

        with pytest.raises(ValidationError):
            RankingPublicoItem(
                nome="Arthur",
                avatar=None,
                pontos=100,
                streak=5,
                refeicoes=["Almoco 500 kcal"],  # Campo proibido
            )

    def test_desafio_publico_item_expoe_estritamente_quatro_campos(self) -> None:
        """DTO de item de desafio deve conter apenas nome, avatar, pontos e streak."""
        item = DesafioPublicoItem(
            nome="Desafiante Top",
            avatar=None,
            pontos=120,
            streak=7,
        )
        dados = item.model_dump()
        assert set(dados.keys()) == {"nome", "avatar", "pontos", "streak"}

    def test_desafio_publico_item_rejeita_campos_sensiveis_extras(self) -> None:
        """Tentativa de incluir dados clinicos no DTO de desafio deve ser impedida."""
        with pytest.raises(ValidationError):
            DesafioPublicoItem(
                nome="Atleta",
                avatar=None,
                pontos=50,
                streak=3,
                meta_kcal=1900,  # Proibido
            )


class TestConformidadePrivacidadeEndpoints:
    """Valida que terceiros e outros usuarios nao recebem calorias, peso e refeicoes (Item 51)."""

    def test_ranking_publico_nao_retorna_calorias_peso_nem_refeicoes_a_terceiros(
        self,
        client: TestClient,
        paciente_com_dados_clinicos: Paciente,
        amigo_terceiro: Paciente,
    ) -> None:
        """Ao consultar o ranking publico, o terceiro nao pode ter acesso a dados de saude."""
        resp = client.get(
            f"/api/v1/privacidade/ranking-publico?paciente_id={amigo_terceiro.id}"
        )
        assert resp.status_code == 200
        dados = resp.json()

        assert "ranking" in dados
        assert dados["total_participantes"] >= 2

        # Encontra o registro correspondente ao paciente com dados clinicos
        item_lucas = next(
            (it for it in dados["ranking"] if it["nome"] == "Lucas Silva"), None
        )
        assert item_lucas is not None

        # Verifica campos autorizados
        assert set(item_lucas.keys()) == {"nome", "avatar", "pontos", "streak"}
        assert item_lucas["nome"] == "Lucas Silva"
        assert item_lucas["avatar"] == "https://cdn.nutrivision.app/avatars/lucas.png"
        assert item_lucas["pontos"] == 100
        assert item_lucas["streak"] == 12

        # Assertivas estritas de nao exposicao de saude
        campos_proibidos = [
            "peso",
            "peso_kg",
            "altura",
            "altura_cm",
            "idade",
            "genero",
            "nivel_atividade",
            "meta_kcal",
            "origem_meta",
            "calorias",
            "calorias_kcal",
            "refeicao",
            "refeicoes",
            "itens",
            "carboidratos_g",
            "proteinas_g",
            "gorduras_g",
            "tmb_kcal",
        ]
        for campo in campos_proibidos:
            assert campo not in item_lucas, f"Campo sensivel '{campo}' vazou no ranking publico!"

    def test_ranking_publico_via_gamificacao_router_tem_mesma_protecao(
        self,
        client: TestClient,
        amigo_terceiro: Paciente,
    ) -> None:
        """Alias /api/v1/gamificacao/ranking-publico segue a mesma conformidade LGPD."""
        resp = client.get(
            f"/api/v1/gamificacao/ranking-publico?paciente_id={amigo_terceiro.id}"
        )
        assert resp.status_code == 200
        item = resp.json()["ranking"][0]
        assert set(item.keys()) == {"nome", "avatar", "pontos", "streak"}
        assert "calorias" not in item
        assert "peso_kg" not in item
        assert "refeicoes" not in item

    def test_desafio_publico_nao_retorna_calorias_peso_nem_refeicoes(
        self,
        client: TestClient,
        paciente_com_dados_clinicos: Paciente,
        amigo_terceiro: Paciente,
    ) -> None:
        """Placar publico de desafios em grupo nao expoem calorias, peso nem refeicoes."""
        pids = f"{paciente_com_dados_clinicos.id},{amigo_terceiro.id}"
        resp = client.get(
            f"/api/v1/privacidade/desafios/10/publico?participantes={pids}&titulo=Desafio 7 Dias"
        )
        assert resp.status_code == 200
        dados = resp.json()

        assert dados["desafio_id"] == 10
        assert dados["titulo"] == "Desafio 7 Dias"
        assert dados["total_participantes"] == 2

        for part in dados["participantes"]:
            assert set(part.keys()) == {"nome", "avatar", "pontos", "streak"}
            assert "peso_kg" not in part
            assert "calorias" not in part
            assert "calorias_kcal" not in part
            assert "meta_kcal" not in part
            assert "refeicoes" not in part

    def test_desafio_publico_via_gamificacao_router_tem_mesma_protecao(
        self,
        client: TestClient,
        paciente_com_dados_clinicos: Paciente,
    ) -> None:
        """Alias /api/v1/gamificacao/desafios/{id}/publico preserva LGPD."""
        resp = client.get(
            f"/api/v1/gamificacao/desafios/5/publico?participantes={paciente_com_dados_clinicos.id}"
        )
        assert resp.status_code == 200
        item = resp.json()["participantes"][0]
        assert set(item.keys()) == {"nome", "avatar", "pontos", "streak"}
        assert "calorias" not in item
        assert "peso" not in item

    def test_terceiros_nao_recebem_refeicoes_de_outros_usuarios(
        self,
        client: TestClient,
        paciente_com_dados_clinicos: Paciente,
        amigo_terceiro: Paciente,
    ) -> None:
        """Ao listar refeicoes como amigo_terceiro, nao traz refeicoes do paciente 77."""
        resp = client.get(f"/api/v1/refeicoes?paciente_id={amigo_terceiro.id}")
        assert resp.status_code == 200
        refeicoes = resp.json()

        # O amigo terceiro nao tem refeicoes cadastradas
        assert len(refeicoes) == 0

        # Nenhuma refeicao do paciente com dados clinicos vazou
        for ref in refeicoes:
            assert ref["paciente_id"] != paciente_com_dados_clinicos.id

    def test_lista_de_amigos_social_nao_expoe_calorias_nem_peso(
        self,
        client: TestClient,
        amigo_terceiro: Paciente,
    ) -> None:
        """Endpoint de amizades expoe dados sociais e exclui metricas clinicas."""
        resp = client.get(f"/api/v1/amizades?paciente_id={amigo_terceiro.id}")
        assert resp.status_code == 200
        amigos = resp.json()
        assert len(amigos) == 1

        amigo = amigos[0]
        assert "username" in amigo
        assert "streak" in amigo

        # Dados de saude proibidos
        assert "peso_kg" not in amigo
        assert "calorias" not in amigo
        assert "meta_kcal" not in amigo
        assert "refeicoes" not in amigo
