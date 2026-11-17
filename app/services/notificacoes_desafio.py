"""Notificacoes motivacionais diarias de desafios via FCM (Task 4.5, RF05.5).

Regra do job:
- Para cada desafio ativo no momento `agora` (`inicio_em <= agora <= fim_em`),
  calcula o placar dos participantes que aceitaram o desafio (`status == "aceito"`).
- Determina a posicao de cada participante e quantos dias faltam para o fim do
  desafio no fuso local (`America/Sao_Paulo`).
- Envia push via FCM (ex: "Voce esta em 2º lugar no desafio 'Semana equilibrada'.
  Faltam 2 dias!") para os aparelhos (`DispositivoPush`) do participante.
- Limite de frequencia: no maximo uma notificacao por participante por dia local
  (controlado por `NotificacaoDesafio` com chave unica `(paciente_id, enviado_em)`),
  evitando spam mesmo que o participante esteja em multiplos desafios ou que o
  job rode mais de uma vez no dia.
"""

from collections.abc import Callable
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.desafio import Desafio, TipoDesafio
from app.models.lembrete_refeicao import DispositivoPush
from app.models.notificacao_desafio import NotificacaoDesafio
from app.services.desafios import FUSO_HORARIO, _pontuacoes
from app.services.fcm import ResultadoPush

EnviarPush = Callable[[str, str, str, dict[str, str]], ResultadoPush]


def _ordenar_placar(desafio: Desafio, linhas: list) -> list:
    linhas_ordenadas = list(linhas)
    linhas_ordenadas.sort(
        key=lambda linha: (
            linha[2] is None,
            linha[2] or 0,
            linha[1].casefold(),
        ),
        reverse=desafio.tipo != TipoDesafio.VARIACAO_CALORICA.value,
    )
    return linhas_ordenadas


def _dias_restantes(desafio: Desafio, hoje: date) -> int:
    fim_em = desafio.fim_em
    fim_local = (
        (fim_em.replace(tzinfo=UTC) if fim_em.tzinfo is None else fim_em)
        .astimezone(FUSO_HORARIO)
        .date()
    )
    return max(0, (fim_local - hoje).days)


def montar_mensagem_desafio(
    nome_desafio: str, posicao: int, dias_restantes: int
) -> tuple[str, str]:
    """Gera titulo e corpo da notificacao motivacional (RF05.5)."""
    titulo = f"Desafio: {nome_desafio}"
    if dias_restantes == 0:
        trecho_dias = "hoje é o último dia para vencer o desafio"
    elif dias_restantes == 1:
        trecho_dias = "falta 1 dia para vencer o desafio"
    else:
        trecho_dias = f"faltam {dias_restantes} dias para vencer o desafio"

    corpo = f"Você está em {posicao}º lugar — {trecho_dias}!"
    return titulo, corpo


def _ja_notificado_hoje(db: Session, paciente_id: int, hoje: date) -> bool:
    return (
        db.scalar(
            select(NotificacaoDesafio.id).where(
                NotificacaoDesafio.paciente_id == paciente_id,
                NotificacaoDesafio.enviado_em == hoje,
            )
        )
        is not None
    )


def _notificar_participante(
    db: Session,
    dispositivos: list[DispositivoPush],
    desafio: Desafio,
    posicao: int,
    dias_restantes: int,
    enviar: EnviarPush,
) -> bool:
    """Envia push para todos os aparelhos do paciente; True se ao menos um recebeu."""
    titulo, corpo = montar_mensagem_desafio(desafio.nome, posicao, dias_restantes)
    dados = {
        "tipo_notificacao": "andamento_desafio",
        "desafio_id": str(desafio.id),
        "posicao": str(posicao),
        "dias_restantes": str(dias_restantes),
    }

    enviado = False
    for dispositivo in dispositivos:
        resultado = enviar(dispositivo.token, titulo, corpo, dados)
        if resultado == ResultadoPush.ENVIADO:
            enviado = True
        elif resultado == ResultadoPush.TOKEN_INVALIDO:
            db.delete(dispositivo)
    return enviado


def processar_notificacoes_desafios(db: Session, agora: datetime, enviar: EnviarPush) -> int:
    """Calcula a posicao nos desafios ativos em `agora` e envia push com limite diario."""
    agora_utc = agora.replace(tzinfo=UTC) if agora.tzinfo is None else agora.astimezone(UTC)
    agora_local = agora_utc.astimezone(FUSO_HORARIO)
    hoje: date = agora_local.date()

    desafios_ativos = list(
        db.scalars(
            select(Desafio)
            .where(
                Desafio.inicio_em <= agora_utc,
                Desafio.fim_em >= agora_utc,
            )
            .order_by(Desafio.fim_em.asc(), Desafio.id.asc())
        ).all()
    )

    enviados = 0
    for desafio in desafios_ativos:
        linhas = _pontuacoes(db, desafio, desafio.tipo)
        if not linhas:
            continue

        placar = _ordenar_placar(desafio, linhas)
        dias_restantes = _dias_restantes(desafio, hoje)

        for posicao, (paciente_id, _nome, _pontuacao) in enumerate(placar, start=1):
            if _ja_notificado_hoje(db, paciente_id, hoje):
                continue

            dispositivos = list(
                db.scalars(
                    select(DispositivoPush).where(DispositivoPush.paciente_id == paciente_id)
                ).all()
            )
            if not dispositivos:
                continue

            if _notificar_participante(db, dispositivos, desafio, posicao, dias_restantes, enviar):
                db.add(
                    NotificacaoDesafio(
                        paciente_id=paciente_id,
                        desafio_id=desafio.id,
                        posicao=posicao,
                        dias_restantes=dias_restantes,
                        enviado_em=hoje,
                    )
                )
                enviados += 1
            # Commit por participante para persistir envio/remocao de token invalido com seguranca.
            db.commit()

    return enviados
