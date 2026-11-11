"""Testes do job diario de notificacoes motivacionais de desafios via FCM (Task 4.5, RF05.5)."""

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.desafio import Desafio, ParticipanteDesafio, StatusParticipante, TipoDesafio
from app.models.lembrete_refeicao import DispositivoPush
from app.models.notificacao_desafio import NotificacaoDesafio
from app.models.refeicao import ItemRefeicao, Refeicao, TipoRefeicao
from app.services.desafios import FUSO_HORARIO
from app.services.fcm import ResultadoPush
from app.services.notificacoes_desafio import (
    montar_mensagem_desafio,
    processar_notificacoes_desafios,
)
from tests import factories

DIA = date(2026, 10, 12)


def _local(hora: int = 9, minuto: int = 0, dia: date = DIA) -> datetime:
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
    for paciente_id in (1, 2, 3):
        paciente = factories.criar_paciente(db, paciente_id)
        paciente.meta_kcal = Decimal("2000")
    db.commit()


def _dispositivo(db: Session, paciente_id: int, token: str) -> None:
    db.add(DispositivoPush(paciente_id=paciente_id, token=token))
    db.commit()


def _criar_desafio(
    db: Session,
    *,
    criador_id: int = 1,
    nome: str = "Semana equilibrada",
    tipo: TipoDesafio = TipoDesafio.REFEICOES,
    inicio_em: datetime | None = None,
    fim_em: datetime | None = None,
    participantes: list[tuple[int, StatusParticipante]] | None = None,
) -> Desafio:
    inicio = (inicio_em or _local(0, 0, DIA - timedelta(days=1))).astimezone(UTC)
    fim = (fim_em or _local(23, 59, DIA + timedelta(days=2))).astimezone(UTC)
    desafio = Desafio(
        criador_id=criador_id,
        nome=nome,
        tipo=tipo.value,
        regra="Completar todas as refeicoes",
        inicio_em=inicio,
        fim_em=fim,
    )
    db.add(desafio)
    db.flush()

    membros = (
        participantes
        if participantes is not None
        else [
            (1, StatusParticipante.ACEITO),
            (2, StatusParticipante.ACEITO),
        ]
    )
    for pid, status in membros:
        db.add(
            ParticipanteDesafio(
                desafio_id=desafio.id,
                paciente_id=pid,
                status=status.value,
            )
        )
    db.commit()
    db.refresh(desafio)
    return desafio


def _refeicao_completa_dia(db: Session, paciente_id: int, dia: date = DIA) -> None:
    """Registra as 4 categorias de refeicao no dia para pontuar no desafio de refeicoes."""
    for idx, tipo in enumerate(TipoRefeicao, start=8):
        db.add(
            Refeicao(
                paciente_id=paciente_id,
                consumida_em=datetime.combine(dia, time(idx, 0), tzinfo=FUSO_HORARIO).astimezone(
                    UTC
                ),
                tipo=tipo.value,
                itens=[
                    ItemRefeicao(
                        nome_alimento="Alimento",
                        quantidade_g=Decimal("100"),
                        calorias_kcal=Decimal("100"),
                        proteinas_g=Decimal("5"),
                        carboidratos_g=Decimal("10"),
                        gorduras_g=Decimal("2"),
                    )
                ],
            )
        )
    db.commit()


def test_montar_mensagem_desafio_formata_posicao_e_dias_restantes() -> None:
    titulo, corpo_plural = montar_mensagem_desafio("Semana Fit", 2, 2)
    assert titulo == "Desafio: Semana Fit"
    assert "você está em 2º lugar" in corpo_plural.lower()
    assert "faltam 2 dias" in corpo_plural.lower()

    _, corpo_um_dia = montar_mensagem_desafio("Semana Fit", 1, 1)
    assert "você está em 1º lugar" in corpo_um_dia.lower()
    assert "falta 1 dia" in corpo_um_dia.lower()

    _, corpo_ultimo_dia = montar_mensagem_desafio("Semana Fit", 3, 0)
    assert "você está em 3º lugar" in corpo_ultimo_dia.lower()
    assert "último dia" in corpo_ultimo_dia.lower()


def test_calcula_posicao_e_envia_push_para_participantes_aceitos(db: Session) -> None:
    # Paciente 1 pontua todas as categorias; Paciente 2 nao registra nada -> 1o e 2o lugares.
    desafio = _criar_desafio(
        db,
        participantes=[
            (1, StatusParticipante.ACEITO),
            (2, StatusParticipante.ACEITO),
            (3, StatusParticipante.CONVIDADO),  # convidado nao recebe notificacao
        ],
    )
    _refeicao_completa_dia(db, paciente_id=1)
    _dispositivo(db, 1, "token-pac-1")
    _dispositivo(db, 2, "token-pac-2")
    _dispositivo(db, 3, "token-pac-3")

    push = PushFalso()
    enviados = processar_notificacoes_desafios(db, _local(9, 0), push)

    assert enviados == 2
    assert push.tokens == ["token-pac-1", "token-pac-2"]

    _, titulo1, corpo1, dados1 = push.chamadas[0]
    assert titulo1 == "Desafio: Semana equilibrada"
    assert "1º lugar" in corpo1
    assert "faltam 2 dias" in corpo1
    assert dados1 == {
        "tipo_notificacao": "andamento_desafio",
        "desafio_id": str(desafio.id),
        "posicao": "1",
        "dias_restantes": "2",
    }

    _, _, corpo2, dados2 = push.chamadas[1]
    assert "2º lugar" in corpo2
    assert "faltam 2 dias" in corpo2
    assert dados2["posicao"] == "2"


def test_limite_de_frequencia_impede_segundo_envio_no_mesmo_dia(db: Session) -> None:
    _criar_desafio(db)
    _dispositivo(db, 1, "token-pac-1")
    _dispositivo(db, 2, "token-pac-2")

    push = PushFalso()
    assert processar_notificacoes_desafios(db, _local(9, 0), push) == 2
    assert processar_notificacoes_desafios(db, _local(18, 0), push) == 0
    assert len(push.chamadas) == 2


def test_limite_de_frequencia_entre_multiplos_desafios_ativos_no_mesmo_dia(db: Session) -> None:
    _criar_desafio(db, nome="Desafio A", fim_em=_local(23, 59, DIA + timedelta(days=1)))
    _criar_desafio(db, nome="Desafio B", fim_em=_local(23, 59, DIA + timedelta(days=3)))
    _dispositivo(db, 1, "token-pac-1")

    push = PushFalso()
    assert processar_notificacoes_desafios(db, _local(10, 0), push) == 1
    assert len(push.chamadas) == 1
    assert push.chamadas[0][1] == "Desafio: Desafio A"


def test_novo_dia_libera_novo_envio(db: Session) -> None:
    _criar_desafio(db, fim_em=_local(23, 59, DIA + timedelta(days=3)))
    _dispositivo(db, 1, "token-pac-1")

    push = PushFalso()
    assert processar_notificacoes_desafios(db, _local(9, 0, DIA), push) == 1
    assert processar_notificacoes_desafios(db, _local(9, 0, DIA + timedelta(days=1)), push) == 1
    assert len(push.chamadas) == 2
    assert "faltam 3 dias" in push.chamadas[0][2]
    assert "faltam 2 dias" in push.chamadas[1][2]


def test_ignora_desafios_nao_iniciados_ou_ja_encerrados(db: Session) -> None:
    # Encerrado ontem
    _criar_desafio(
        db,
        nome="Passado",
        inicio_em=_local(0, 0, DIA - timedelta(days=5)),
        fim_em=_local(23, 59, DIA - timedelta(days=1)),
    )
    # Comeca amanha
    _criar_desafio(
        db,
        nome="Futuro",
        inicio_em=_local(0, 0, DIA + timedelta(days=1)),
        fim_em=_local(23, 59, DIA + timedelta(days=5)),
    )
    _dispositivo(db, 1, "token-pac-1")

    push = PushFalso()
    assert processar_notificacoes_desafios(db, _local(9, 0, DIA), push) == 0
    assert push.chamadas == []


def test_participante_sem_dispositivo_push_nao_conta_como_enviado(db: Session) -> None:
    _criar_desafio(db)
    # Apenas paciente 2 tem aparelho registrado
    _dispositivo(db, 2, "token-pac-2")

    push = PushFalso()
    assert processar_notificacoes_desafios(db, _local(9, 0), push) == 1
    assert push.tokens == ["token-pac-2"]

    registros = list(db.scalars(select(NotificacaoDesafio)).all())
    assert len(registros) == 1
    assert registros[0].paciente_id == 2


def test_multiplos_aparelhos_do_mesmo_paciente_e_remocao_de_token_invalido(db: Session) -> None:
    _criar_desafio(db, participantes=[(1, StatusParticipante.ACEITO)])
    _dispositivo(db, 1, "token-antigo")
    _dispositivo(db, 1, "token-valido")

    push = PushFalso({"token-antigo": ResultadoPush.TOKEN_INVALIDO})
    assert processar_notificacoes_desafios(db, _local(9, 0), push) == 1

    tokens_restantes = list(db.scalars(select(DispositivoPush.token)).all())
    assert tokens_restantes == ["token-valido"]


def test_falha_temporaria_no_fcm_nao_registra_envio_e_permite_retentativa(db: Session) -> None:
    _criar_desafio(db, participantes=[(1, StatusParticipante.ACEITO)])
    _dispositivo(db, 1, "token-pac-1")

    push_falho = PushFalso({"token-pac-1": ResultadoPush.FALHA})
    assert processar_notificacoes_desafios(db, _local(9, 0), push_falho) == 0
    assert list(db.scalars(select(NotificacaoDesafio)).all()) == []
    assert list(db.scalars(select(DispositivoPush)).all()) != []

    push_ok = PushFalso()
    assert processar_notificacoes_desafios(db, _local(9, 5), push_ok) == 1
