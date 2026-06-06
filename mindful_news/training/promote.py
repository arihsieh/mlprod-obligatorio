from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Literal

from mindful_news.config import ROOT
from mindful_news.training.data import SPLITS_DIR
from mindful_news.training.train import MODELS_DIR, evaluate_saved_model, train_classifier

Task = Literal["temas", "carga"]
TRIALS_DIR = ROOT / "models" / "tuning"
TUNING_DIR = ROOT / "data" / "tuning"


def _phase_suffix(phase: int) -> str:
    return "" if phase == 1 else f"-phase{phase}"


def _phase_summary_suffix(phase: int) -> str:
    return "" if phase == 1 else f"_phase{phase}"


def _best_params_path(task: Task, phase: int = 1) -> Path:
    return TUNING_DIR / f"{task}{_phase_summary_suffix(phase)}_best.json"


def _model_dir(task: Task, phase: int) -> Path:
    if phase == 1:
        return MODELS_DIR / task
    return MODELS_DIR / f"{task}-phase{phase}"


def _trial_dir(task: Task, trial_number: int, phase: int) -> Path:
    if phase == 1:
        return TRIALS_DIR / task / f"trial-{trial_number:03d}"
    return TRIALS_DIR / task / f"phase{phase}" / f"trial-{trial_number:03d}"


def _final_run_name(task: Task, phase: int) -> str:
    if phase == 1:
        return f"{task}-final-best"
    return f"{task}-p{phase}-final-best"


def _normalize_trial_params(params: dict) -> dict:
    mapping = {
        "batch_size": "per_device_train_batch_size",
        "num_epochs": "num_train_epochs",
    }
    return {mapping.get(key, key): value for key, value in params.items()}


def trial_model_dir(trial_dir: Path) -> Path | None:
    """Return a loadable model directory for a completed trial."""
    if (trial_dir / "config.json").exists():
        return trial_dir
    checkpoints = sorted(trial_dir.glob("checkpoint-*"), key=lambda path: path.stat().st_mtime)
    for path in reversed(checkpoints):
        if (path / "config.json").exists():
            return path
    return None


def _copy_model_tree(source: Path, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination)


def _ensure_trial_checkpoint(
    task: Task,
    phase: int,
    trial_number: int,
    hyper_overrides: dict,
    *,
    splits_dir: Path | None = None,
) -> Path:
    trial_dir = _trial_dir(task, trial_number, phase)
    existing = trial_model_dir(trial_dir)
    if existing is not None:
        return existing

    print(f"No checkpoint for trial {trial_number}; re-running once to save best epoch.")
    train_classifier(
        task,
        splits_dir=splits_dir or SPLITS_DIR,
        output_dir=trial_dir,
        hyper_overrides=hyper_overrides,
        skip_test=True,
        tuning=True,
    )
    saved = trial_model_dir(trial_dir)
    if saved is None:
        raise FileNotFoundError(f"Trial {trial_number} finished without a saved model in {trial_dir}")
    return saved


def promote_best_trial(
    task: Task,
    *,
    phase: int = 1,
    splits_dir: Path | None = None,
    trial_number: int | None = None,
) -> dict:
    """Copy the best Optuna trial checkpoint to the final model dir and evaluate val+test."""
    splits_dir = splits_dir or SPLITS_DIR
    best_path = _best_params_path(task, phase)
    if not best_path.exists():
        raise FileNotFoundError(
            f"Missing {best_path}. Run tuning first: "
            f"python scripts/tune_models.py --task {task} --phase {phase}"
        )

    best = json.loads(best_path.read_text(encoding="utf-8"))
    trial_number = trial_number if trial_number is not None else int(best["trial_number"])
    hyper = best.get("hyper_overrides") or _normalize_trial_params(best["params"])
    final_dir = _model_dir(task, phase)
    trial_dir = _trial_dir(task, trial_number, phase)

    source = _ensure_trial_checkpoint(
        task,
        phase,
        trial_number,
        hyper,
        splits_dir=splits_dir,
    )
    _copy_model_tree(source, final_dir)

    result = evaluate_saved_model(
        task,
        final_dir,
        splits_dir=splits_dir,
        run_name=_final_run_name(task, phase),
    )
    result["output_dir"] = str(final_dir)

    best["trial_number"] = trial_number
    best["trial_dir"] = str(trial_dir)
    best["promoted_from"] = str(source)
    best["final_val_metrics"] = result["val_metrics"]
    best["final_test_metrics"] = result["test_metrics"]
    best["final_model_dir"] = str(final_dir)
    best["promotion"] = "checkpoint_copy"
    best_path.write_text(json.dumps(best, indent=2), encoding="utf-8")
    return result
