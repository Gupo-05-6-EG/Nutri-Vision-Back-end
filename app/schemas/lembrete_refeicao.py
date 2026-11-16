"""Schemas dos lembretes de refeicao e do token de push (Task 2.8, RF26)."""

from datetime import time

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.refeicao import TipoRefeicao


class LembreteIn(BaseModel):
    """Horario de lembrete de um tipo de refeicao."""

    tipo: TipoRefeicao
    horario: time = Field(description="Hora local (America/Sao_Paulo), ex.: 08:30")
    ativo: bool = True

    @field_validator("horario")
    @classmethod
    def _so_hora_e_minuto(cls, valor: time) -> time:
        # O job roda a cada poucos minutos: segundos e fuso nao tem significado aqui.
        return valor.replace(second=0, microsecond=0, tzinfo=None)


class LembretesIn(BaseModel):
    """Lista de lembretes a salvar; so os tipos enviados sao alterados."""

    lembretes: list[LembreteIn] = Field(min_length=1, max_length=len(TipoRefeicao))

    @model_validator(mode="after")
    def _tipos_sem_repeticao(self) -> "LembretesIn":
        tipos = [lembrete.tipo for lembrete in self.lembretes]
        if len(tipos) != len(set(tipos)):
            raise ValueError("Cada tipo de refeicao so pode aparecer uma vez")
        return self


class LembreteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    tipo: TipoRefeicao
    horario: time
    ativo: bool


class LembretesOut(BaseModel):
    paciente_id: int
    lembretes: list[LembreteOut]


class DispositivoPushIn(BaseModel):
    """Token FCM do aparelho, gerado pelo app."""

    token: str = Field(min_length=1, max_length=512)
