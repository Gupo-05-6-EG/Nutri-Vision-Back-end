from datetime import date

from app.models.conquista import ConquistaPaciente
from app.models.vinculo import Vinculo
from app.services.gamificacao import processar_gamificacao_diaria
from tests.factories import criar_nutricionista, criar_paciente, headers_de


def test_resgate_debita_xp_e_consumo_e_idempotente(client, db):
    paciente = criar_paciente(db, 1)
    paciente.xp = 150
    paciente.streak = 5
    db.commit()
    response = client.post("/api/v1/gamificacao/bloqueios", headers=headers_de(1))
    assert response.status_code == 200
    assert response.json()["xp"] == 50
    assert response.json()["bloqueios_perda"] == 1
    assert client.post("/api/v1/gamificacao/bloqueios", headers=headers_de(1)).status_code == 409
    dia = date(2026, 11, 10)
    processar_gamificacao_diaria(db, dia)
    assert paciente.streak == 5
    assert paciente.bloqueios_perda == 0
    processar_gamificacao_diaria(db, dia)
    assert paciente.streak == 5
    processar_gamificacao_diaria(db, date(2026, 11, 11))
    assert paciente.streak == 0


def test_conquistas_permanentes_e_privadas(client, db):
    paciente = criar_paciente(db, 1)
    criar_paciente(db, 2)
    paciente.streak = 30
    db.commit()
    response = client.get("/api/v1/gamificacao/conquistas", headers=headers_de(1))
    assert response.status_code == 200
    assert sum(c["obtida_em"] is not None for c in response.json()) == 2
    paciente.streak = 0
    db.commit()
    response = client.get("/api/v1/gamificacao/conquistas", headers=headers_de(1))
    assert sum(c["obtida_em"] is not None for c in response.json()) == 2
    assert len(db.query(ConquistaPaciente).all()) == 2
    response = client.get("/api/v1/gamificacao/conquistas", headers=headers_de(2))
    assert all(c["obtida_em"] is None for c in response.json())
    assert client.get("/api/v1/gamificacao/conquistas").status_code == 401


def test_fechamento_preserva_marcos_anteriores_ao_primeiro_acesso(db):
    paciente = criar_paciente(db, 1)
    paciente.streak = 30
    db.commit()

    processar_gamificacao_diaria(db, date(2026, 11, 10))

    assert paciente.streak == 0
    assert {c.codigo for c in db.query(ConquistaPaciente).all()} == {"streak_7", "streak_30"}


def test_vinculo_pendente_nao_autoriza_pdf(client, db):
    criar_paciente(db, 1)
    criar_nutricionista(db, 10)
    vinculo = Vinculo(nutricionista_id=10, paciente_id=1, status="pendente")
    db.add(vinculo)
    db.commit()
    path = "/api/v1/pacientes/1/relatorio.pdf?inicio=2026-11-01&fim=2026-11-10"
    assert client.get(path, headers=headers_de(10)).status_code == 403

    vinculo.status = "ativo"
    db.commit()
    response = client.get(path, headers=headers_de(10))
    assert response.status_code == 200
    assert response.content.startswith(b"%PDF-")
    assert response.headers["cache-control"] == "no-store"
    assert client.get(path, headers=headers_de(1)).status_code == 403
    assert (
        client.get(path.replace("2026-11-10", "2026-10-31"), headers=headers_de(10)).status_code
        == 422
    )
    vinculo.status = "encerrado"
    db.commit()
    assert client.get(path, headers=headers_de(10)).status_code == 403


def test_privacidade_exporta_novas_entidades_e_exclui_so_propria_conta(client, db):
    criar_paciente(db, 1)
    criar_paciente(db, 2)
    headers = headers_de(1)
    path = "/api/v1/privacidade"
    assert (
        client.post(
            path + "/consentimento", json={"versao_termo": "2026-11"}, headers=headers
        ).status_code
        == 201
    )
    assert client.get(path + "/consentimento", headers=headers).json()["consentimento_ativo"]
    assert client.post(path + "/consentimento/revogar", headers=headers).status_code == 200
    assert not client.get(path + "/consentimento", headers=headers).json()["consentimento_ativo"]
    response = client.get(path + "/dados", headers=headers)
    assert response.status_code == 200
    assert "senha_hash" not in response.text
    assert {"planos", "conquistas", "lembretes", "participacoes_desafios"} <= response.json().keys()
    assert client.delete(path + "/conta", headers=headers).status_code == 204
    assert client.get(path + "/dados", headers=headers).status_code == 401
    assert client.get(path + "/dados", headers=headers_de(2)).status_code == 200
