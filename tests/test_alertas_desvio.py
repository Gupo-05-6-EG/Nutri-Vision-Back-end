"""Testes do job diario e endpoints de alertas de desvio de meta (Task 5.4, RF10.2)."""

from datetime import date, datetime, time, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.plano_alimentar import AlimentoRefeicaoPlano, PlanoAlimentar, RefeicaoPlano
from app.models.refeicao import ItemRefeicao, Refeicao
from app.models.vinculo import Vinculo
from app.services.alertas_desvio import processar_alertas_desvio_diario
from app.services.gamificacao import FUSO_HORARIO
from tests.factories import criar_nutricionista, criar_paciente, headers_de


def _registrar_consumo_dia(db: Session, paciente_id: int, dia: date, kcal: str) -> None:
    instante = datetime.combine(dia, time(12, 30), tzinfo=FUSO_HORARIO)
    db.add(
        Refeicao(
            paciente_id=paciente_id,
            consumida_em=instante,
            tipo="almoco",
            itens=[
                ItemRefeicao(
                    nome_alimento="Prato executivo",
                    quantidade_g=Decimal("400.00"),
                    calorias_kcal=Decimal(kcal),
                    proteinas_g=Decimal("35.00"),
                    carboidratos_g=Decimal("60.00"),
                    gorduras_g=Decimal("15.00"),
                )
            ],
        )
    )
    db.commit()


def test_regra_padrao_e_atualizacao_pelo_nutricionista(client: TestClient, db: Session) -> None:
    criar_nutricionista(db, 100)
    criar_paciente(db, 1)

    # Paciente nao pode acessar endpoints exclusivos do nutricionista
    resp_paciente = client.get("/api/v1/alertas-desvio/regra", headers=headers_de(1, "paciente"))
    assert resp_paciente.status_code == 403

    # Nutricionista sem regra salva recebe o padrao (20% por 3 dias, ativo)
    resp_padrao = client.get(
        "/api/v1/alertas-desvio/regra", headers=headers_de(100, "nutricionista")
    )
    assert resp_padrao.status_code == 200
    assert resp_padrao.json() == {
        "nutricionista_id": 100,
        "percentual_desvio": 20.0,
        "dias_consecutivos": 3,
        "ativo": True,
    }

    # Salva regra customizada (ex.: >15% por 2 dias) e depois atualiza
    resp_put = client.put(
        "/api/v1/alertas-desvio/regra",
        headers=headers_de(100, "nutricionista"),
        json={"percentual_desvio": 15.5, "dias_consecutivos": 2, "ativo": True},
    )
    assert resp_put.status_code == 200
    assert resp_put.json() == {
        "nutricionista_id": 100,
        "percentual_desvio": 15.5,
        "dias_consecutivos": 2,
        "ativo": True,
    }

    resp_put_2 = client.put(
        "/api/v1/alertas-desvio/regra",
        headers=headers_de(100, "nutricionista"),
        json={"percentual_desvio": 25.0, "dias_consecutivos": 4, "ativo": False},
    )
    assert resp_put_2.status_code == 200
    assert resp_put_2.json()["percentual_desvio"] == 25.0
    assert resp_put_2.json()["dias_consecutivos"] == 4
    assert resp_put_2.json()["ativo"] is False


def test_job_diario_detecta_desvio_acima_da_meta_do_plano_e_notifica(
    client: TestClient, db: Session
) -> None:
    criar_nutricionista(db, 100, nome="Dra. Helena")
    paciente = criar_paciente(db, 1)
    paciente.meta_kcal = Decimal("1800.00")
    db.add(Vinculo(nutricionista_id=100, paciente_id=1, status="ativo"))

    # Plano alimentar ativo com meta de 2000 kcal (tem prioridade sobre a meta basal)
    db.add(
        PlanoAlimentar(
            paciente_id=1,
            nutricionista_id=100,
            versao=1,
            titulo="Plano de manutencao",
            ativo=True,
            refeicoes=[
                RefeicaoPlano(
                    ordem=0,
                    nome="Almoco",
                    meta_kcal=Decimal("1000.00"),
                    meta_proteinas_g=Decimal("50.00"),
                    alimentos=[
                        AlimentoRefeicaoPlano(
                            ordem=0,
                            nome_alimento="Arroz e frango",
                            quantidade_g=Decimal("300.00"),
                        )
                    ],
                ),
                RefeicaoPlano(
                    ordem=1,
                    nome="Jantar",
                    meta_kcal=Decimal("1000.00"),
                    meta_proteinas_g=Decimal("50.00"),
                    alimentos=[
                        AlimentoRefeicaoPlano(
                            ordem=0,
                            nome_alimento="Peixe e legumes",
                            quantidade_g=Decimal("300.00"),
                        )
                    ],
                ),
            ],
        )
    )
    db.commit()

    hoje = date(2026, 11, 14)
    # 3 dias consecutivos >20% acima de 2000 kcal (2500, 2600, 2700 kcal -> media 2600 kcal, +30%)
    _registrar_consumo_dia(db, 1, hoje - timedelta(days=2), "2500.00")
    _registrar_consumo_dia(db, 1, hoje - timedelta(days=1), "2600.00")
    _registrar_consumo_dia(db, 1, hoje, "2700.00")

    notificacoes: list[tuple[str, str, str]] = []

    def _capturar_notificacao(email: str, titulo: str, mensagem: str, _alerta: object) -> bool:
        notificacoes.append((email, titulo, mensagem))
        return True

    gerados = processar_alertas_desvio_diario(db, hoje, notificar=_capturar_notificacao)
    assert gerados == 1
    assert len(notificacoes) == 1
    assert notificacoes[0][0] == "nutri100@exemplo.com"
    assert "Paciente 1" in notificacoes[0][1]
    assert "30.00% acima da meta" in notificacoes[0][2]

    # Idempotente: rodar novamente no mesmo dia nao duplica o alerta nem a notificacao
    assert processar_alertas_desvio_diario(db, hoje, notificar=_capturar_notificacao) == 0

    # Listagem e leitura no painel web
    resp_lista = client.get(
        "/api/v1/alertas-desvio?apenas_nao_lidos=true",
        headers=headers_de(100, "nutricionista"),
    )
    assert resp_lista.status_code == 200
    itens = resp_lista.json()
    assert len(itens) == 1
    alerta = itens[0]
    assert alerta["paciente_id"] == 1
    assert alerta["paciente_nome"] == "Paciente 1"
    assert alerta["direcao"] == "acima"
    assert alerta["meta_kcal"] == 2000.0
    assert alerta["consumo_medio_kcal"] == 2600.0
    assert alerta["percentual_medio_desvio"] == 30.0
    assert alerta["lido"] is False
    assert alerta["notificado_em"] is not None

    # Marca como lido
    resp_lido = client.patch(
        f"/api/v1/alertas-desvio/{alerta['id']}/lido",
        headers=headers_de(100, "nutricionista"),
    )
    assert resp_lido.status_code == 200
    assert resp_lido.json()["lido"] is True

    resp_nao_lidos = client.get(
        "/api/v1/alertas-desvio?apenas_nao_lidos=true",
        headers=headers_de(100, "nutricionista"),
    )
    assert resp_nao_lidos.json() == []


def test_regra_customizada_abaixo_e_ambos_e_bloqueios(client: TestClient, db: Session) -> None:
    criar_nutricionista(db, 100)
    criar_nutricionista(db, 200)
    p1 = criar_paciente(db, 1)
    p1.meta_kcal = Decimal("2000.00")
    p2 = criar_paciente(db, 2)
    p2.meta_kcal = Decimal("2000.00")
    db.add_all(
        [
            Vinculo(nutricionista_id=100, paciente_id=1, status="ativo"),
            Vinculo(nutricionista_id=100, paciente_id=2, status="ativo"),
        ]
    )
    db.commit()

    # Configura regra para >25% por 2 dias consecutivos
    client.put(
        "/api/v1/alertas-desvio/regra",
        headers=headers_de(100, "nutricionista"),
        json={"percentual_desvio": 25.0, "dias_consecutivos": 2, "ativo": True},
    )

    hoje = date(2026, 11, 14)
    # Paciente 1: 2 dias consecutivos >25% abaixo da meta (1400 kcal = -30%)
    _registrar_consumo_dia(db, 1, hoje - timedelta(days=1), "1400.00")
    _registrar_consumo_dia(db, 1, hoje, "1400.00")

    # Paciente 2: 1 dia >25% abaixo (1400 kcal) e 1 dia >25% acima (2600 kcal) -> "ambos"
    _registrar_consumo_dia(db, 2, hoje - timedelta(days=1), "1400.00")
    _registrar_consumo_dia(db, 2, hoje, "2600.00")

    resp_proc = client.post(
        f"/api/v1/alertas-desvio/processar?dia_referencia={hoje.isoformat()}",
        headers=headers_de(100, "nutricionista"),
    )
    assert resp_proc.status_code == 200
    assert resp_proc.json() == {"data_referencia": "2026-11-14", "alertas_gerados": 2}

    resp_p1 = client.get(
        "/api/v1/alertas-desvio?paciente_id=1",
        headers=headers_de(100, "nutricionista"),
    )
    assert len(resp_p1.json()) == 1
    assert resp_p1.json()[0]["direcao"] == "abaixo"

    resp_p2 = client.get(
        "/api/v1/alertas-desvio?paciente_id=2",
        headers=headers_de(100, "nutricionista"),
    )
    assert len(resp_p2.json()) == 1
    assert resp_p2.json()[0]["direcao"] == "ambos"

    # Outro nutricionista nao consegue marcar como lido o alerta do nutricionista 100
    alerta_id = resp_p1.json()[0]["id"]
    resp_outro = client.patch(
        f"/api/v1/alertas-desvio/{alerta_id}/lido",
        headers=headers_de(200, "nutricionista"),
    )
    assert resp_outro.status_code == 404


def test_nao_gera_alerta_quando_dentro_da_faixa_ou_regra_inativa(
    client: TestClient, db: Session
) -> None:
    criar_nutricionista(db, 100)
    paciente = criar_paciente(db, 1)
    paciente.meta_kcal = Decimal("2000.00")
    db.add(Vinculo(nutricionista_id=100, paciente_id=1, status="ativo"))
    db.commit()

    hoje = date(2026, 11, 14)
    # Desvio de apenas 10% (2200 kcal vs 2000 kcal)
    for d in range(3):
        _registrar_consumo_dia(db, 1, hoje - timedelta(days=d), "2200.00")

    assert processar_alertas_desvio_diario(db, hoje) == 0

    # Desativa a regra: mesmo com desvio > 20% em outra data, nao gera alerta
    client.put(
        "/api/v1/alertas-desvio/regra",
        headers=headers_de(100, "nutricionista"),
        json={"percentual_desvio": 20.0, "dias_consecutivos": 1, "ativo": False},
    )
    amanha = hoje + timedelta(days=1)
    _registrar_consumo_dia(db, 1, amanha, "3000.00")
    assert processar_alertas_desvio_diario(db, amanha) == 0
