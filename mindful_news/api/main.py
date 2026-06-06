from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, Response

from mindful_news.api.schemas import (
    BatchJobResponse,
    BatchRequest,
    BatchResultItem,
    BatchStatusResponse,
    HeadlineItem,
    PredictRequest,
    PredictResponse,
)
from mindful_news.db import fetch_headlines, init_db
from mindful_news.inference import NewsClassifier

_classifier: NewsClassifier | None = None
_jobs: dict[str, dict[str, Any]] = {}

_PORTAL_HTML = Path(__file__).resolve().parents[2] / "portal" / "index.html"

# Teal-wave SVG served as favicon (matches the in-page logo exactly)
_FAVICON_SVG = """\
<svg viewBox="0 0 680 680" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="lg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#2dd4bf"/>
      <stop offset="100%" stop-color="#059669"/>
    </linearGradient>
    <clipPath id="cp"><circle cx="340" cy="340" r="268"/></clipPath>
  </defs>
  <circle cx="340" cy="340" r="270" fill="none" stroke="#14b8a6" stroke-width="6"/>
  <g clip-path="url(#cp)" fill="none" stroke="url(#lg)" stroke-linecap="round" stroke-linejoin="round">
    <path stroke-width="5.5" d="M70 345 Q180 290,340 320 Q500 350,610 295"/>
    <path stroke-width="5.5" d="M70 375 Q170 315,340 348 Q510 380,610 322"/>
    <path stroke-width="5.5" d="M82 408 Q175 345,340 378 Q510 410,605 355"/>
    <path stroke-width="5.5" d="M105 442 Q185 378,340 410 Q505 442,598 390"/>
    <path stroke-width="5.5" d="M135 478 Q200 415,340 445 Q498 476,580 425"/>
    <path stroke-width="5.5" d="M175 515 Q222 455,340 480 Q488 510,555 462"/>
    <path stroke-width="5.5" d="M222 552 Q252 498,340 518 Q468 545,520 502"/>
    <path stroke-width="5.5" d="M278 585 Q295 548,340 558 Q430 576,475 548"/>
    <path stroke-width="5.5" d="M338 608 Q342 598,355 595 Q390 590,428 588"/>
  </g>
</svg>"""


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _classifier
    try:
        init_db()
    except Exception:  # noqa: BLE001 — DB may not be available in all envs
        pass
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


# ── Portal ────────────────────────────────────────────────────────────────────


@app.get("/favicon.svg", include_in_schema=False)
def favicon() -> Response:
    return Response(content=_FAVICON_SVG, media_type="image/svg+xml")


@app.get("/portal", response_class=HTMLResponse, include_in_schema=False)
def portal() -> HTMLResponse:
    if not _PORTAL_HTML.exists():
        raise HTTPException(status_code=404, detail="portal/index.html not found")
    return HTMLResponse(_PORTAL_HTML.read_text(encoding="utf-8"))


@app.get("/api/headlines")
def get_headlines(
    t: list[str] = Query(default=[]),
    c: list[str] = Query(default=[]),
    limit: int = Query(default=60, ge=1, le=200),
) -> list[dict]:
    rows = fetch_headlines(temas=t or None, cargas=c or None, limit=limit)
    return jsonable_encoder(rows)
