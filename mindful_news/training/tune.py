from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import optuna
import wandb
from optuna.trial import TrialState

from mindful_news.config import ROOT, load_config
from mindful_news.training.data import SPLITS_DIR
from mindful_news.training.promote import promote_best_trial
from mindful_news.training.train import MODELS_DIR, train_classifier

Task = Literal["temas", "carga"]
TUNING_DIR = ROOT / "data" / "tuning"
TRIALS_DIR = ROOT / "models" / "tuning"


def _phase_suffix(phase: int) -> str:
    return "" if phase == 1 else f"-phase{phase}"


def _phase_summary_suffix(phase: int) -> str:
    return "" if phase == 1 else f"_phase{phase}"


def _tuning_root() -> dict:
    return load_config().get("training", {}).get("tuning", {})


def _tuning_config(phase: int = 1) -> dict:
    root = _tuning_root()
    if phase == 1:
        return root
    phase_cfg = root.get(f"phase{phase}", {})
    merged = {**root, **{k: v for k, v in phase_cfg.items() if k not in ("temas", "carga", "anchors")}}
    merged["anchors"] = phase_cfg.get("anchors", [])
    return merged


def _search_space(task: Task, phase: int) -> dict:
    root = _tuning_root()
    if phase == 1:
        return root.get("search_space", {})
    phase_cfg = root.get(f"phase{phase}", {})
    return phase_cfg.get(task, phase_cfg.get("search_space", {}))


def _study_db_path(task: Task, phase: int = 1) -> Path:
    TUNING_DIR.mkdir(parents=True, exist_ok=True)
    return TUNING_DIR / f"{task}{_phase_suffix(phase)}.db"


def _study_summary_path(task: Task, phase: int = 1) -> Path:
    return TUNING_DIR / f"{task}{_phase_summary_suffix(phase)}_study.json"


def _best_params_path(task: Task, phase: int = 1) -> Path:
    return TUNING_DIR / f"{task}{_phase_summary_suffix(phase)}_best.json"


def _model_dir(task: Task, phase: int) -> Path:
    if phase == 1:
        return MODELS_DIR / task
    return MODELS_DIR / f"{task}-phase{phase}"


def _normalize_trial_params(params: dict) -> dict:
    mapping = {
        "batch_size": "per_device_train_batch_size",
        "num_epochs": "num_train_epochs",
    }
    return {mapping.get(key, key): value for key, value in params.items()}


def _suggest_hyperparameters(trial: optuna.Trial, task: Task, phase: int = 1) -> dict:
    search = _search_space(task, phase)
    return {
        "learning_rate": trial.suggest_float(
            "learning_rate",
            float(search.get("learning_rate_min", 1e-5)),
            float(search.get("learning_rate_max", 5e-5)),
            log=True,
        ),
        "per_device_train_batch_size": trial.suggest_categorical(
            "batch_size",
            search.get("batch_sizes", [16, 32, 64]),
        ),
        "num_train_epochs": trial.suggest_int(
            "num_epochs",
            int(search.get("epochs_min", 3)),
            int(search.get("epochs_max", 8)),
        ),
        "warmup_ratio": trial.suggest_float(
            "warmup_ratio",
            float(search.get("warmup_min", 0.05)),
            float(search.get("warmup_max", 0.2)),
        ),
        "weight_decay": trial.suggest_float(
            "weight_decay",
            float(search.get("weight_decay_min", 0.0)),
            float(search.get("weight_decay_max", 0.1)),
        ),
    }


def _anchor_trials(task: Task, phase: int) -> list[dict]:
    cfg = _tuning_config(phase)
    anchors: list[dict] = []
    for source_phase in cfg.get("anchors", []):
        path = _best_params_path(task, int(source_phase))
        if not path.exists():
            continue
        best = json.loads(path.read_text(encoding="utf-8"))
        if best.get("params"):
            anchors.append(best["params"])
    return anchors


def _completed_trials(study: optuna.Study) -> list[optuna.trial.FrozenTrial]:
    return [trial for trial in study.trials if trial.state == TrialState.COMPLETE]


def _save_study_summary(task: Task, study: optuna.Study, phase: int, target_trials: int) -> None:
    completed = _completed_trials(study)
    payload = {
        "task": task,
        "phase": phase,
        "study_name": study.study_name,
        "storage": str(_study_db_path(task, phase)),
        "direction": study.direction.name,
        "target_trials": target_trials,
        "completed_trials": len(completed),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "best_trial": study.best_trial.number if completed else None,
        "best_value": study.best_value if completed else None,
        "best_params": study.best_params if completed else None,
        "search_space": _search_space(task, phase),
        "trials": [
            {
                "number": trial.number,
                "value": trial.value,
                "params": trial.params,
                "state": trial.state.name,
            }
            for trial in study.trials
        ],
    }
    _study_summary_path(task, phase).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def create_or_load_study(task: Task, *, phase: int = 1, resume: bool = True) -> optuna.Study:
    cfg = _tuning_config(phase)
    db_path = _study_db_path(task, phase)
    if not resume and db_path.exists():
        db_path.unlink()
    storage = f"sqlite:///{db_path.as_posix()}"
    default_name = "{task}-mmbert" if phase == 1 else f"{{task}}-mmbert-phase{phase}"
    study_name = cfg.get("study_name_template", default_name).format(task=task)

    return optuna.create_study(
        study_name=study_name,
        storage=storage,
        load_if_exists=resume,
        direction="maximize",
    )


def _trial_dir(task: Task, trial_number: int, phase: int) -> Path:
    if phase == 1:
        return TRIALS_DIR / task / f"trial-{trial_number:03d}"
    return TRIALS_DIR / task / f"phase{phase}" / f"trial-{trial_number:03d}"


def _run_name(task: Task, trial_number: int, phase: int) -> str:
    if phase == 1:
        return f"{task}-trial-{trial_number:03d}"
    return f"{task}-p{phase}-trial-{trial_number:03d}"


def _wandb_group(task: Task, phase: int) -> str:
    cfg = _tuning_config(phase)
    if phase == 1:
        template = cfg.get("wandb_group_template", "{task}-optuna")
    else:
        template = cfg.get("wandb_group_template", f"{{task}}-optuna-v{phase}")
    return template.format(task=task)


def _final_run_name(task: Task, phase: int) -> str:
    if phase == 1:
        return f"{task}-final-best"
    return f"{task}-p{phase}-final-best"


def train_final_best(
    task: Task,
    *,
    splits_dir: Path | None = None,
    phase: int = 1,
) -> dict:
    return promote_best_trial(task, phase=phase, splits_dir=splits_dir)


def run_tuning(
    task: Task,
    *,
    phase: int = 1,
    n_trials: int | None = None,
    splits_dir: Path | None = None,
    resume: bool = True,
    final_train: bool = True,
) -> dict:
    cfg = _tuning_config(phase)
    wandb_cfg = load_config().get("training", {}).get("wandb", {})
    default_trials = 30 if phase in (2, 4) else 15
    n_trials = n_trials or int(cfg.get("n_trials", default_trials))
    splits_dir = splits_dir or SPLITS_DIR
    project = wandb_cfg.get("project", "mindful-news")
    group = _wandb_group(task, phase)

    study = create_or_load_study(task, phase=phase, resume=resume)
    completed = len(_completed_trials(study))
    remaining = max(0, n_trials - completed)

    if completed == 0:
        for params in _anchor_trials(task, phase):
            study.enqueue_trial(params)

    def objective(trial: optuna.Trial) -> float:
        hyper = _suggest_hyperparameters(trial, task, phase)
        trial_dir = _trial_dir(task, trial.number, phase)
        run_name = _run_name(task, trial.number, phase)

        wandb.init(
            project=project,
            group=group,
            name=run_name,
            job_type="optuna-trial",
            tags=[f"phase-{phase}", task],
            reinit="finish_previous",
            config={
                "task": task,
                "phase": phase,
                "trial_number": trial.number,
                **hyper,
            },
        )
        try:
            result = train_classifier(
                task,
                splits_dir=splits_dir,
                output_dir=trial_dir,
                hyper_overrides=hyper,
                skip_test=True,
                tuning=True,
                run_name=run_name,
            )
            val_f1 = float(result["val_metrics"]["eval_f1_macro"])
            wandb.log(
                {
                    "val/f1_macro": val_f1,
                    "val/accuracy": float(result["val_metrics"]["eval_accuracy"]),
                    "val/loss": float(result["val_metrics"]["eval_loss"]),
                    "train/loss": float(result["train_loss"]),
                    "train/rows": result["train_rows"],
                    "val/rows": result["val_rows"],
                }
            )
            wandb.summary["best_val_f1_macro"] = val_f1
            return val_f1
        except Exception as exc:
            wandb.summary["error"] = str(exc)
            raise
        finally:
            wandb.finish()

    if remaining:
        study.optimize(objective, n_trials=remaining, gc_after_trial=True)

    _save_study_summary(task, study, phase, n_trials)

    if not _completed_trials(study):
        raise RuntimeError(f"No completed trials for task={task} phase={phase}")

    best_params = _normalize_trial_params(study.best_params)
    best_payload = {
        "task": task,
        "phase": phase,
        "trial_number": study.best_trial.number,
        "val_f1_macro": study.best_value,
        "params": study.best_params,
        "hyper_overrides": best_params,
        "search_space": _search_space(task, phase),
    }
    _best_params_path(task, phase).write_text(json.dumps(best_payload, indent=2), encoding="utf-8")

    final_result = None
    if final_train:
        final_result = promote_best_trial(
            task,
            phase=phase,
            splits_dir=splits_dir,
            trial_number=study.best_trial.number,
        )
        best_payload["final_val_metrics"] = final_result["val_metrics"]
        best_payload["final_test_metrics"] = final_result["test_metrics"]
        best_payload["final_model_dir"] = str(_model_dir(task, phase))
        best_payload["promotion"] = "checkpoint_copy"
        _best_params_path(task, phase).write_text(json.dumps(best_payload, indent=2), encoding="utf-8")

    return {
        "task": task,
        "phase": phase,
        "completed_trials": len(_completed_trials(study)),
        "target_trials": n_trials,
        "best_trial": study.best_trial.number,
        "best_val_f1_macro": study.best_value,
        "best_params": study.best_params,
        "study_summary": str(_study_summary_path(task, phase)),
        "best_params_file": str(_best_params_path(task, phase)),
        "final_result": final_result,
    }


def copy_best_trial_model(task: Task, phase: int = 1) -> Path:
    result = promote_best_trial(task, phase=phase)
    return Path(result.get("output_dir", str(_model_dir(task, phase))))
