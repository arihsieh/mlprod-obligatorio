from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class PredictRequest(BaseModel):
    titulo: str = Field(..., min_length=1, description="Titular de la noticia")
    seccion: str | None = Field(
        None,
        description="Sección del medio (opcional; mejora clasificación de temas)",
    )


class PredictResponse(BaseModel):
    tema: str
    carga: str
    tema_confidence: float
    carga_confidence: float
    latencia_ms: float


class HeadlineItem(BaseModel):
    titulo: str = Field(..., min_length=1)
    seccion: str | None = None


class BatchRequest(BaseModel):
    titulares: list[str] | None = Field(
        None,
        description="Lista simple de titulares (sin sección)",
    )
    items: list[HeadlineItem] | None = Field(
        None,
        description="Titulares con sección opcional (recomendado)",
    )

    @model_validator(mode="after")
    def _require_payload(self) -> BatchRequest:
        if not self.titulares and not self.items:
            raise ValueError("Enviá 'titulares' o 'items'")
        return self


class BatchJobResponse(BaseModel):
    job_id: str


class BatchResultItem(BaseModel):
    titulo: str
    seccion: str | None
    tema: str
    carga: str
    tema_confidence: float
    carga_confidence: float


class BatchStatusResponse(BaseModel):
    status: str
    results: list[BatchResultItem] | None = None
    error: str | None = None
