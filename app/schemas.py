from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import JobStatus


class TaskId(str, Enum):
    """Sitios soportados.

    Al tiparlo como Enum, un task_id invalido lo rechaza Pydantic con 422 y mensaje
    explicito, en lugar de reventar en la capa de servicio con un 500.
    """

    saucedemo = "saucedemo"
    practicesoftware = "practicesoftware"


class TaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: TaskId = Field(description="Identificador del sitio a automatizar")
    lookup_key: str | None = Field(
        default=None,
        max_length=255,
        description="Filtro opcional por nombre de producto (coincidencia parcial)",
    )

    @field_validator("lookup_key")
    @classmethod
    def _normalize_lookup_key(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        return trimmed or None


class TaskAccepted(BaseModel):
    job_id: UUID


class ProductOut(BaseModel):
    """Forma exacta que exige el challenge para cada producto."""

    name: str
    price: str
    description: str
    image_url: str


class TaskStatusOut(BaseModel):
    """Respuesta de GET /tasks/{job_id}.

    Los campos opcionales se omiten cuando son None (ver response_model_exclude_none),
    de modo que un job completado devuelve {status, data} y uno fallido {status, error_message}.
    """

    status: JobStatus
    data: list[ProductOut] | None = None
    error_message: str | None = None


class HealthOut(BaseModel):
    status: str
    database: str
    queue: str
    time: datetime
