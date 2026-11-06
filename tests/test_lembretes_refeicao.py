"""Testes dos lembretes de refeicao: configuracao, token de push e job (Task 2.8, RF26).

O envio real (FCM) e substituido por `PushFalso`, que registra as chamadas.
"""

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.lembrete_refeicao import DispositivoPush, LembreteRefeicao
from app.models.refeicao import ItemRefeicao, Refeicao, TipoRefeicao
from app.services import fcm
from app.services.fcm import FcmNaoConfigurado, ResultadoPush
from app.services.gamificacao import FUSO_HORARIO
from app.services.lembretes_refeicao import processar_lembretes
from tests import factories

DIA = date(2026, 10, 12)


def _local(hora: int, minuto: int = 0, dia: date = DIA) -> datetime:
    """Momento em hora local (America/Sao_Paulo), com fuso."""
    return datetime.combine(dia, time(hora, minuto), tzinfo=FUSO_HORARIO)


class PushFalso:
    def __init__(self, resultados: dict[str, ResultadoPush] | None = None) -> None:
        self.resultados = resultados or {}
        self.chamadas: list[tuple[str, str, str, dict[str, str]]] = []

    def __call__(self, token: str, titulo: str, corpo: str, dados: dict[str, str]) -> ResultadoPush:
        self.chamadas.append((token, titulo, corpo, dados))
        return self.resultados.get(token, ResultadoPush.ENVIADO)

    @property
    def tokens(self) -> list[str]:
        return [chamada[0] for chamada in self.chamadas]


@pytest.fixture(autouse=True)
def _pacientes(db: Session) -> None:
    for paciente_id in (1, 2):
        factories.criar_paciente(db, paciente_id)


def _lembrete(
    db: Session,
    tipo: TipoRefeicao = TipoRefeicao.ALMOCO,
    horario: time = time(12, 30),
    paciente_id: int = 1,
    ativo: bool = True,
) -> LembreteRefeicao:
    lembrete = LembreteRefeicao(
        paciente_id=paciente_id, tipo=tipo.value, horario=horario, ativo=ativo
    )
    db.add(lembrete)
    db.commit()
    return lembrete


def _dispositivo(db: Session, token: str = "token-1", paciente_id: int = 1) -> None:
    db.add(DispositivoPush(paciente_id=paciente_id, token=token))
    db.commit()


def _refeicao(db: Session, tipo: TipoRefeicao, momento: datetime, paciente_id: int = 1) -> None:
    db.add(
        Refeicao(
            paciente_id=paciente_id,
            # Em UTC: o SQLite dos testes guarda o relogio como veio, sem converter.
            consumida_em=momento.astimezone(UTC),
            tipo=tipo.value,
            itens=[
                ItemRefeicao(
                    nome_alimento="Item",
                    quantidade_g=Decimal("100"),
                    calorias_kcal=Decimal("100"),
                    proteinas_g=Decimal("0"),
                    carboidratos_g=Decimal("0"),
                    gorduras_g=Decimal("0"),
                )
            ],
        )
    )
    db.commit()


# --------------------------------------------------------------------------- API


def _put(client: TestClient, lembretes: list[dict[str, Any]], paciente_id: int = 1):
    return client.put(
        f"/api/v1/pacientes/{paciente_id}/lembretes-refeicao", json={"lembretes": lembretes}
    )


def test_salva_e_lista_lembretes_ordenados_por_horario(client: TestClient) -> None:
    resposta = _put(
        client,
        [
            {"tipo": "jantar", "horario": "20:00"},
            {"tipo": "cafe_da_manha", "horario": "07:30:00", "ativo": False},
        ],
    )

    assert resposta.status_code == 200
    esperado = {
        "paciente_id": 1,
        "lembretes": [
            {"tipo": "cafe_da_manha", "horario": "07:30:00", "ativo": False},
            {"tipo": "jantar", "horario": "20:00:00", "ativo": True},
        ],
    }
    assert resposta.json() == esperado
    assert client.get("/api/v1/pacientes/1/lembretes-refeicao").json() == esperado


def test_put_atualiza_so_os_tipos_enviados(client: TestClient) -> None:
    _put(client, [{"tipo": "almoco", "horario": "12:00"}, {"tipo": "jantar", "horario": "20:00"}])

    resposta = _put(client, [{"tipo": "almoco", "horario": "13:15", "ativo": False}])

    assert resposta.json()["lembretes"] == [
        {"tipo": "almoco", "horario": "13:15:00", "ativo": False},
        {"tipo": "jantar", "horario": "20:00:00", "ativo": True},
    ]


def test_segundos_sao_descartados(client: TestClient) -> None:
    resposta = _put(client, [{"tipo": "almoco", "horario": "12:30:45"}])

    assert resposta.json()["lembretes"][0]["horario"] == "12:30:00"


def test_lembretes_de_um_paciente_nao_aparecem_para_outro(client: TestClient) -> None:
    _put(client, [{"tipo": "almoco", "horario": "12:00"}], paciente_id=1)

    assert client.get("/api/v1/pacientes/2/lembretes-refeicao").json()["lembretes"] == []


@pytest.mark.parametrize(
    "lembretes",
    [
        [],
        [{"tipo": "ceia", "horario": "22:00"}],
        [{"tipo": "almoco", "horario": "25:00"}],
        [{"tipo": "almoco"}],
        [{"tipo": "almoco", "horario": "12:00"}, {"tipo": "almoco", "horario": "13:00"}],
    ],
)
def test_corpo_invalido_retorna_422(client: TestClient, lembretes: list[dict[str, Any]]) -> None:
    assert _put(client, lembretes).status_code == 422


def test_paciente_inexistente_retorna_404(client: TestClient) -> None:
    assert client.get("/api/v1/pacientes/99/lembretes-refeicao").status_code == 404
    assert _put(client, [{"tipo": "almoco", "horario": "12:00"}], paciente_id=99).status_code == 404
    resposta = client.put("/api/v1/pacientes/99/dispositivos-push", json={"token": "abc"})
    assert resposta.status_code == 404


def test_registra_dispositivo_de_forma_idempotente(client: TestClient, db: Session) -> None:
    for _ in range(2):
        resposta = client.put("/api/v1/pacientes/1/dispositivos-push", json={"token": "abc"})
        assert resposta.status_code == 204

    dispositivos = db.execute(select(DispositivoPush)).scalars().all()
    assert [(d.paciente_id, d.token) for d in dispositivos] == [(1, "abc")]


def test_token_ja_registrado_passa_para_o_novo_paciente(client: TestClient, db: Session) -> None:
    client.put("/api/v1/pacientes/1/dispositivos-push", json={"token": "abc"})
    client.put("/api/v1/pacientes/2/dispositivos-push", json={"token": "abc"})

    dispositivos = db.execute(select(DispositivoPush)).scalars().all()
    assert [(d.paciente_id, d.token) for d in dispositivos] == [(2, "abc")]


@pytest.mark.parametrize("token", ["", "x" * 513])
def test_token_invalido_retorna_422(client: TestClient, token: str) -> None:
    resposta = client.put("/api/v1/pacientes/1/dispositivos-push", json={"token": token})
    assert resposta.status_code == 422


# --------------------------------------------------------------------------- job


def test_envia_quando_a_refeicao_nao_foi_registrada(db: Session) -> None:
    lembrete = _lembrete(db, TipoRefeicao.ALMOCO, time(12, 30))
    _dispositivo(db)
    push = PushFalso()

    assert processar_lembretes(db, _local(12, 35), push) == 1

    assert push.tokens == ["token-1"]
    _, titulo, corpo, dados = push.chamadas[0]
    assert titulo == "Hora de registrar sua refeição"
    assert "almoço" in corpo
    assert dados == {"tipo_notificacao": "lembrete_refeicao", "tipo_refeicao": "almoco"}
    assert lembrete.ultimo_envio_em == DIA


def test_nao_envia_antes_do_horario(db: Session) -> None:
    _lembrete(db, TipoRefeicao.ALMOCO, time(12, 30))
    _dispositivo(db)
    push = PushFalso()

    assert processar_lembretes(db, _local(12, 29), push) == 0
    assert push.chamadas == []


def test_nao_envia_se_a_refeicao_do_tipo_foi_registrada_na_janela(db: Session) -> None:
    _lembrete(db, TipoRefeicao.ALMOCO, time(12, 30))
    _dispositivo(db)
    _refeicao(db, TipoRefeicao.ALMOCO, _local(11, 45))
    push = PushFalso()

    assert processar_lembretes(db, _local(12, 35), push) == 0
    assert push.chamadas == []


def test_refeicao_de_outro_tipo_nao_conta(db: Session) -> None:
    _lembrete(db, TipoRefeicao.ALMOCO, time(12, 30))
    _dispositivo(db)
    _refeicao(db, TipoRefeicao.CAFE_DA_MANHA, _local(12, 0))
    push = PushFalso()

    assert processar_lembretes(db, _local(12, 35), push) == 1


def test_refeicao_de_antes_da_janela_nao_conta(db: Session) -> None:
    _lembrete(db, TipoRefeicao.ALMOCO, time(12, 30))
    _dispositivo(db)
    _refeicao(db, TipoRefeicao.ALMOCO, _local(10, 0))  # janela do almoco comeca as 11h
    push = PushFalso()

    assert processar_lembretes(db, _local(12, 35), push) == 1


def test_refeicao_de_outro_paciente_nao_conta(db: Session) -> None:
    _lembrete(db, TipoRefeicao.ALMOCO, time(12, 30))
    _dispositivo(db)
    _refeicao(db, TipoRefeicao.ALMOCO, _local(12, 0), paciente_id=2)

    assert processar_lembretes(db, _local(12, 35), PushFalso()) == 1


def test_envia_no_maximo_uma_vez_por_dia(db: Session) -> None:
    _lembrete(db, TipoRefeicao.ALMOCO, time(12, 30))
    _dispositivo(db)
    push = PushFalso()

    assert processar_lembretes(db, _local(12, 35), push) == 1
    assert processar_lembretes(db, _local(12, 40), push) == 0
    assert len(push.chamadas) == 1


def test_envia_de_novo_no_dia_seguinte(db: Session) -> None:
    _lembrete(db, TipoRefeicao.ALMOCO, time(12, 30))
    _dispositivo(db)
    push = PushFalso()
    amanha = DIA + timedelta(days=1)

    assert processar_lembretes(db, _local(12, 35), push) == 1
    assert processar_lembretes(db, _local(12, 35, amanha), push) == 1


def test_nao_envia_depois_da_tolerancia(db: Session) -> None:
    _lembrete(db, TipoRefeicao.ALMOCO, time(12, 30))
    _dispositivo(db)
    push = PushFalso()

    assert processar_lembretes(db, _local(13, 31), push) == 0
    assert processar_lembretes(db, _local(13, 30), push) == 1


def test_lembrete_inativo_nao_envia(db: Session) -> None:
    _lembrete(db, TipoRefeicao.ALMOCO, time(12, 30), ativo=False)
    _dispositivo(db)

    assert processar_lembretes(db, _local(12, 35), PushFalso()) == 0


def test_sem_dispositivo_nao_envia_nem_marca_como_enviado(db: Session) -> None:
    lembrete = _lembrete(db, TipoRefeicao.ALMOCO, time(12, 30))
    push = PushFalso()

    assert processar_lembretes(db, _local(12, 35), push) == 0
    assert lembrete.ultimo_envio_em is None

    _dispositivo(db)  # registrou o aparelho dentro da tolerancia
    assert processar_lembretes(db, _local(12, 40), push) == 1


def test_envia_para_todos_os_aparelhos_do_paciente(db: Session) -> None:
    _lembrete(db, TipoRefeicao.ALMOCO, time(12, 30))
    _dispositivo(db, "token-1")
    _dispositivo(db, "token-2")
    _dispositivo(db, "token-do-outro", paciente_id=2)
    push = PushFalso()

    assert processar_lembretes(db, _local(12, 35), push) == 1
    assert sorted(push.tokens) == ["token-1", "token-2"]


def test_token_invalido_e_removido(db: Session) -> None:
    lembrete = _lembrete(db, TipoRefeicao.ALMOCO, time(12, 30))
    _dispositivo(db, "token-morto")
    _dispositivo(db, "token-vivo")
    push = PushFalso({"token-morto": ResultadoPush.TOKEN_INVALIDO})

    assert processar_lembretes(db, _local(12, 35), push) == 1

    restantes = db.execute(select(DispositivoPush.token)).scalars().all()
    assert restantes == ["token-vivo"]
    assert lembrete.ultimo_envio_em == DIA


def test_falha_no_envio_tenta_de_novo_na_proxima_execucao(db: Session) -> None:
    lembrete = _lembrete(db, TipoRefeicao.ALMOCO, time(12, 30))
    _dispositivo(db)

    assert processar_lembretes(db, _local(12, 35), PushFalso({"token-1": ResultadoPush.FALHA})) == 0
    assert lembrete.ultimo_envio_em is None
    assert db.execute(select(DispositivoPush)).scalars().all()  # token nao foi apagado

    assert processar_lembretes(db, _local(12, 40), PushFalso()) == 1


def test_alterar_o_horario_libera_novo_envio_no_dia(client: TestClient, db: Session) -> None:
    _dispositivo(db)
    _put(client, [{"tipo": "almoco", "horario": "12:30"}])
    push = PushFalso()
    assert processar_lembretes(db, _local(12, 35), push) == 1

    _put(client, [{"tipo": "almoco", "horario": "12:50"}])

    assert processar_lembretes(db, _local(12, 55), push) == 1


def test_manter_o_horario_nao_libera_novo_envio(client: TestClient, db: Session) -> None:
    _dispositivo(db)
    _put(client, [{"tipo": "almoco", "horario": "12:30"}])
    push = PushFalso()
    assert processar_lembretes(db, _local(12, 35), push) == 1

    _put(client, [{"tipo": "almoco", "horario": "12:30", "ativo": True}])

    assert processar_lembretes(db, _local(12, 40), push) == 0


def test_horario_antes_do_inicio_da_faixa_usa_o_horario_como_inicio_da_janela(
    db: Session,
) -> None:
    _lembrete(db, TipoRefeicao.CAFE_DA_MANHA, time(4, 0))  # faixa do cafe comeca as 5h
    _dispositivo(db)
    _refeicao(db, TipoRefeicao.CAFE_DA_MANHA, _local(4, 10))

    assert processar_lembretes(db, _local(4, 20), PushFalso()) == 0


# --------------------------------------------------------------------------- FCM


def test_fcm_sem_credenciais_levanta_erro_claro(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        fcm, "get_settings", lambda: type("S", (), {"FCM_CREDENTIALS_FILE": None})()
    )
    fcm._app_firebase.cache_clear()

    with pytest.raises(FcmNaoConfigurado):
        fcm.enviar_push_fcm("t", "titulo", "corpo", {})


def _preparar_fcm(monkeypatch: pytest.MonkeyPatch, efeito: Exception | None) -> list[Any]:
    from firebase_admin import messaging

    enviadas: list[Any] = []

    def _send(mensagem: Any, app: Any = None) -> str:
        enviadas.append(mensagem)
        if efeito is not None:
            raise efeito
        return "projects/x/messages/1"

    monkeypatch.setattr(fcm, "_app_firebase", lambda: object())
    monkeypatch.setattr(messaging, "send", _send)
    return enviadas


def test_fcm_envia_a_mensagem_montada(monkeypatch: pytest.MonkeyPatch) -> None:
    enviadas = _preparar_fcm(monkeypatch, None)

    resultado = fcm.enviar_push_fcm("tok", "Titulo", "Corpo", {"a": "b"})

    assert resultado == ResultadoPush.ENVIADO
    mensagem = enviadas[0]
    assert mensagem.token == "tok"
    assert (mensagem.notification.title, mensagem.notification.body) == ("Titulo", "Corpo")
    assert mensagem.data == {"a": "b"}


def test_fcm_token_nao_registrado_vira_token_invalido(monkeypatch: pytest.MonkeyPatch) -> None:
    from firebase_admin import messaging

    _preparar_fcm(monkeypatch, messaging.UnregisteredError("token morto"))

    assert fcm.enviar_push_fcm("tok", "t", "c", {}) == ResultadoPush.TOKEN_INVALIDO


def test_fcm_erro_generico_vira_falha(monkeypatch: pytest.MonkeyPatch) -> None:
    from firebase_admin import exceptions

    _preparar_fcm(monkeypatch, exceptions.UnavailableError("fora do ar"))

    assert fcm.enviar_push_fcm("tok", "t", "c", {}) == ResultadoPush.FALHA
