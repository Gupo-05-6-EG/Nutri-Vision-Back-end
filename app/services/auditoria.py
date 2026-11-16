"""Registro da trilha de auditoria (Task 5.3, RNF08)."""

from typing import Any

from sqlalchemy.orm import Session

from app.models.auditoria import AcaoAuditoria, Auditoria, EntidadeAuditada


def registrar_auditoria(
    db: Session,
    *,
    paciente_id: int,
    autor_id: int | None,
    entidade: EntidadeAuditada,
    registro_id: int,
    antes: dict[str, Any] | None,
    depois: dict[str, Any],
) -> Auditoria:
    """Adiciona a linha de auditoria a sessao, **sem commit**.

    Quem chama faz o commit junto com a alteracao auditada: as duas coisas
    entram na mesma transacao, entao nao existe alteracao sem auditoria (nem
    auditoria de uma alteracao que nao aconteceu).
    """
    auditoria = Auditoria(
        paciente_id=paciente_id,
        autor_id=autor_id,
        entidade=entidade.value,
        registro_id=registro_id,
        acao=(AcaoAuditoria.ATUALIZACAO if antes is not None else AcaoAuditoria.CRIACAO).value,
        antes=antes,
        depois=depois,
    )
    db.add(auditoria)
    return auditoria
