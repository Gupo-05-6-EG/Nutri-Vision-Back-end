"""Regras de negocio do plano alimentar (RF09.1) e do seu historico (RF08, RNF08)."""

from typing import Any, NamedTuple

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models.alimento_taco import AlimentoTaco
from app.models.auditoria import EntidadeAuditada
from app.models.paciente import Paciente
from app.models.plano_alimentar import AlimentoRefeicaoPlano, PlanoAlimentar, RefeicaoPlano
from app.models.usuario import Perfil, Usuario
from app.models.vinculo import StatusVinculo, Vinculo
from app.schemas.plano_alimentar import PlanoAlimentarIn, PlanoAlimentarOut
from app.services.auditoria import registrar_auditoria


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
            Vinculo.nutricionista_id == usuario.id,
            Vinculo.paciente_id == paciente_id,
            Vinculo.status == StatusVinculo.ATIVO.value,
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


class Autor(NamedTuple):
    id: int
    nome: str


def _copia_do_plano(plano: PlanoAlimentar) -> dict[str, Any]:
    """O plano como a API o devolve (numeros no JSON), para a auditoria."""
    return PlanoAlimentarOut.model_validate(plano).model_dump(mode="json")


def _plano_ativo_ou_none(db: Session, paciente_id: int) -> PlanoAlimentar | None:
    return db.execute(
        select(PlanoAlimentar).where(
            PlanoAlimentar.paciente_id == paciente_id, PlanoAlimentar.ativo.is_(True)
        )
    ).scalar_one_or_none()


def prescrever_plano(
    db: Session, nutricionista: Usuario, paciente_id: int, dados: PlanoAlimentarIn
) -> PlanoAlimentar:
    """Salva o plano do paciente como uma versao nova (RF08).

    Prescrever o primeiro plano e editar um plano existente sao a mesma operacao:
    a versao anterior e desativada, mas continua no banco, e a mudanca entra na
    auditoria com os valores de antes e depois (RNF08), na mesma transacao.
    """
    _exigir_acesso(db, nutricionista, paciente_id)
    _conferir_alimentos_taco(db, dados)

    # Trava a linha do paciente: duas edicoes simultaneas esperam a vez em vez de
    # disputar o mesmo numero de versao (o UNIQUE barraria a segunda com erro).
    db.execute(select(Paciente.id).where(Paciente.id == paciente_id).with_for_update())

    anterior = _plano_ativo_ou_none(db, paciente_id)
    antes = _copia_do_plano(anterior) if anterior is not None else None
    ultima_versao = db.scalar(
        select(func.max(PlanoAlimentar.versao)).where(PlanoAlimentar.paciente_id == paciente_id)
    )

    db.execute(
        update(PlanoAlimentar)
        .where(PlanoAlimentar.paciente_id == paciente_id, PlanoAlimentar.ativo.is_(True))
        .values(ativo=False)
    )
    plano = PlanoAlimentar(
        paciente_id=paciente_id,
        nutricionista_id=nutricionista.id,
        versao=(ultima_versao or 0) + 1,
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
    db.flush()  # gera o id e o criado_em do plano, que a auditoria registra

    registrar_auditoria(
        db,
        paciente_id=paciente_id,
        autor_id=nutricionista.id,
        entidade=EntidadeAuditada.PLANO_ALIMENTAR,
        registro_id=plano.id,
        antes=antes,
        depois=_copia_do_plano(plano),
    )
    db.commit()
    db.refresh(plano)
    return plano


def plano_ativo(db: Session, usuario: Usuario, paciente_id: int) -> PlanoAlimentar:
    _exigir_acesso(db, usuario, paciente_id)
    plano = _plano_ativo_ou_none(db, paciente_id)
    if plano is None:
        raise PlanoNaoEncontrado
    return plano


def historico_de_versoes(
    db: Session, nutricionista: Usuario, paciente_id: int
) -> list[tuple[PlanoAlimentar, Autor | None]]:
    """Todas as versoes do plano do paciente, da mais nova para a mais antiga.

    Cada versao vem com o nutricionista que a salvou, ou `None` se a conta dele
    foi removida depois.
    """
    _exigir_acesso(db, nutricionista, paciente_id)
    linhas = db.execute(
        select(PlanoAlimentar, Usuario.id, Usuario.nome)
        .outerjoin(Usuario, Usuario.id == PlanoAlimentar.nutricionista_id)
        .where(PlanoAlimentar.paciente_id == paciente_id)
        .order_by(PlanoAlimentar.versao.desc())
    ).all()
    return [
        (plano, Autor(autor_id, autor_nome) if autor_id is not None else None)
        for plano, autor_id, autor_nome in linhas
    ]
