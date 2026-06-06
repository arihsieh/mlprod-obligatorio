from __future__ import annotations

import json
from pathlib import Path

from typing import Literal

import numpy as np
import pandas as pd
import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from mindful_news.config import ROOT, load_config
from mindful_news.training.data import SPLITS_DIR, load_splits, prepare_task_frame
from mindful_news.training.labels import ID_TO_CARGA, ID_TO_TEMA
from mindful_news.training.preprocess import build_input_text, preprocess

Task = Literal["temas", "carga"]

_BEST_PATHS: dict[Task, list[Path]] = {
    "temas": [
        ROOT / "data" / "tuning" / "temas_phase4_best.json",
        ROOT / "data" / "tuning" / "temas_best.json",
    ],
    "carga": [
        ROOT / "data" / "tuning" / "carga_phase3_best.json",
        ROOT / "data" / "tuning" / "carga_best.json",
    ],
}


def _default_model_dir(task: Task) -> Path:
    for path in _BEST_PATHS[task]:
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            return Path(payload["final_model_dir"])
    return ROOT / "models" / task


def _inference_texts(frame: pd.DataFrame, model_dir: Path) -> list[str]:
    metrics_path = model_dir / "metrics.json"
    mode = "seccion_titulo"
    if metrics_path.exists():
        mode = json.loads(metrics_path.read_text(encoding="utf-8")).get("input_text_mode", mode)

    if mode == "titulo":
        return frame["titulo"].astype(str).map(preprocess).tolist()

    if "input_text" in frame.columns:
        return frame["input_text"].astype(str).tolist()

    return [
        build_input_text(row["titulo"], row.get("seccion"))
        for _, row in frame.iterrows()
    ]


def predict_test_errors(
    task: Task,
    *,
    model_dir: Path | None = None,
    splits_dir: Path | None = None,
    batch_size: int = 64,
) -> pd.DataFrame:
    model_dir = model_dir or _default_model_dir(task)
    splits_dir = splits_dir or SPLITS_DIR
    label_col = "tema" if task == "temas" else "carga"
    id_to_label = ID_TO_TEMA if task == "temas" else ID_TO_CARGA

    frame = prepare_task_frame(load_splits(splits_dir)["test"], task)
    tokenizer = AutoTokenizer.from_pretrained(model_dir)
    model = AutoModelForSequenceClassification.from_pretrained(model_dir)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device)
    model.eval()

    texts = _inference_texts(frame, model_dir)
    pred_labels: list[int] = []
    confidences: list[float] = []

    for start in range(0, len(texts), batch_size):
        batch_texts = texts[start : start + batch_size]
        encodings = tokenizer(
            batch_texts,
            truncation=True,
            padding=True,
            max_length=int(load_config().get("training", {}).get("max_length", 128)),
            return_tensors="pt",
        )
        encodings = {key: value.to(device) for key, value in encodings.items()}
        with torch.no_grad():
            logits = model(**encodings).logits
            probs = torch.softmax(logits, dim=-1)
            scores, preds = torch.max(probs, dim=-1)
        pred_labels.extend(preds.cpu().tolist())
        confidences.extend(scores.cpu().tolist())

    result = frame.copy()
    result["true_label"] = result[label_col]
    result["pred_label"] = [id_to_label[i] for i in pred_labels]
    result["confidence"] = confidences
    result["correct"] = result["true_label"] == result["pred_label"]
    return result.sort_values(["correct", "confidence"], ascending=[True, False])
