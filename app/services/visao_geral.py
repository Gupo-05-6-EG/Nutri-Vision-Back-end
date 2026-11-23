"""Visao geral da carteira do nutricionista: indicadores e monitoramento por paciente.

Regras (documentadas no README):

- **adesao semanal**: dos ultimos 7 dias locais completos (ontem para tras), a
  porcentagem em que o paciente ficou dentro da meta - a mesma regra da ofensiva
  (pelo menos 2 refeicoes e consumo a ate 30% da meta);
- **em risco**: vinculo ativo com alerta de desvio nao lido, ou sem nenhum
  registro de refeicao nas ultimas 48 h;
- **pendente**: o paciente resgatou o codigo e ainda nao aceitou o vinculo.
"""

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.tempo import em_fuso_local, intervalo_do_dia
from app.core.texto import sem_acento
from app.models.alerta_desvio import AlertaDesvioPlano
from app.models.paciente import Paciente
from app.models.refeicao import ItemRefeicao, Refeicao
from app.models.usuario import Usuario
from app.models.vinculo import StatusVinculo, Vinculo
from app.schemas.visao_geral import (
    ContagemSituacoes,
    IndicadoresCarteira,
    PacienteMonitorado,
    UltimoRegistro,
    VisaoGeralOut,
)
from app.services.gamificacao import cumpriu_meta_do_dia
from app.services.metas import meta_kcal_do_paciente

DIAS_ADESAO = 7
HORAS_SEM_REGISTRO = 48
FILTROS = {"todos", "ativos", "em_risco", "pendentes"}


def _consumo_por_dia(
    db: Session, paciente_ids: list[int], desde: date
) -> dict[int, dict[date, tuple[int, Decimal]]]:
    """(refeicoes, kcal) por paciente e dia local, de `desde` ate hoje."""
    inicio, _ = intervalo_do_dia(desde)
    linhas = db.execute(
        select(
            Refeicao.paciente_id,
            Refeicao.id,
            Refeicao.consumida_em,
            func.coalesce(func.sum(ItemRefeicao.calorias_kcal), 0),
        )
        .outerjoin(ItemRefeicao, ItemRefeicao.refeicao_id == Refeicao.id)
        .where(Refeicao.paciente_id.in_(paciente_ids), Refeicao.consumida_em >= inicio)
        .group_by(Refeicao.paciente_id, Refeicao.id, Refeicao.consumida_em)
    ).all()
    por_dia: dict[int, dict[date, list]] = defaultdict(lambda: defaultdict(lambda: [0, Decimal(0)]))
    for paciente_id, _id, consumida_em, kcal in linhas:
        dia = em_fuso_local(consumida_em).date()
        por_dia[paciente_id][dia][0] += 1
        por_dia[paciente_id][dia][1] += Decimal(str(kcal))
    return {pid: {d: (v[0], v[1]) for d, v in dias.items()} for pid, dias in por_dia.items()}


def _ultimos_registros(db: Session, paciente_ids: list[int]) -> dict[int, Refeicao]:
    ultimo = (
        select(Refeicao.paciente_id, func.max(Refeicao.consumida_em).label("em"))
        .where(Refeicao.paciente_id.in_(paciente_ids))
        .group_by(Refeicao.paciente_id)
        .subquery()
    )
    refeicoes = db.scalars(
        select(Refeicao).join(
            ultimo,
            (Refeicao.paciente_id == ultimo.c.paciente_id) & (Refeicao.consumida_em == ultimo.c.em),
        )
    ).all()
    return {r.paciente_id: r for r in refeicoes}


def _alertas_nao_lidos(db: Session, nutricionista_id: int) -> dict[int, int]:
    return dict(
        db.execute(
            select(AlertaDesvioPlano.paciente_id, func.count(AlertaDesvioPlano.id))
            .where(
                AlertaDesvioPlano.nutricionista_id == nutricionista_id,
                AlertaDesvioPlano.lido.is_(False),
            )
            .group_by(AlertaDesvioPlano.paciente_id)
        ).all()
    )


def _media(valores: list[float]) -> float | None:
    return round(sum(valores) / len(valores), 1) if valores else None


def montar_visao_geral(
    db: Session,
    nutricionista_id: int,
    *,
    filtro: str = "todos",
    busca: str | None = None,
    pagina: int = 1,
    por_pagina: int = 10,
    agora: datetime | None = None,
) -> VisaoGeralOut:
    agora = agora or datetime.now(UTC)
    hoje = em_fuso_local(agora).date()
    linhas = db.execute(
        select(Vinculo, Usuario, Paciente)
        .join(Usuario, Usuario.id == Vinculo.paciente_id)
        .join(Paciente, Paciente.id == Vinculo.paciente_id)
        .where(
            Vinculo.nutricionista_id == nutricionista_id,
            Vinculo.status.in_((StatusVinculo.ATIVO.value, StatusVinculo.PENDENTE.value)),
        )
        .order_by(Usuario.nome, Usuario.id)
    ).all()

    ativos_ids = [p.id for v, _, p in linhas if v.status == StatusVinculo.ATIVO.value]
    consumo = _consumo_por_dia(db, ativos_ids, hoje - timedelta(days=DIAS_ADESAO))
    ultimos = _ultimos_registros(db, ativos_ids)
    alertas = _alertas_nao_lidos(db, nutricionista_id)
    limite_sem_registro = agora - timedelta(hours=HORAS_SEM_REGISTRO)

    monitorados: list[PacienteMonitorado] = []
    for vinculo, usuario, paciente in linhas:
        pendente = vinculo.status == StatusVinculo.PENDENTE.value
        dias = consumo.get(paciente.id, {})
        meta = None if pendente else meta_kcal_do_paciente(db, paciente)
        adesao = None
        if meta is not None:
            dentro = sum(
                cumpriu_meta_do_dia(meta, *dias.get(hoje - timedelta(days=n), (0, Decimal(0))))
                for n in range(1, DIAS_ADESAO + 1)
            )
            adesao = round(100 * dentro / DIAS_ADESAO, 1)
        ultima = ultimos.get(paciente.id)
        ultima_em = None
        if ultima is not None:
            ultima_em = (
                ultima.consumida_em
                if ultima.consumida_em.tzinfo
                else ultima.consumida_em.replace(tzinfo=UTC)
            )
        motivo = None
        if not pendente:
            if alertas.get(paciente.id):
                motivo = "alerta_desvio"
            elif ultima_em is None or ultima_em < limite_sem_registro:
                motivo = "sem_registro"
        situacao = "pendente" if pendente else ("em_risco" if motivo else "ativo")
        monitorados.append(
            PacienteMonitorado(
                paciente_id=paciente.id,
                nome=usuario.nome,
                email=usuario.email,
                status_vinculo=vinculo.status,
                vinculado_em=vinculo.criado_em,
                situacao=situacao,
                motivo_risco=motivo,
                meta_kcal=meta,
                consumo_hoje_kcal=dias.get(hoje, (0, Decimal(0)))[1],
                adesao_semanal_pct=adesao,
                ofensiva=paciente.streak,
                xp=paciente.xp,
                alertas_nao_lidos=alertas.get(paciente.id, 0),
                ultimo_registro=(
                    UltimoRegistro(tipo=ultima.tipo, em=ultima_em) if ultima is not None else None
                ),
            )
        )

    ativos = [m for m in monitorados if m.situacao != "pendente"]
    em_risco = [m for m in monitorados if m.situacao == "em_risco"]
    pendentes = [m for m in monitorados if m.situacao == "pendente"]
    indicadores = IndicadoresCarteira(
        pacientes_ativos=len(ativos),
        pacientes_pendentes=len(pendentes),
        alertas_criticos=len(em_risco),
        adesao_media_pct=_media(
            [m.adesao_semanal_pct for m in ativos if m.adesao_semanal_pct is not None]
        ),
        ofensiva_media_dias=_media([float(m.ofensiva) for m in ativos]),
    )
    contagens = ContagemSituacoes(
        todos=len(monitorados), ativos=len(ativos), em_risco=len(em_risco), pendentes=len(pendentes)
    )

    selecionados = {
        "todos": monitorados,
        "ativos": ativos,
        "em_risco": em_risco,
        "pendentes": pendentes,
    }[filtro]
    termo = sem_acento(busca)
    if termo:
        selecionados = [
            m for m in selecionados if termo in sem_acento(m.nome) or termo in m.email.lower()
        ]
    inicio = (pagina - 1) * por_pagina
    return VisaoGeralOut(
        indicadores=indicadores,
        contagens=contagens,
        total=len(selecionados),
        pagina=pagina,
        por_pagina=por_pagina,
        pacientes=selecionados[inicio : inicio + por_pagina],
    )
