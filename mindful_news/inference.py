from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from mindful_news.config import ROOT, load_config
from mindful_news.training.labels import ID_TO_CARGA, ID_TO_TEMA
from mindful_news.training.preprocess import build_input_text, preprocess

Task = Literal["temas", "carga"]


@dataclass(frozen=True)
class LabelPrediction:
    label: str
    confidence: float


@dataclass(frozen=True)
class HeadlinePrediction:
    tema: str
    carga: str
    tema_confidence: float
    carga_confidence: float
    input_text_temas: str


def _resolve_model_dir(task: Task, override: Path | None = None) -> Path:
    if override is not None:
        return override

    env_key = "MODEL_TEMAS_PATH" if task == "temas" else "MODEL_CARGA_PATH"
    env_path = os.getenv(env_key)
    if env_path:
        return Path(env_path)

    from mindful_news.training.evaluate import _default_model_dir

    return _default_model_dir(task)


def _input_text_mode(model_dir: Path) -> str:
    metrics_path = model_dir / "metrics.json"
    if metrics_path.exists():
        payload = json.loads(metrics_path.read_text(encoding="utf-8"))
        return payload.get("input_text_mode", "seccion_titulo")
    return "titulo"


class TaskClassifier:
    """Single-task mmBERT classifier loaded once at startup."""

    def __init__(self, task: Task, model_dir: Path | None = None) -> None:
        self.task = task
        self.model_dir = _resolve_model_dir(task, model_dir)
        self.id_to_label = ID_TO_TEMA if task == "temas" else ID_TO_CARGA
        self.input_mode = _input_text_mode(self.model_dir)
        self.max_length = int(load_config().get("training", {}).get("max_length", 128))

        self.tokenizer = AutoTokenizer.from_pretrained(self.model_dir)
        self.model = AutoModelForSequenceClassification.from_pretrained(self.model_dir)
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model.to(self.device)
        self.model.eval()

    def _build_text(self, titulo: str, seccion: str | None) -> str:
        if self.input_mode == "titulo":
            return preprocess(titulo)
        return build_input_text(titulo, seccion)

    def predict_texts(self, texts: list[str]) -> list[LabelPrediction]:
        if not texts:
            return []

        predictions: list[LabelPrediction] = []
        batch_size = 32
        for start in range(0, len(texts), batch_size):
            batch_texts = texts[start : start + batch_size]
            encodings = self.tokenizer(
                batch_texts,
                truncation=True,
                padding=True,
                max_length=self.max_length,
                return_tensors="pt",
            )
            encodings = {key: value.to(self.device) for key, value in encodings.items()}
            with torch.no_grad():
                logits = self.model(**encodings).logits
                probs = torch.softmax(logits, dim=-1)
                scores, preds = torch.max(probs, dim=-1)

            for pred_id, score in zip(preds.cpu().tolist(), scores.cpu().tolist()):
                predictions.append(
                    LabelPrediction(label=self.id_to_label[pred_id], confidence=float(score))
                )
        return predictions

    def predict_one(self, titulo: str, seccion: str | None = None) -> LabelPrediction:
        return self.predict_texts([self._build_text(titulo, seccion)])[0]


class NewsClassifier:
    """Production predictor: tema + carga for one headline."""

    def __init__(
        self,
        temas_dir: Path | None = None,
        carga_dir: Path | None = None,
    ) -> None:
        self.temas = TaskClassifier("temas", temas_dir)
        self.carga = TaskClassifier("carga", carga_dir)

    def predict(self, titulo: str, seccion: str | None = None) -> HeadlinePrediction:
        input_text_temas = self.temas._build_text(titulo, seccion)
        tema_pred = self.temas.predict_texts([input_text_temas])[0]
        carga_pred = self.carga.predict_one(titulo, seccion=None)
        return HeadlinePrediction(
            tema=tema_pred.label,
            carga=carga_pred.label,
            tema_confidence=tema_pred.confidence,
            carga_confidence=carga_pred.confidence,
            input_text_temas=input_text_temas,
        )

    def predict_batch(
        self,
        items: list[tuple[str, str | None]],
    ) -> list[HeadlinePrediction]:
        tema_texts = [self.temas._build_text(t, s) for t, s in items]
        carga_texts = [self.carga._build_text(t, None) for t, _ in items]
        tema_preds = self.temas.predict_texts(tema_texts)
        carga_preds = self.carga.predict_texts(carga_texts)
        return [
            HeadlinePrediction(
                tema=tp.label,
                carga=cp.label,
                tema_confidence=tp.confidence,
                carga_confidence=cp.confidence,
                input_text_temas=text,
            )
            for tp, cp, text in zip(tema_preds, carga_preds, tema_texts)
        ]
