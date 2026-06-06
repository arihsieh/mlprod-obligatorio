from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import BackgroundTasks, FastAPI, HTTPException

from mindful_news.api.schemas import (
    BatchJobResponse,
    BatchRequest,
    BatchResultItem,
    BatchStatusResponse,
    HeadlineItem,
    PredictRequest,
    PredictResponse,
)
from mindful_news.inference import NewsClassifier

_classifier: NewsClassifier | None = None
_jobs: dict[str, dict[str, Any]] = {}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _classifier
    _classifier = NewsClassifier()
    yield
    _classifier = None


app = FastAPI(
    title="Clasificador de Noticias UY",
    version="1.0",
    description="Clasifica titulares uruguayos por tema y carga emocional.",
    lifespan=lifespan,
)


def _get_classifier() -> NewsClassifier:
    if _classifier is None:
        raise HTTPException(status_code=503, detail="Modelos aún no cargados")
    return _classifier


def _batch_items(body: BatchRequest) -> list[HeadlineItem]:
    if body.items:
        return body.items
    return [HeadlineItem(titulo=t) for t in (body.titulares or [])]


def _run_batch(job_id: str, items: list[HeadlineItem]) -> None:
    _jobs[job_id]["status"] = "running"
    try:
        classifier = _get_classifier()
        pairs = [(item.titulo, item.seccion) for item in items]
        preds = classifier.predict_batch(pairs)
        _jobs[job_id]["results"] = [
            BatchResultItem(
                titulo=item.titulo,
                seccion=item.seccion,
                tema=p.tema,
                carga=p.carga,
                tema_confidence=p.tema_confidence,
                carga_confidence=p.carga_confidence,
            )
            for item, p in zip(items, preds)
        ]
        _jobs[job_id]["status"] = "completed"
    except Exception as exc:  # noqa: BLE001 — surface batch failure to client
        _jobs[job_id]["status"] = "failed"
        _jobs[job_id]["error"] = str(exc)


@app.get("/health")
def health() -> dict[str, str | bool]:
    ready = _classifier is not None
    return {"status": "ok" if ready else "starting", "models_loaded": ready}


@app.get("/ready")
def ready() -> dict[str, str]:
    if _classifier is None:
        raise HTTPException(status_code=503, detail="Modelos aún no cargados")
    return {"status": "ready"}


@app.post("/predict", response_model=PredictResponse)
def predict(body: PredictRequest) -> PredictResponse:
    start = time.perf_counter()
    pred = _get_classifier().predict(body.titulo, body.seccion)
    elapsed_ms = (time.perf_counter() - start) * 1000
    return PredictResponse(
        tema=pred.tema,
        carga=pred.carga,
        tema_confidence=pred.tema_confidence,
        carga_confidence=pred.carga_confidence,
        latencia_ms=round(elapsed_ms, 2),
    )


@app.post("/predict/batch", response_model=BatchJobResponse)
def predict_batch(body: BatchRequest, background_tasks: BackgroundTasks) -> BatchJobResponse:
    items = _batch_items(body)
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {"status": "pending", "results": None, "error": None}
    background_tasks.add_task(_run_batch, job_id, items)
    return BatchJobResponse(job_id=job_id)


@app.get("/predict/batch/{job_id}", response_model=BatchStatusResponse)
def get_batch_result(job_id: str) -> BatchStatusResponse:
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job no encontrado")
    return BatchStatusResponse(
        status=job["status"],
        results=job["results"],
        error=job.get("error"),
    )
