"""Regras de negocio do plano alimentar (RF09.1)."""

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.alimento_taco import AlimentoTaco
from app.models.paciente import Paciente
from app.models.plano_alimentar import AlimentoRefeicaoPlano, PlanoAlimentar, RefeicaoPlano
from app.models.usuario import Perfil, Usuario
from app.models.vinculo import Vinculo
from app.schemas.plano_alimentar import PlanoAlimentarIn


class PacienteNaoEncontrado(Exception):
    """`paciente_id` nao corresponde a um paciente cadastrado."""


class AcessoNegado(Exception):
    """Quem chama nao e o proprio paciente nem um nutricionista vinculado a ele."""


class PlanoNaoEncontrado(Exception):
    """O paciente ainda nao tem plano ativo."""


class AlimentoTacoNaoEncontrado(Exception):
    """Algum `alimento_taco_id` informado nao existe na TACO."""


def _exigir_acesso(db: Session, usuario: Usuario, paciente_id: int) -> None:
    if db.get(Paciente, paciente_id) is None:
        raise PacienteNaoEncontrado
    if usuario.perfil == Perfil.PACIENTE:
        if usuario.id != paciente_id:
            raise AcessoNegado
        return
    vinculado = db.execute(
        select(Vinculo.id).where(
            Vinculo.nutricionista_id == usuario.id, Vinculo.paciente_id == paciente_id
        )
    ).first()
    if vinculado is None:
        raise AcessoNegado


def _conferir_alimentos_taco(db: Session, dados: PlanoAlimentarIn) -> None:
    ids = {
        alimento.alimento_taco_id
        for refeicao in dados.refeicoes
        for alimento in refeicao.alimentos
        if alimento.alimento_taco_id is not None
    }
    if not ids:
        return
    encontrados = set(db.execute(select(AlimentoTaco.id).where(AlimentoTaco.id.in_(ids))).scalars())
    if encontrados != ids:
        raise AlimentoTacoNaoEncontrado


def prescrever_plano(
    db: Session, nutricionista: Usuario, paciente_id: int, dados: PlanoAlimentarIn
) -> PlanoAlimentar:
    """Cria o plano do paciente e desativa o plano ativo anterior, se houver."""
    _exigir_acesso(db, nutricionista, paciente_id)
    _conferir_alimentos_taco(db, dados)

    db.execute(
        update(PlanoAlimentar)
        .where(PlanoAlimentar.paciente_id == paciente_id, PlanoAlimentar.ativo.is_(True))
        .values(ativo=False)
    )
    plano = PlanoAlimentar(
        paciente_id=paciente_id,
        nutricionista_id=nutricionista.id,
        titulo=dados.titulo,
        observacao=dados.observacao,
        ativo=True,
        refeicoes=[
            RefeicaoPlano(
                ordem=ordem,
                nome=refeicao.nome,
                horario=refeicao.horario,
                meta_kcal=refeicao.meta_kcal,
                meta_proteinas_g=refeicao.meta_proteinas_g,
                observacao=refeicao.observacao,
                alimentos=[
                    AlimentoRefeicaoPlano(ordem=posicao, **alimento.model_dump())
                    for posicao, alimento in enumerate(refeicao.alimentos)
                ],
            )
            for ordem, refeicao in enumerate(dados.refeicoes)
        ],
    )
    db.add(plano)
    db.commit()
    db.refresh(plano)
    return plano


def plano_ativo(db: Session, usuario: Usuario, paciente_id: int) -> PlanoAlimentar:
    _exigir_acesso(db, usuario, paciente_id)
    plano = db.execute(
        select(PlanoAlimentar).where(
            PlanoAlimentar.paciente_id == paciente_id, PlanoAlimentar.ativo.is_(True)
        )
    ).scalar_one_or_none()
    if plano is None:
        raise PlanoNaoEncontrado
    return plano
