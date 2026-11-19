"""Monta o perfil do paciente (app: Inicio/Perfil; painel: ficha do paciente)."""

from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.paciente import Genero, NivelAtividade, Paciente
from app.models.refeicao import Refeicao
from app.models.usuario import Nutricionista, Usuario
from app.models.vinculo import StatusVinculo, Vinculo
from app.schemas.perfil import (
    GamificacaoPerfilOut,
    MetaDiariaOut,
    NutricionistaResumo,
    PerfilPacienteOut,
    PlanoResumo,
)
from app.services.calculo_basal import calcular_tmb, fator_de_atividade
from app.services.metas import meta_do_paciente, plano_ativo

# (nome, XP minimo). O prototipo mostra 520 XP como "Ouro".
DIVISOES: tuple[tuple[str, int], ...] = (
    ("Bronze", 0),
    ("Prata", 200),
    ("Ouro", 500),
    ("Diamante", 1500),
)
UMA_CASA = Decimal("0.1")


class PacienteNaoEncontrado(Exception):
    pass


def divisao_por_xp(xp: int) -> tuple[str, str | None, int | None]:
    """Divisao atual, a proxima e quanto XP falta para ela."""
    atual = DIVISOES[0]
    proxima: tuple[str, int] | None = None
    for i, divisao in enumerate(DIVISOES):
        if xp >= divisao[1]:
            atual = divisao
            proxima = DIVISOES[i + 1] if i + 1 < len(DIVISOES) else None
    if proxima is None:
        return atual[0], None, None
    return atual[0], proxima[0], proxima[1] - xp


def classificar_imc(imc: Decimal) -> str:
    """Faixas da OMS para adultos."""
    if imc < Decimal("18.5"):
        return "Abaixo do peso"
    if imc < 25:
        return "Eutrófico"
    if imc < 30:
        return "Sobrepeso"
    if imc < 35:
        return "Obesidade grau I"
    if imc < 40:
        return "Obesidade grau II"
    return "Obesidade grau III"


def _imc(peso_kg: Decimal | None, altura_cm: Decimal | None) -> Decimal | None:
    if not peso_kg or not altura_cm:
        return None
    metros = Decimal(altura_cm) / 100
    return (Decimal(peso_kg) / (metros * metros)).quantize(UMA_CASA, rounding=ROUND_HALF_UP)


def _tmb(paciente: Paciente) -> Decimal | None:
    if None in (paciente.peso_kg, paciente.altura_cm, paciente.idade, paciente.genero):
        return None
    try:
        genero = Genero(paciente.genero)
    except ValueError:
        return None
    return calcular_tmb(
        peso_kg=Decimal(paciente.peso_kg),
        altura_cm=Decimal(paciente.altura_cm),
        idade=paciente.idade,
        genero=genero,
    )


def _fator(nivel: str | None) -> Decimal | None:
    try:
        return fator_de_atividade(NivelAtividade(nivel)) if nivel else None
    except ValueError:
        return None


def montar_perfil(db: Session, paciente_id: int) -> PerfilPacienteOut:
    paciente = db.get(Paciente, paciente_id)
    usuario = db.get(Usuario, paciente_id)
    if paciente is None or usuario is None:
        raise PacienteNaoEncontrado

    meta = meta_do_paciente(db, paciente)
    imc = _imc(paciente.peso_kg, paciente.altura_cm)
    divisao, proxima, falta = divisao_por_xp(paciente.xp)
    refeicoes = db.scalar(
        select(func.count(Refeicao.id)).where(Refeicao.paciente_id == paciente_id)
    )
    vinculo = db.execute(
        select(Usuario, Nutricionista)
        .join(Vinculo, Vinculo.nutricionista_id == Usuario.id)
        .join(Nutricionista, Nutricionista.id == Usuario.id)
        .where(Vinculo.paciente_id == paciente_id, Vinculo.status == StatusVinculo.ATIVO.value)
        .order_by(Vinculo.id.desc())
    ).first()
    plano = plano_ativo(db, paciente_id)

    return PerfilPacienteOut(
        paciente_id=paciente_id,
        nome=usuario.nome,
        email=usuario.email,
        membro_desde=usuario.criado_em,
        idade=paciente.idade,
        genero=paciente.genero,
        peso_kg=paciente.peso_kg,
        altura_cm=paciente.altura_cm,
        imc=imc,
        classificacao_imc=classificar_imc(imc) if imc is not None else None,
        tmb_kcal=_tmb(paciente),
        nivel_atividade=paciente.nivel_atividade,
        fator_atividade=_fator(paciente.nivel_atividade),
        meta=MetaDiariaOut(
            kcal=meta.kcal,
            proteinas_g=meta.proteinas_g,
            carboidratos_g=meta.carboidratos_g,
            gorduras_g=meta.gorduras_g,
            origem=meta.origem,
        ),
        gamificacao=GamificacaoPerfilOut(
            xp=paciente.xp,
            ofensiva=paciente.streak,
            bloqueios=paciente.bloqueios_perda,
            divisao=divisao,
            proxima_divisao=proxima,
            xp_para_proxima=falta,
            refeicoes_registradas=refeicoes or 0,
        ),
        nutricionista=(
            NutricionistaResumo(id=vinculo[0].id, nome=vinculo[0].nome, crn=vinculo[1].crn)
            if vinculo
            else None
        ),
        plano_ativo=(
            PlanoResumo(id=plano.id, titulo=plano.titulo, versao=plano.versao) if plano else None
        ),
    )
