"""Servico e job diario de deteccao de desvios significativos da meta (Task 5.4, RF10.2).

Regra de negocio:
- Cada nutricionista possui uma regra configuravel (`RegraAlertaDesvio`), com
  padrao de desvio > 20% (acima ou abaixo da meta diaria) por 3 dias consecutivos.
- A meta diaria de referencia e o total calorico do plano alimentar ativo do
  paciente (`PlanoAlimentar.totais["meta_kcal"]`); caso nao haja plano ativo com
  meta positiva, usa `Paciente.meta_kcal` (calculo basal da triagem).
- O job diario (`processar_alertas_desvio_diario`) avalia a janela de N dias
  consecutivos encerrada em `dia_referencia`. Se em todos os N dias o paciente
  registrou consumo com desvio percentual absoluto estritamente maior que
  `percentual_desvio`, gera um `AlertaDesvioPlano` (idempotente por
  nutricionista, paciente e data) e dispara a notificacao ao nutricionista.
"""

import logging
from collections.abc import Callable
from datetime import UTC, date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.alerta_desvio import AlertaDesvioPlano, DirecaoDesvio, RegraAlertaDesvio
from app.models.paciente import Paciente
from app.models.plano_alimentar import PlanoAlimentar
from app.models.refeicao import ItemRefeicao, Refeicao
from app.models.usuario import Usuario
from app.models.vinculo import StatusVinculo, Vinculo
from app.schemas.alerta_desvio import AlertaDesvioOut, RegraAlertaDesvioIn, RegraAlertaDesvioOut
from app.services.gamificacao import FUSO_HORARIO

logger = logging.getLogger(__name__)

PERCENTUAL_DESVIO_PADRAO = Decimal("20.00")
DIAS_CONSECUTIVOS_PADRAO = 3
DUAS_CASAS = Decimal("0.01")

# Callback (nutricionista_email, titulo, mensagem, alerta) -> bool
NotificarNutricionista = Callable[[str, str, str, AlertaDesvioPlano], bool]


class AlertaNaoEncontrado(Exception):
    """Nao existe alerta com esse id para o nutricionista autenticado."""


def notificar_nutricionista_log(
    email_nutricionista: str,
    titulo: str,
    mensagem: str,
    alerta: AlertaDesvioPlano,
) -> bool:
    """Canal padrao de notificacao ao nutricionista (log estruturado + painel web)."""
    logger.info(
        "Notificacao ao nutricionista (%s) [alerta_id=%s, paciente_id=%s]: %s - %s",
        email_nutricionista,
        alerta.id,
        alerta.paciente_id,
        titulo,
        mensagem,
    )
    return True


def obter_regra(db: Session, nutricionista_id: int) -> RegraAlertaDesvioOut:
    """Retorna a regra configurada pelo nutricionista ou os valores padrao (20%, 3 dias)."""
    regra = db.execute(
        select(RegraAlertaDesvio).where(RegraAlertaDesvio.nutricionista_id == nutricionista_id)
    ).scalar_one_or_none()
    if regra is None:
        return RegraAlertaDesvioOut(
            nutricionista_id=nutricionista_id,
            percentual_desvio=PERCENTUAL_DESVIO_PADRAO,
            dias_consecutivos=DIAS_CONSECUTIVOS_PADRAO,
            ativo=True,
        )
    return RegraAlertaDesvioOut.model_validate(regra)


def salvar_regra(
    db: Session, nutricionista_id: int, dados: RegraAlertaDesvioIn
) -> RegraAlertaDesvioOut:
    """Cria ou atualiza a regra configuravel de alerta de desvio do nutricionista."""
    regra = db.execute(
        select(RegraAlertaDesvio).where(RegraAlertaDesvio.nutricionista_id == nutricionista_id)
    ).scalar_one_or_none()
    if regra is None:
        regra = RegraAlertaDesvio(
            nutricionista_id=nutricionista_id,
            percentual_desvio=dados.percentual_desvio,
            dias_consecutivos=dados.dias_consecutivos,
            ativo=dados.ativo,
        )
        db.add(regra)
    else:
        regra.percentual_desvio = dados.percentual_desvio
        regra.dias_consecutivos = dados.dias_consecutivos
        regra.ativo = dados.ativo
    db.commit()
    db.refresh(regra)
    return RegraAlertaDesvioOut.model_validate(regra)


def _meta_kcal_do_paciente(db: Session, paciente: Paciente) -> Decimal | None:
    """Prioriza a meta do plano alimentar ativo; se nao houver, usa a meta basal."""
    plano = db.execute(
        select(PlanoAlimentar).where(
            PlanoAlimentar.paciente_id == paciente.id,
            PlanoAlimentar.ativo.is_(True),
        )
    ).scalar_one_or_none()
    if plano is not None:
        meta_plano = plano.totais["meta_kcal"]
        if meta_plano > 0:
            return meta_plano
    if paciente.meta_kcal is not None and paciente.meta_kcal > 0:
        return Decimal(paciente.meta_kcal)
    return None


def _consumo_no_dia(db: Session, paciente_id: int, dia: date) -> tuple[int, Decimal]:
    """Retorna (quantidade_refeicoes, calorias_totais) do paciente no dia local."""
    inicio_utc = datetime.combine(dia, time.min, tzinfo=FUSO_HORARIO).astimezone(UTC)
    fim_utc = datetime.combine(dia, time.max, tzinfo=FUSO_HORARIO).astimezone(UTC)

    linha = db.execute(
        select(
            func.count(func.distinct(Refeicao.id)),
            func.coalesce(func.sum(ItemRefeicao.calorias_kcal), 0),
        )
        .select_from(Refeicao)
        .outerjoin(ItemRefeicao, ItemRefeicao.refeicao_id == Refeicao.id)
        .where(
            Refeicao.paciente_id == paciente_id,
            Refeicao.consumida_em >= inicio_utc,
            Refeicao.consumida_em <= fim_utc,
        )
    ).one()
    return int(linha[0] or 0), Decimal(str(linha[1] or 0))


def _avaliar_janela_paciente(
    db: Session,
    paciente: Paciente,
    dia_referencia: date,
    percentual_limite: Decimal,
    dias_consecutivos: int,
) -> tuple[DirecaoDesvio, Decimal, Decimal, Decimal] | None:
    """Avalia se houve desvio > percentual_limite em todos os N dias consecutivos.

    Retorna `(direcao, meta_kcal, consumo_medio_kcal, percentual_medio_desvio)`
    quando o alerta deve ser disparado, ou `None` caso contrario.
    """
    meta_kcal = _meta_kcal_do_paciente(db, paciente)
    if meta_kcal is None or meta_kcal <= 0:
        return None

    direcoes: set[DirecaoDesvio] = set()
    consumos: list[Decimal] = []
    desvios_percentuais: list[Decimal] = []

    for deslocamento in range(dias_consecutivos):
        dia = dia_referencia - timedelta(days=deslocamento)
        qtd_refeicoes, calorias = _consumo_no_dia(db, paciente.id, dia)
        # Dias sem nenhum registro pertencem ao alerta de abandono (RF10.1), nao desvio de consumo.
        if qtd_refeicoes == 0:
            return None

        diferenca = calorias - meta_kcal
        desvio_pct = (abs(diferenca) / meta_kcal) * Decimal("100")
        if desvio_pct <= percentual_limite:
            return None

        direcoes.add(DirecaoDesvio.ACIMA if diferenca > 0 else DirecaoDesvio.ABAIXO)
        consumos.append(calorias)
        desvios_percentuais.append(desvio_pct)

    direcao_final = direcoes.pop() if len(direcoes) == 1 else DirecaoDesvio.AMBOS
    consumo_medio = (sum(consumos, Decimal("0")) / Decimal(dias_consecutivos)).quantize(
        DUAS_CASAS, rounding=ROUND_HALF_UP
    )
    desvio_medio = (sum(desvios_percentuais, Decimal("0")) / Decimal(dias_consecutivos)).quantize(
        DUAS_CASAS, rounding=ROUND_HALF_UP
    )
    meta_arredondada = meta_kcal.quantize(DUAS_CASAS, rounding=ROUND_HALF_UP)

    return direcao_final, meta_arredondada, consumo_medio, desvio_medio


def processar_alertas_desvio_diario(
    db: Session,
    dia_referencia: date,
    notificar: NotificarNutricionista = notificar_nutricionista_log,
    *,
    nutricionista_id: int | None = None,
) -> int:
    """Compara consumo x metas para todos os vinculos ativos e gera alertas de desvio.

    Retorna o total de novos alertas gerados na execucao.
    """
    consulta_vinculos = select(Vinculo).where(Vinculo.status == StatusVinculo.ATIVO.value)
    if nutricionista_id is not None:
        consulta_vinculos = consulta_vinculos.where(Vinculo.nutricionista_id == nutricionista_id)
    vinculos = list(db.execute(consulta_vinculos).scalars())
    if not vinculos:
        return 0

    regras_por_nutri = {
        r.nutricionista_id: r for r in db.execute(select(RegraAlertaDesvio)).scalars()
    }

    gerados = 0
    for vinculo in vinculos:
        regra = regras_por_nutri.get(vinculo.nutricionista_id)
        if regra is not None and not regra.ativo:
            continue

        percentual_limite = (
            Decimal(regra.percentual_desvio) if regra is not None else PERCENTUAL_DESVIO_PADRAO
        )
        dias_consecutivos = (
            regra.dias_consecutivos if regra is not None else DIAS_CONSECUTIVOS_PADRAO
        )

        ja_existe = db.execute(
            select(AlertaDesvioPlano.id).where(
                AlertaDesvioPlano.nutricionista_id == vinculo.nutricionista_id,
                AlertaDesvioPlano.paciente_id == vinculo.paciente_id,
                AlertaDesvioPlano.data_referencia == dia_referencia,
            )
        ).first()
        if ja_existe is not None:
            continue

        paciente = db.get(Paciente, vinculo.paciente_id)
        if paciente is None:
            continue

        avaliacao = _avaliar_janela_paciente(
            db,
            paciente,
            dia_referencia,
            percentual_limite,
            dias_consecutivos,
        )
        if avaliacao is None:
            continue

        direcao, meta_kcal, consumo_medio, desvio_medio = avaliacao
        alerta = AlertaDesvioPlano(
            nutricionista_id=vinculo.nutricionista_id,
            paciente_id=vinculo.paciente_id,
            data_referencia=dia_referencia,
            direcao=direcao.value,
            dias_consecutivos=dias_consecutivos,
            percentual_limite=percentual_limite,
            percentual_medio_desvio=desvio_medio,
            meta_kcal=meta_kcal,
            consumo_medio_kcal=consumo_medio,
            lido=False,
        )
        db.add(alerta)
        db.flush()

        usuario_nutri = db.get(Usuario, vinculo.nutricionista_id)
        usuario_paciente = db.get(Usuario, vinculo.paciente_id)
        nome_paciente = usuario_paciente.nome if usuario_paciente else f"Paciente #{paciente.id}"
        email_nutri = usuario_nutri.email if usuario_nutri else ""

        resumo_direcao = {
            DirecaoDesvio.ACIMA: "acima da meta",
            DirecaoDesvio.ABAIXO: "abaixo da meta",
            DirecaoDesvio.AMBOS: "fora da meta",
        }[direcao]
        titulo = f"Desvio de meta: {nome_paciente}"
        mensagem = (
            f"{nome_paciente} ficou {desvio_medio}% {resumo_direcao} "
            f"(limite >{percentual_limite}%) por {dias_consecutivos} dias consecutivos."
        )
        if notificar(email_nutri, titulo, mensagem, alerta):
            alerta.notificado_em = datetime.now(UTC)

        gerados += 1

    db.commit()
    return gerados


def listar_alertas(
    db: Session,
    nutricionista_id: int,
    *,
    paciente_id: int | None = None,
    apenas_nao_lidos: bool = False,
) -> list[AlertaDesvioOut]:
    """Lista os alertas de desvio do nutricionista, do mais recente para o mais antigo."""
    consulta = (
        select(AlertaDesvioPlano, Usuario.nome, Usuario.email)
        .join(Usuario, Usuario.id == AlertaDesvioPlano.paciente_id)
        .where(AlertaDesvioPlano.nutricionista_id == nutricionista_id)
        .order_by(AlertaDesvioPlano.data_referencia.desc(), AlertaDesvioPlano.id.desc())
    )
    if paciente_id is not None:
        consulta = consulta.where(AlertaDesvioPlano.paciente_id == paciente_id)
    if apenas_nao_lidos:
        consulta = consulta.where(AlertaDesvioPlano.lido.is_(False))

    linhas = db.execute(consulta).all()
    return [
        AlertaDesvioOut(
            id=alerta.id,
            nutricionista_id=alerta.nutricionista_id,
            paciente_id=alerta.paciente_id,
            paciente_nome=nome,
            paciente_email=email,
            data_referencia=alerta.data_referencia,
            direcao=DirecaoDesvio(alerta.direcao),
            dias_consecutivos=alerta.dias_consecutivos,
            percentual_limite=alerta.percentual_limite,
            percentual_medio_desvio=alerta.percentual_medio_desvio,
            meta_kcal=alerta.meta_kcal,
            consumo_medio_kcal=alerta.consumo_medio_kcal,
            lido=alerta.lido,
            notificado_em=alerta.notificado_em,
            criado_em=alerta.criado_em,
        )
        for alerta, nome, email in linhas
    ]


def marcar_alerta_como_lido(db: Session, nutricionista_id: int, alerta_id: int) -> AlertaDesvioOut:
    """Marca um alerta do nutricionista como lido."""
    linha = db.execute(
        select(AlertaDesvioPlano, Usuario.nome, Usuario.email)
        .join(Usuario, Usuario.id == AlertaDesvioPlano.paciente_id)
        .where(
            AlertaDesvioPlano.id == alerta_id,
            AlertaDesvioPlano.nutricionista_id == nutricionista_id,
        )
    ).one_or_none()
    if linha is None:
        raise AlertaNaoEncontrado

    alerta, nome, email = linha
    alerta.lido = True
    db.commit()
    db.refresh(alerta)
    return AlertaDesvioOut(
        id=alerta.id,
        nutricionista_id=alerta.nutricionista_id,
        paciente_id=alerta.paciente_id,
        paciente_nome=nome,
        paciente_email=email,
        data_referencia=alerta.data_referencia,
        direcao=DirecaoDesvio(alerta.direcao),
        dias_consecutivos=alerta.dias_consecutivos,
        percentual_limite=alerta.percentual_limite,
        percentual_medio_desvio=alerta.percentual_medio_desvio,
        meta_kcal=alerta.meta_kcal,
        consumo_medio_kcal=alerta.consumo_medio_kcal,
        lido=alerta.lido,
        notificado_em=alerta.notificado_em,
        criado_em=alerta.criado_em,
    )
