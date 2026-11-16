"""Regras de negocio do sistema social e amizades (RF05)."""

from datetime import UTC, datetime

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.models.amizade import Amizade, StatusAmizade
from app.models.paciente import Paciente
from app.schemas.amizade import AmigoItem


class AmizadesError(Exception):
    """Erro base das operacoes de amizades."""


class PacienteNaoEncontrado(AmizadesError):
    """Paciente informado nao existe no sistema."""


class AmizadeNaoEncontrada(AmizadesError):
    """Registro de amizade nao encontrado."""


class AutoAmizadeNaoPermitida(AmizadesError):
    """Um paciente nao pode solicitar amizade a si mesmo."""


class AmizadeJaExiste(AmizadesError):
    """Os pacientes ja possuem vinculo de amizade ativo."""


class SolicitacaoJaPendente(AmizadesError):
    """Ja existe solicitacao pendente entre os pacientes."""


class SolicitacaoJaRespondida(AmizadesError):
    """A solicitacao ja foi aceita ou recusada anteriormente."""


class OperacaoNaoPermitida(AmizadesError):
    """O paciente nao tem permissao para realizar esta acao."""


def _garantir_paciente(db: Session, paciente_id: int) -> Paciente:
    paciente = db.get(Paciente, paciente_id)
    if not paciente:
        raise PacienteNaoEncontrado(f"Paciente {paciente_id} nao encontrado")
    return paciente


def solicitar_amizade(db: Session, pac_id: int, amigo_id: int) -> Amizade:
    """Envia uma solicitacao de amizade entre dois pacientes."""
    if pac_id == amigo_id:
        raise AutoAmizadeNaoPermitida("Um paciente nao pode ser amigo de si mesmo")

    _garantir_paciente(db, pac_id)
    _garantir_paciente(db, amigo_id)

    # Verifica se ja existe relacionamento previo entre ambos em qualquer sentido
    consulta = select(Amizade).where(
        or_(
            and_(Amizade.pac_id == pac_id, Amizade.amigo_id == amigo_id),
            and_(Amizade.pac_id == amigo_id, Amizade.amigo_id == pac_id),
        )
    )
    amizade_existente = db.scalars(consulta).first()

    if amizade_existente:
        if amizade_existente.status == StatusAmizade.ACEITO:
            raise AmizadeJaExiste("Os pacientes ja sao amigos")
        if amizade_existente.status == StatusAmizade.PENDENTE:
            if amizade_existente.pac_id == pac_id:
                raise SolicitacaoJaPendente("Solicitacao de amizade ja enviada e pendente")
            # O outro usuario ja havia enviado o convite: aceita automaticamente
            amizade_existente.status = StatusAmizade.ACEITO
            db.commit()
            db.refresh(amizade_existente)
            return amizade_existente
        # Caso tenha sido recusada no passado, renova como nova solicitacao pendente
        amizade_existente.pac_id = pac_id
        amizade_existente.amigo_id = amigo_id
        amizade_existente.status = StatusAmizade.PENDENTE
        amizade_existente.criado_em = datetime.now(UTC)
        db.commit()
        db.refresh(amizade_existente)
        return amizade_existente

    nova_amizade = Amizade(
        pac_id=pac_id,
        amigo_id=amigo_id,
        status=StatusAmizade.PENDENTE,
    )
    db.add(nova_amizade)
    db.commit()
    db.refresh(nova_amizade)
    return nova_amizade


def responder_solicitacao(db: Session, amizade_id: int, paciente_id: int, aceitar: bool) -> Amizade:
    """Aceita ou recusa uma solicitacao de amizade recebida."""
    amizade = db.get(Amizade, amizade_id)
    if not amizade:
        raise AmizadeNaoEncontrada("Solicitacao de amizade nao encontrada")

    if amizade.amigo_id != paciente_id:
        raise OperacaoNaoPermitida(
            "Apenas o paciente convidado pode aceitar ou recusar a solicitacao"
        )

    if amizade.status != StatusAmizade.PENDENTE:
        raise SolicitacaoJaRespondida("Esta solicitacao ja foi processada anteriormente")

    amizade.status = StatusAmizade.ACEITO if aceitar else StatusAmizade.RECUSADO
    db.commit()
    db.refresh(amizade)
    return amizade


def listar_amizades(
    db: Session, paciente_id: int, status: StatusAmizade | None = None
) -> list[AmigoItem]:
    """Lista as amizades e solicitacoes vinculadas ao paciente."""
    _garantir_paciente(db, paciente_id)

    filtros = [or_(Amizade.pac_id == paciente_id, Amizade.amigo_id == paciente_id)]
    if status is not None:
        filtros.append(Amizade.status == status)

    consulta = select(Amizade).where(*filtros).order_by(Amizade.criado_em.desc())
    registros = db.scalars(consulta).all()

    resultado: list[AmigoItem] = []
    for reg in registros:
        outro_id = reg.amigo_id if reg.pac_id == paciente_id else reg.pac_id
        outro = db.get(Paciente, outro_id)
        resultado.append(
            AmigoItem(
                id=reg.id,
                paciente_id=outro_id,
                username=outro.username if outro else None,
                streak=outro.streak if outro else 0,
                status=StatusAmizade(reg.status),
                sou_solicitante=(reg.pac_id == paciente_id),
                criado_em=reg.criado_em,
            )
        )
    return resultado


def remover_amizade(db: Session, amizade_id: int, paciente_id: int) -> None:
    """Desfaz uma amizade ou cancela uma solicitacao enviada."""
    amizade = db.get(Amizade, amizade_id)
    if not amizade:
        raise AmizadeNaoEncontrada("Amizade nao encontrada")

    if amizade.pac_id != paciente_id and amizade.amigo_id != paciente_id:
        raise OperacaoNaoPermitida("O paciente nao faz parte desta conexao de amizade")

    db.delete(amizade)
    db.commit()


def obter_ids_amigos_aceitos(db: Session, paciente_id: int) -> list[int]:
    """Retorna a lista de IDs de todos os amigos com status 'aceito'."""
    consulta = select(Amizade).where(
        Amizade.status == StatusAmizade.ACEITO,
        or_(Amizade.pac_id == paciente_id, Amizade.amigo_id == paciente_id),
    )
    amizades = db.scalars(consulta).all()

    ids: set[int] = set()
    for a in amizades:
        ids.add(a.amigo_id if a.pac_id == paciente_id else a.pac_id)
    return list(ids)
