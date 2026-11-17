"""Modelos ORM.

Todo modelo novo deve ser importado aqui: o Alembic usa `Base.metadata` para
comparar o codigo com o banco, e so enxerga o que foi importado.
"""

from app.db.base import Base
from app.models.alerta_desvio import AlertaDesvioPlano, DirecaoDesvio, RegraAlertaDesvio
from app.models.alimento_personalizado import AlimentoPersonalizado
from app.models.alimento_taco import AlimentoTaco
from app.models.amizade import Amizade, StatusAmizade
from app.models.auditoria import AcaoAuditoria, Auditoria, EntidadeAuditada
from app.models.conquista import ConquistaPaciente
from app.models.consentimento import Consentimento
from app.models.desafio import Desafio, ParticipanteDesafio, StatusParticipante, TipoDesafio
from app.models.historico_xp import HistoricoXP
from app.models.lembrete_refeicao import DispositivoPush, LembreteRefeicao
from app.models.notificacao_desafio import NotificacaoDesafio
from app.models.paciente import Genero, NivelAtividade, Paciente
from app.models.plano_alimentar import AlimentoRefeicaoPlano, PlanoAlimentar, RefeicaoPlano
from app.models.refeicao import ItemRefeicao, Refeicao, TipoRefeicao
from app.models.usuario import Nutricionista, Perfil, Usuario
from app.models.vinculo import CodigoVinculacao, StatusCodigoVinculacao, StatusVinculo, Vinculo

__all__ = [
    "AcaoAuditoria",
    "AlertaDesvioPlano",
    "AlimentoPersonalizado",
    "AlimentoRefeicaoPlano",
    "AlimentoTaco",
    "Amizade",
    "Auditoria",
    "Base",
    "CodigoVinculacao",
    "ConquistaPaciente",
    "Consentimento",
    "Desafio",
    "DirecaoDesvio",
    "DispositivoPush",
    "EntidadeAuditada",
    "Genero",
    "HistoricoXP",
    "ItemRefeicao",
    "LembreteRefeicao",
    "NivelAtividade",
    "NotificacaoDesafio",
    "Nutricionista",
    "Paciente",
    "ParticipanteDesafio",
    "Perfil",
    "PlanoAlimentar",
    "Refeicao",
    "RefeicaoPlano",
    "RegraAlertaDesvio",
    "StatusAmizade",
    "StatusCodigoVinculacao",
    "StatusParticipante",
    "StatusVinculo",
    "TipoRefeicao",
    "TipoDesafio",
    "Usuario",
    "Vinculo",
]
