from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Literal

import pandas as pd

from mindful_news.classify.labels import CARGAS, TEMAS
from mindful_news.config import ROOT, load_config
from mindful_news.db import connection, init_db
from mindful_news.training.labels import CARGA_TO_ID, TEMA_TO_ID, normalize_label
from mindful_news.training.preprocess import build_input_text, preprocess

Task = Literal["temas", "carga"]
SPLITS_DIR = ROOT / "data" / "splits"
EXPORTS_DIR = ROOT / "data" / "exports"

LOAD_COLUMNS = (
    "id",
    "titulo",
    "tema",
    "carga",
    "fecha",
    "scraped_at",
    "medio",
    "seccion",
    "url",
)


def _training_config() -> dict:
    return load_config().get("training", {})


def _label_map(task: Task) -> dict[str, int]:
    return TEMA_TO_ID if task == "temas" else CARGA_TO_ID


def _valid_labels(task: Task) -> set[str]:
    return set(TEMAS if task == "temas" else CARGAS)


def _coerce_datetime(value) -> datetime | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, datetime):
        return value
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.to_pydatetime()


def load_labeled_headlines(source: str | None = None) -> pd.DataFrame:
    """Load classified headlines from MySQL or a CSV export."""
    if source:
        path = Path(source)
        if not path.exists():
            raise FileNotFoundError(path)
        frame = pd.read_csv(path)
    else:
        init_db()
        query = (
            "SELECT id, titulo, tema, carga, fecha, scraped_at, medio, seccion, url "
            "FROM headlines WHERE classified_at IS NOT NULL ORDER BY id"
        )
        with connection() as conn:
            frame = pd.read_sql(query, conn)

    missing = set(LOAD_COLUMNS) - set(frame.columns)
    if missing:
        raise ValueError(f"Missing columns: {sorted(missing)}")

    frame = frame.copy()
    frame["titulo"] = frame["titulo"].astype(str).map(preprocess)
    if "seccion" not in frame.columns:
        frame["seccion"] = None
    frame["input_text"] = frame.apply(
        lambda row: build_input_text(row["titulo"], row.get("seccion")),
        axis=1,
    )
    frame["tema"] = frame["tema"].map(normalize_label)
    frame["carga"] = frame["carga"].map(normalize_label)
    frame["split_date"] = frame.apply(
        lambda row: _coerce_datetime(row["fecha"]) or _coerce_datetime(row["scraped_at"]),
        axis=1,
    )
    frame = frame[frame["split_date"].notna() & frame["tema"].notna() & frame["carga"].notna()]
    frame = frame.sort_values("split_date").reset_index(drop=True)
    return frame


def _temporal_cutoffs(dates: pd.Series, train_ratio: float, val_ratio: float) -> tuple[datetime, datetime]:
    if not 0 < train_ratio < 1:
        raise ValueError("train_ratio must be between 0 and 1")
    if not 0 < val_ratio < 1:
        raise ValueError("val_ratio must be between 0 and 1")
    if train_ratio + val_ratio >= 1:
        raise ValueError("train_ratio + val_ratio must be less than 1")

    ordered = dates.sort_values()
    train_end = ordered.iloc[int(len(ordered) * train_ratio) - 1]
    val_end = ordered.iloc[int(len(ordered) * (train_ratio + val_ratio)) - 1]
    return train_end.to_pydatetime(), val_end.to_pydatetime()


def make_temporal_splits(
    frame: pd.DataFrame,
    train_ratio: float | None = None,
    val_ratio: float | None = None,
) -> dict[str, pd.DataFrame]:
    cfg = _training_config().get("split", {})
    train_ratio = train_ratio if train_ratio is not None else float(cfg.get("train_ratio", 0.70))
    val_ratio = val_ratio if val_ratio is not None else float(cfg.get("val_ratio", 0.15))

    train_end, val_end = _temporal_cutoffs(frame["split_date"], train_ratio, val_ratio)
    train = frame[frame["split_date"] <= train_end].copy()
    val = frame[(frame["split_date"] > train_end) & (frame["split_date"] <= val_end)].copy()
    test = frame[frame["split_date"] > val_end].copy()
    return {"train": train, "val": val, "test": test}


def save_splits(splits: dict[str, pd.DataFrame], output_dir: Path | None = None) -> Path:
    output_dir = output_dir or SPLITS_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, frame in splits.items():
        path = output_dir / f"{name}.csv"
        frame.to_csv(path, index=False, quoting=csv.QUOTE_MINIMAL)
    return output_dir


def load_splits(output_dir: Path | None = None) -> dict[str, pd.DataFrame]:
    output_dir = output_dir or SPLITS_DIR
    splits = {}
    for name in ("train", "val", "test"):
        path = output_dir / f"{name}.csv"
        if not path.exists():
            raise FileNotFoundError(f"Missing split file: {path}")
        splits[name] = pd.read_csv(path)
    return splits


def _attach_input_text(frame: pd.DataFrame) -> pd.DataFrame:
    subset = frame.copy()
    if "seccion" not in subset.columns:
        subset["seccion"] = None
    if "input_text" not in subset.columns:
        subset["input_text"] = subset.apply(
            lambda row: build_input_text(row["titulo"], row.get("seccion")),
            axis=1,
        )
    return subset


def prepare_task_frame(frame: pd.DataFrame, task: Task) -> pd.DataFrame:
    label_col = "tema" if task == "temas" else "carga"
    valid = _valid_labels(task)
    label_map = _label_map(task)

    subset = frame[frame[label_col].isin(valid)].copy()
    subset["label"] = subset[label_col].map(label_map)
    subset = subset[subset["label"].notna()].reset_index(drop=True)
    subset = _attach_input_text(subset)
    return subset[
        ["id", "titulo", "seccion", "input_text", label_col, "label", "split_date", "medio", "url"]
    ]


def split_summary(splits: dict[str, pd.DataFrame], task: Task) -> dict[str, dict]:
    label_col = "tema" if task == "temas" else "carga"
    summary = {}
    for name, frame in splits.items():
        task_frame = prepare_task_frame(frame, task)
        counts = task_frame[label_col].value_counts().to_dict()
        summary[name] = {"rows": len(task_frame), "labels": counts}
    return summary


def latest_export_csv() -> Path | None:
    if not EXPORTS_DIR.exists():
        return None
    candidates = [
        path
        for path in EXPORTS_DIR.glob("headlines_*.csv")
        if path.name != "headlines_smoke.csv"
    ]
    if not candidates:
        candidates = list(EXPORTS_DIR.glob("headlines_*.csv"))
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)
