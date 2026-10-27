"""Regras de negocio do modulo de Privacidade e Conformidade LGPD (Item 51 - RF29, RNF06, RNF07).

Responsavel por:
- Evitar exposicao de dados de saude (peso, calorias, refeicoes, metas) a terceiros.
- Fornecer servicos de montagem de ranking e desafio utilizando estritamente DTOs publicos
  que contem unicamente nome, avatar, pontos e streak.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.paciente import Paciente
from app.schemas.privacidade import (
    DesafioPublicoItem,
    DesafioPublicoOut,
    RankingPublicoItem,
    RankingPublicoOut,
)
from app.services import amizades as amizades_servico
from app.services import gamificacao as gamificacao_servico


def obter_ranking_publico(
    db: Session,
    paciente_id: int,
    limite: int = 10,
    incluir_solicitante: bool = True,
) -> RankingPublicoOut:
    """Gera o ranking publico entre amigos expondo APENAS nome, avatar, pontos e streak (RF29).

    Garante que dados sensiveis (peso_kg, altura_cm, idade, meta_kcal, refeicoes, etc.)
    jamais sejam incluidos no retorno a terceiros.
    """
    gamificacao_servico._garantir_paciente(db, paciente_id)

    amigo_ids = amizades_servico.obter_ids_amigos_aceitos(db, paciente_id)
    participantes_ids = list(set([paciente_id] + amigo_ids)) if incluir_solicitante else amigo_ids

    inicio, fim = gamificacao_servico.janela_semanal()

    if not participantes_ids:
        return RankingPublicoOut(
            total_participantes=0,
            ranking=[],
        )

    totais_xp = gamificacao_servico.calcular_xp_semanal(db, participantes_ids, inicio, fim)

    pacientes_consulta = select(Paciente).where(Paciente.id.in_(participantes_ids))
    pacientes = {p.id: p for p in db.scalars(pacientes_consulta).all()}

    # Agrupa candidatos em DTOs publicos estritos
    candidatos = []
    for pid in participantes_ids:
        paciente = pacientes.get(pid)
        nome = (paciente.nome if paciente and paciente.nome else None) or (
            paciente.username if paciente else None
        )
        avatar = paciente.avatar if paciente else None
        pontos = totais_xp.get(pid, 0)
        streak = paciente.streak if paciente else 0

        candidatos.append(
            {
                "pid": pid,
                "item": RankingPublicoItem(
                    nome=nome,
                    avatar=avatar,
                    pontos=pontos,
                    streak=streak,
                ),
            }
        )

    # Ordenacao padrao de gamificacao: Maior pontuacao -> Maior streak -> Menor PID
    candidatos.sort(key=lambda c: (-c["item"].pontos, -c["item"].streak, c["pid"]))

    ranking_itens = [c["item"] for c in candidatos[:limite]]

    return RankingPublicoOut(
        total_participantes=len(candidatos),
        ranking=ranking_itens,
    )


def obter_desafio_publico(
    db: Session,
    desafio_id: int,
    titulo: str = "Desafio Semanal de Adesao ao Plano",
    participante_ids: list[int] | None = None,
) -> DesafioPublicoOut:
    """Gera o placar de desafio expondo APENAS nome, avatar, pontos e streak (RF05.2, RF29).

    Participantes competem sem ter seus dados clinicos (calorias consumidas, refeicoes
    individuais ou peso) revelados aos demais concorrentes.
    """
    ids = participante_ids or []
    if not ids:
        return DesafioPublicoOut(
            desafio_id=desafio_id,
            titulo=titulo,
            total_participantes=0,
            participantes=[],
        )

    pacientes_consulta = select(Paciente).where(Paciente.id.in_(ids))
    pacientes = {p.id: p for p in db.scalars(pacientes_consulta).all()}

    inicio, fim = gamificacao_servico.janela_semanal()
    totais_xp = gamificacao_servico.calcular_xp_semanal(db, ids, inicio, fim)

    participantes = []
    for pid in ids:
        paciente = pacientes.get(pid)
        nome = (paciente.nome if paciente and paciente.nome else None) or (
            paciente.username if paciente else None
        )
        avatar = paciente.avatar if paciente else None
        pontos = totais_xp.get(pid, 0)
        streak = paciente.streak if paciente else 0

        participantes.append(
            DesafioPublicoItem(
                nome=nome,
                avatar=avatar,
                pontos=pontos,
                streak=streak,
            )
        )

    # Ordenacao por pontuacao e streak
    participantes.sort(key=lambda p: (-p.pontos, -p.streak))

    return DesafioPublicoOut(
        desafio_id=desafio_id,
        titulo=titulo,
        total_participantes=len(participantes),
        participantes=participantes,
    )
