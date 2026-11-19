"""Processamento diario de streak/XP e Leaderboard Semanal (RF05, RF16, RF29).

XP so vem de regras internas (a rota aberta POST /gamificacao/xp saiu):

- boas-vindas, no cadastro: 50
- refeicao registrada (uma por tipo de refeicao por dia local): 10
- refeicao registrada por foto (no lugar dos 10): 20
- dia dentro da meta (fechamento diario): 50
- incentivo do nutricionista vinculado (1 por dia): 10

Todo ganho grava um HistoricoXP, que alimenta o ranking semanal.
"""

from datetime import UTC, date, datetime, time
from decimal import Decimal

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.tempo import FUSO as FUSO_HORARIO
from app.core.tempo import em_fuso_local, hoje_local, janela_semanal
from app.models.historico_xp import HistoricoXP
from app.models.paciente import Paciente
from app.models.refeicao import ItemRefeicao, Refeicao
from app.schemas.gamificacao import LeaderboardItem, LeaderboardOut
from app.services import amizades as amizades_servico
from app.services.conquistas import registrar_conquistas

# Dia "dentro da meta": pelo menos 2 refeicoes e consumo a ate 30% da meta, para
# mais ou para menos. (Antes a regra era consumo <= 30% DA meta: quem comia o
# planejado nunca pontuava.)
TOLERANCIA_DA_META = Decimal("0.30")
MINIMO_REFEICOES_NO_DIA = 2
XP_POR_DIA = 50
XP_BOAS_VINDAS = 50
XP_REFEICAO = 10
XP_REFEICAO_FOTO = 20
XP_INCENTIVO = 10
CUSTO_BLOQUEIO_XP = 100


def cumpriu_meta_do_dia(meta_kcal: Decimal | None, refeicoes: int, calorias: Decimal) -> bool:
    """Regra unica do dia dentro da meta (ofensiva e desafio `sequencia_meta`)."""
    if meta_kcal is None or meta_kcal <= 0 or refeicoes < MINIMO_REFEICOES_NO_DIA:
        return False
    return abs(calorias - meta_kcal) <= meta_kcal * TOLERANCIA_DA_META


def registrar_xp(db: Session, paciente: Paciente, quantidade: int, motivo: str) -> HistoricoXP:
    """Soma XP e grava o historico, sem commit (entra na transacao de quem chamou)."""
    paciente.xp = (paciente.xp or 0) + quantidade
    registro = HistoricoXP(
        paciente_id=paciente.id,
        quantidade=quantidade,
        motivo=motivo,
        criado_em=datetime.now(UTC),
    )
    db.add(registro)
    return registro


def ja_recebeu(db: Session, paciente_id: int, *motivos: str) -> bool:
    return (
        db.scalar(
            select(HistoricoXP.id)
            .where(HistoricoXP.paciente_id == paciente_id, HistoricoXP.motivo.in_(motivos))
            .limit(1)
        )
        is not None
    )


def xp_por_refeicao(db: Session, refeicao: Refeicao, por_foto: bool) -> int:
    """Credita o XP de uma refeicao nova: um por tipo de refeicao por dia local."""
    chave = f"{refeicao.tipo}:{em_fuso_local(refeicao.consumida_em).date().isoformat()}"
    if ja_recebeu(db, refeicao.paciente_id, f"refeicao:{chave}", f"refeicao_foto:{chave}"):
        return 0
    paciente = db.get(Paciente, refeicao.paciente_id)
    if paciente is None:
        return 0
    if por_foto:
        registrar_xp(db, paciente, XP_REFEICAO_FOTO, f"refeicao_foto:{chave}")
        return XP_REFEICAO_FOTO
    registrar_xp(db, paciente, XP_REFEICAO, f"refeicao:{chave}")
    return XP_REFEICAO


def resgatar_bloqueio(db: Session, paciente_id: int) -> Paciente | None:
    """Debita XP e credita um bloqueio em uma única atualização."""
    paciente = db.scalar(
        update(Paciente)
        .where(Paciente.id == paciente_id, Paciente.xp >= CUSTO_BLOQUEIO_XP)
        .values(xp=Paciente.xp - CUSTO_BLOQUEIO_XP, bloqueios_perda=Paciente.bloqueios_perda + 1)
        .returning(Paciente)
    )
    if paciente is not None:
        db.commit()
    return paciente


class GamificacaoError(Exception):
    """Erro base para operacoes de gamificacao."""


class PacienteNaoEncontrado(GamificacaoError):
    """Paciente informado nao existe."""


def _garantir_paciente(db: Session, paciente_id: int) -> Paciente:
    paciente = db.get(Paciente, paciente_id)
    if not paciente:
        raise PacienteNaoEncontrado(f"Paciente {paciente_id} nao encontrado")
    return paciente


def conceder_xp(db: Session, paciente_id: int, quantidade: int, motivo: str) -> HistoricoXP:
    """Registra ganho de XP para um paciente e atualiza seu saldo total acumulado."""
    paciente = _garantir_paciente(db, paciente_id)
    registro = registrar_xp(db, paciente, quantidade, motivo)
    db.commit()
    db.refresh(registro)
    return registro


class IncentivoJaConcedido(GamificacaoError):
    """O paciente ja recebeu o incentivo do nutricionista hoje."""


def conceder_incentivo(db: Session, paciente_id: int) -> Paciente:
    """+10 XP dado pelo nutricionista vinculado, no maximo uma vez por dia local.

    Quem chama confere o vinculo ativo; aqui so vale a regra do limite diario.
    """
    paciente = _garantir_paciente(db, paciente_id)
    motivo = f"incentivo:{hoje_local().isoformat()}"
    if ja_recebeu(db, paciente_id, motivo):
        raise IncentivoJaConcedido
    registrar_xp(db, paciente, XP_INCENTIVO, motivo)
    db.commit()
    db.refresh(paciente)
    return paciente


def calcular_xp_semanal(
    db: Session, paciente_ids: list[int], inicio: datetime, fim: datetime
) -> dict[int, int]:
    """Calcula o total de XP obtido por cada paciente na janela temporal especificada."""
    if not paciente_ids:
        return {}

    totais: dict[int, int] = {pid: 0 for pid in paciente_ids}
    consulta = (
        select(
            HistoricoXP.paciente_id,
            func.coalesce(func.sum(HistoricoXP.quantidade), 0).label("total_xp"),
        )
        .where(
            HistoricoXP.paciente_id.in_(paciente_ids),
            HistoricoXP.criado_em >= inicio,
            HistoricoXP.criado_em <= fim,
        )
        .group_by(HistoricoXP.paciente_id)
    )

    linhas = db.execute(consulta).all()
    for row in linhas:
        totais[row.paciente_id] = int(row.total_xp)

    return totais


def obter_leaderboard_semanal(
    db: Session,
    paciente_id: int,
    limite: int = 10,
    referencia: datetime | None = None,
    incluir_solicitante: bool = True,
) -> LeaderboardOut:
    """Retorna o placar ordenado dos amigos por XP semanal (RF05.3, RF29)."""
    _garantir_paciente(db, paciente_id)

    amigo_ids = amizades_servico.obter_ids_amigos_aceitos(db, paciente_id)
    participantes_ids = list(set([paciente_id] + amigo_ids)) if incluir_solicitante else amigo_ids

    inicio, fim = janela_semanal(referencia)

    if not participantes_ids:
        return LeaderboardOut(
            inicio_semana=inicio,
            fim_semana=fim,
            total_participantes=0,
            posicao_solicitante=None,
            ranking=[],
        )

    totais_xp = calcular_xp_semanal(db, participantes_ids, inicio, fim)

    pacientes_consulta = select(Paciente).where(Paciente.id.in_(participantes_ids))
    pacientes = {p.id: p for p in db.scalars(pacientes_consulta).all()}

    # Agrupa candidatos para ordenacao
    candidatos = []
    for pid in participantes_ids:
        paciente = pacientes.get(pid)
        candidatos.append(
            {
                "paciente_id": pid,
                "username": paciente.username if paciente else None,
                "streak": paciente.streak if paciente else 0,
                "xp_semanal": totais_xp.get(pid, 0),
            }
        )

    # Ordenacao: Maior ganho de XP semanal -> Maior streak -> Menor ID
    candidatos.sort(key=lambda c: (-c["xp_semanal"], -c["streak"], c["paciente_id"]))

    posicao_solicitante: int | None = None
    ranking_itens: list[LeaderboardItem] = []

    for idx, c in enumerate(candidatos, start=1):
        if c["paciente_id"] == paciente_id:
            posicao_solicitante = idx

        if idx <= limite:
            ranking_itens.append(
                LeaderboardItem(
                    posicao=idx,
                    paciente_id=c["paciente_id"],
                    username=c["username"],
                    xp_semanal=c["xp_semanal"],
                    streak=c["streak"],
                    e_voce=(c["paciente_id"] == paciente_id),
                )
            )

    return LeaderboardOut(
        inicio_semana=inicio,
        fim_semana=fim,
        total_participantes=len(candidatos),
        posicao_solicitante=posicao_solicitante,
        ranking=ranking_itens,
    )


def listar_historico_xp(
    db: Session, paciente_id: int, limite: int = 50, deslocamento: int = 0
) -> list[HistoricoXP]:
    """Lista eventos individuais de XP concedidos a um paciente."""
    _garantir_paciente(db, paciente_id)
    consulta = (
        select(HistoricoXP)
        .where(HistoricoXP.paciente_id == paciente_id)
        .order_by(HistoricoXP.criado_em.desc())
        .offset(deslocamento)
        .limit(limite)
    )
    return list(db.scalars(consulta).all())


def processar_gamificacao_diaria(db: Session, dia: date) -> int:
    """Atualiza streak/XP para o dia local informado; retorna pacientes processados."""
    inicio_local = datetime.combine(dia, time.min, tzinfo=FUSO_HORARIO)
    fim_local = datetime.combine(dia, time.max, tzinfo=FUSO_HORARIO)
    inicio_utc = inicio_local.astimezone(UTC)
    fim_utc = fim_local.astimezone(UTC)

    consumo = (
        select(
            Refeicao.paciente_id,
            func.count(func.distinct(Refeicao.id)).label("quantidade_refeicoes"),
            func.coalesce(func.sum(ItemRefeicao.calorias_kcal), 0).label("calorias"),
        )
        .select_from(Refeicao)
        .outerjoin(ItemRefeicao, ItemRefeicao.refeicao_id == Refeicao.id)
        .where(Refeicao.consumida_em >= inicio_utc, Refeicao.consumida_em <= fim_utc)
        .group_by(Refeicao.paciente_id)
        .subquery()
    )
    resultados = {
        paciente_id: (quantidade, Decimal(calorias))
        for paciente_id, quantidade, calorias in db.execute(select(consumo)).all()
    }

    pacientes = db.execute(
        select(Paciente)
        .where(
            (Paciente.gamificacao_processada_em.is_(None))
            | (Paciente.gamificacao_processada_em < dia)
        )
        .order_by(Paciente.id)
        .with_for_update()
    ).scalars()
    ofensivas = {}
    for paciente in pacientes:
        streak_anterior = paciente.streak
        quantidade, calorias = resultados.get(paciente.id, (0, Decimal(0)))
        if cumpriu_meta_do_dia(paciente.meta_kcal, quantidade, calorias):
            paciente.streak += 1
            registrar_xp(db, paciente, XP_POR_DIA, f"meta_diaria:{dia.isoformat()}")
        elif paciente.streak > 0 and paciente.bloqueios_perda > 0:
            paciente.bloqueios_perda -= 1
        else:
            paciente.streak = 0
        paciente.gamificacao_processada_em = dia
        # Reconhece também a ofensiva que já existia antes do primeiro fechamento.
        ofensivas[paciente.id] = max(streak_anterior, paciente.streak)

    registrar_conquistas(db, ofensivas)
    db.commit()
    return len(ofensivas)


__all__ = ["FUSO_HORARIO", "hoje_local", "janela_semanal"]
