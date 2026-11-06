"""Lembretes de refeicao: configuracao de horarios e job de envio (Task 2.8, RF26).

Regra do job: para cada lembrete ativo cujo horario ja passou, se o paciente
nao registrou nenhuma refeicao daquele tipo na janela da refeicao, envia um push
(FCM) para os aparelhos dele - no maximo uma vez por dia.

A janela vai do inicio da faixa do tipo (`JANELA_INICIO`) ate o momento do
envio. Se o horario configurado for anterior ao inicio da faixa, a janela comeca
no horario. O push so e enviado ate `TOLERANCIA_ENVIO` depois do horario: assim
um lembrete criado/editado no fim do dia, ou um job que ficou parado, nao dispara
notificacoes atrasadas.
"""

from collections.abc import Callable
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.lembrete_refeicao import DispositivoPush, LembreteRefeicao
from app.models.paciente import Paciente
from app.models.refeicao import Refeicao, TipoRefeicao
from app.schemas.lembrete_refeicao import LembretesIn
from app.services.fcm import ResultadoPush
from app.services.gamificacao import FUSO_HORARIO

# Inicio (hora local) da faixa de cada refeicao, alinhado a categorizacao do RF19.
JANELA_INICIO: dict[TipoRefeicao, time] = {
    TipoRefeicao.CAFE_DA_MANHA: time(5),
    TipoRefeicao.ALMOCO: time(11),
    TipoRefeicao.LANCHE: time(15),
    TipoRefeicao.JANTAR: time(18),
}
TOLERANCIA_ENVIO = timedelta(minutes=60)

NOME_DA_REFEICAO: dict[TipoRefeicao, str] = {
    TipoRefeicao.CAFE_DA_MANHA: "café da manhã",
    TipoRefeicao.ALMOCO: "almoço",
    TipoRefeicao.LANCHE: "lanche",
    TipoRefeicao.JANTAR: "jantar",
}

# (token, titulo, corpo, dados) -> resultado. O job recebe isso por parametro:
# em producao e o FCM; nos testes, um envio falso.
EnviarPush = Callable[[str, str, str, dict[str, str]], ResultadoPush]


class PacienteNaoEncontrado(Exception):
    """Nao existe paciente cadastrado com o id informado."""


def _exigir_paciente(db: Session, paciente_id: int) -> None:
    if db.get(Paciente, paciente_id) is None:
        raise PacienteNaoEncontrado


def listar_lembretes(db: Session, paciente_id: int) -> list[LembreteRefeicao]:
    _exigir_paciente(db, paciente_id)
    return list(
        db.execute(
            select(LembreteRefeicao)
            .where(LembreteRefeicao.paciente_id == paciente_id)
            .order_by(LembreteRefeicao.horario, LembreteRefeicao.id)
        ).scalars()
    )


def salvar_lembretes(db: Session, paciente_id: int, dados: LembretesIn) -> list[LembreteRefeicao]:
    """Cria ou atualiza o lembrete de cada tipo enviado; os demais ficam como estao."""
    _exigir_paciente(db, paciente_id)
    existentes = {
        lembrete.tipo: lembrete
        for lembrete in db.execute(
            select(LembreteRefeicao).where(LembreteRefeicao.paciente_id == paciente_id)
        ).scalars()
    }
    for novo in dados.lembretes:
        lembrete = existentes.get(novo.tipo.value)
        if lembrete is None:
            db.add(
                LembreteRefeicao(
                    paciente_id=paciente_id,
                    tipo=novo.tipo.value,
                    horario=novo.horario,
                    ativo=novo.ativo,
                )
            )
            continue
        if lembrete.horario != novo.horario:
            # Horario novo: libera um envio hoje, se ainda der tempo.
            lembrete.ultimo_envio_em = None
        lembrete.horario = novo.horario
        lembrete.ativo = novo.ativo
    db.commit()
    return listar_lembretes(db, paciente_id)


def registrar_dispositivo(db: Session, paciente_id: int, token: str) -> None:
    """Guarda o token FCM do aparelho; se o token ja existia, passa a ser deste paciente."""
    _exigir_paciente(db, paciente_id)
    dispositivo = db.execute(
        select(DispositivoPush).where(DispositivoPush.token == token)
    ).scalar_one_or_none()
    if dispositivo is None:
        db.add(DispositivoPush(paciente_id=paciente_id, token=token))
    else:
        dispositivo.paciente_id = paciente_id
    db.commit()


def _ja_registrou(
    db: Session, paciente_id: int, tipo: str, inicio_utc: datetime, fim_utc: datetime
) -> bool:
    return (
        db.execute(
            select(Refeicao.id)
            .where(
                Refeicao.paciente_id == paciente_id,
                Refeicao.tipo == tipo,
                Refeicao.consumida_em >= inicio_utc,
                Refeicao.consumida_em <= fim_utc,
            )
            .limit(1)
        ).first()
        is not None
    )


def _notificar(
    db: Session, lembrete: LembreteRefeicao, dispositivos: list[DispositivoPush], enviar: EnviarPush
) -> bool:
    """Envia para todos os aparelhos; True se ao menos um recebeu."""
    nome = NOME_DA_REFEICAO[TipoRefeicao(lembrete.tipo)]
    titulo = "Hora de registrar sua refeição"
    corpo = f"Você ainda não registrou seu {nome}. Que tal registrar agora?"
    dados = {"tipo_notificacao": "lembrete_refeicao", "tipo_refeicao": lembrete.tipo}

    enviado = False
    for dispositivo in dispositivos:
        resultado = enviar(dispositivo.token, titulo, corpo, dados)
        if resultado == ResultadoPush.ENVIADO:
            enviado = True
        elif resultado == ResultadoPush.TOKEN_INVALIDO:
            db.delete(dispositivo)
    return enviado


def processar_lembretes(db: Session, agora: datetime, enviar: EnviarPush) -> int:
    """Envia os lembretes devidos em `agora` (com fuso); retorna quantos foram enviados."""
    agora_utc = agora.astimezone(UTC)
    agora_local = agora_utc.astimezone(FUSO_HORARIO)
    hoje: date = agora_local.date()

    candidatos = (
        db.execute(
            select(LembreteRefeicao).where(
                LembreteRefeicao.ativo.is_(True),
                or_(
                    LembreteRefeicao.ultimo_envio_em.is_(None),
                    LembreteRefeicao.ultimo_envio_em < hoje,
                ),
                LembreteRefeicao.horario <= agora_local.time(),
            )
        )
        .scalars()
        .all()
    )

    enviados = 0
    for lembrete in candidatos:
        momento = datetime.combine(hoje, lembrete.horario, tzinfo=FUSO_HORARIO)
        if agora_local - momento > TOLERANCIA_ENVIO:
            continue

        inicio_faixa = datetime.combine(
            hoje, JANELA_INICIO[TipoRefeicao(lembrete.tipo)], tzinfo=FUSO_HORARIO
        )
        inicio_janela = min(inicio_faixa, momento).astimezone(UTC)
        if _ja_registrou(db, lembrete.paciente_id, lembrete.tipo, inicio_janela, agora_utc):
            continue

        dispositivos = list(
            db.execute(
                select(DispositivoPush).where(DispositivoPush.paciente_id == lembrete.paciente_id)
            ).scalars()
        )
        if _notificar(db, lembrete, dispositivos, enviar):
            lembrete.ultimo_envio_em = hoje
            enviados += 1
        # Commit por lembrete: se o job cair no meio, o que ja foi enviado nao se repete.
        db.commit()

    return enviados
