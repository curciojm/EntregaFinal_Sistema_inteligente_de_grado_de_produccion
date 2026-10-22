from enum import Enum
from operator import add
from typing import Annotated, Optional, List, Dict, Literal
from langgraph.graph import MessagesState
from pydantic import Field, BaseModel


# Agent

class AgentState(MessagesState):

    """Hereda 'messages' y suma los campos propios del workflow."""

    job_id: Optional[str]

    approval: Optional[bool]

    feedback_humano: Optional[str]

    revision_humana: bool

    next_agent: Optional[str]

    contribuciones: Annotated[List[Dict[str, str]], add]

    pasos: int

    task_completed: bool

    revisiones: int

class ApprovalRequest(BaseModel):
    decision: Literal["approve", "reject"]
    feedback: str = ""

class DecisionSupervisor(BaseModel):

    next: Literal["profesor", "evaluador", "FINISH"] = Field(
        description=(
            "Próximo agente a invocar, o FINISH si la tarea ya está completa."
        )
    )

    razon: str = Field(
        description="Breve justificación de la decisión."
    )

class ResultadoConcepto(BaseModel):

    contenido: str = Field(
        description="Contenido relevante recuperado del documento."
    )


class ResultadoFuente(BaseModel):

    fuente: str = Field(
        description="Fuente bibliográfica del documento."
    )

    pagina: int = Field(
        description="Número entero de página donde aparece la información."
    )

class ResultadoEvaluacion(BaseModel):

    evaluacion: Literal["Mal", "Incompleta", "Bien", "Muy bien"] = Field(
        description="Evaluación del conocimiento del usuario sobre el concepto."
    )

    mejora: str = Field(
        description=(
            "Cómo puede mejorar su respuesta. "
            "Si es Muy bien, indicar que no necesita mejoras."
        )
    )

# Redis
class TaskRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)

class TaskStatus(str, Enum):
    pending = "pending"
    processing = "processing"
    waiting_approval = "waiting_approval"
    completed = "completed"
    failed = "failed"

class TaskResponse(BaseModel):
    job_id: str
    status: TaskStatus

# Errors
class LLMErrorType(str, Enum):
    """Tipos de errores utilizados para clasificar las excepciones."""

    RATE_LIMIT = "rate_limit"
    UNKNOWN = "unknown"
    KEY = "key"


class LLMError(Exception):
    """Permite clasificar el error y proporcionar un mensaje legible al usuario."""

    def __init__(self, error_type: str, message: str):
        self.error_type = error_type
        self.message = message
        super().__init__(message)