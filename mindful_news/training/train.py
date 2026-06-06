from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Literal

import numpy as np
import torch
import wandb
from datasets import Dataset
from sklearn.metrics import accuracy_score, classification_report, f1_score
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    EarlyStoppingCallback,
    Trainer,
    TrainerCallback,
    TrainingArguments,
)

from mindful_news.classify.labels import CARGAS, TEMAS
from mindful_news.config import ROOT, load_config
from mindful_news.training.data import load_splits, prepare_task_frame
from mindful_news.training.labels import ID_TO_CARGA, ID_TO_TEMA
from mindful_news.training.preprocess import input_text_mode
Task = Literal["temas", "carga"]
MODELS_DIR = ROOT / "models"


def _training_config() -> dict:
    return load_config().get("training", {})


def _resolve_device() -> torch.device:
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def _log_device() -> str:
    device = _resolve_device()
    if device.type == "cpu" and "+cpu" in torch.__version__:
        print(
            "WARNING: PyTorch is CPU-only (%s). Install the CUDA build, e.g.\n"
            "  pip install torch==2.12.0+cu126 --index-url https://download.pytorch.org/whl/cu126"
            % torch.__version__
        )
    elif device.type == "cuda":
        print(f"Using GPU: {torch.cuda.get_device_name(0)} (torch {torch.__version__})")
    else:
        print(f"Using CPU (torch {torch.__version__})")
    return str(device)


def _task_labels(task: Task) -> tuple[str, ...]:
    return TEMAS if task == "temas" else CARGAS


def _id_to_label(task: Task) -> dict[int, str]:
    return ID_TO_TEMA if task == "temas" else ID_TO_CARGA


def download_model(model_id: str | None = None, cache_dir: Path | None = None) -> tuple:
    cfg = _training_config()
    model_id = model_id or cfg.get("model_id", "jhu-clsp/mmBERT-small")
    cache_dir = cache_dir or ROOT / cfg.get("cache_dir", "models/cache")

    tokenizer = AutoTokenizer.from_pretrained(model_id, cache_dir=cache_dir)
    model = AutoModelForSequenceClassification.from_pretrained(
        model_id,
        num_labels=len(_task_labels("temas")),
        cache_dir=cache_dir,
    )
    return tokenizer, model, model_id


def _frame_to_dataset(frame, tokenizer, max_length: int) -> Dataset:
    texts = frame["input_text"].astype(str).tolist()
    labels = frame["label"].astype(int).tolist()

    encodings = tokenizer(
        texts,
        truncation=True,
        padding=False,
        max_length=max_length,
    )
    encodings["labels"] = labels
    return Dataset.from_dict(encodings)


def _compute_metrics_builder(id_to_label: dict[int, str]):
    label_names = [id_to_label[index] for index in sorted(id_to_label)]

    def compute_metrics(eval_pred):
        logits, labels = eval_pred
        predictions = np.argmax(logits, axis=-1)
        return {
            "accuracy": accuracy_score(labels, predictions),
            "f1_macro": f1_score(labels, predictions, average="macro", zero_division=0),
            "f1_weighted": f1_score(labels, predictions, average="weighted", zero_division=0),
        }

    compute_metrics.label_names = label_names
    return compute_metrics


class WandbEpochCallback(TrainerCallback):
    """Log validation metrics to W&B once per epoch with an explicit epoch axis."""

    def on_evaluate(self, args, state, control, metrics=None, **kwargs):
        if not metrics or wandb.run is None:
            return
        payload = {"train/epoch": state.epoch}
        for key, value in metrics.items():
            if key.startswith("eval_"):
                payload[f"val/{key.removeprefix('eval_')}"] = value
        wandb.log(payload, step=int(state.epoch))


def _build_training_args(
    task: Task,
    output_dir: Path,
    num_labels: int,
    overrides: dict | None = None,
    hyper_overrides: dict | None = None,
    *,
    tuning: bool = False,
    eval_only: bool = False,
) -> TrainingArguments:
    cfg = _training_config()
    hyper = {**cfg.get("hyperparameters", {}), **(hyper_overrides or {})}
    wandb_cfg = cfg.get("wandb", {})
    overrides = overrides or {}

    project = wandb_cfg.get("project", "mindful-news")
    run_name = overrides.pop("run_name", wandb_cfg.get("run_name") or f"mmbert-{task}")

    if wandb_cfg.get("enabled", True) and os.getenv("WANDB_DISABLED") != "true":
        os.environ.setdefault("WANDB_PROJECT", project)
        report_to = "wandb"
    else:
        report_to = "none"

    args = {
        "output_dir": str(output_dir),
        "num_train_epochs": float(hyper.get("num_train_epochs", 5)),
        "per_device_train_batch_size": int(hyper.get("per_device_train_batch_size", 32)),
        "per_device_eval_batch_size": int(hyper.get("per_device_eval_batch_size", 64)),
        "learning_rate": float(hyper.get("learning_rate", 2e-5)),
        "warmup_ratio": float(hyper.get("warmup_ratio", 0.1)),
        "weight_decay": float(hyper.get("weight_decay", 0.01)),
        "eval_strategy": "epoch",
        "logging_strategy": "steps",
        "logging_steps": int(hyper.get("logging_steps", 17)),
        "logging_first_step": bool(hyper.get("logging_first_step", True)),
        "load_best_model_at_end": not eval_only,
        "metric_for_best_model": "f1_macro",
        "greater_is_better": True,
        "save_total_limit": 1,
        "save_strategy": "no" if eval_only else "epoch",
        "fp16": bool(hyper.get("fp16", True)) and torch.cuda.is_available(),
        "report_to": report_to,
        "run_name": run_name,
        "seed": int(hyper.get("seed", 42)),
        "dataloader_num_workers": 0,
    }
    args.update(overrides)
    return TrainingArguments(**args)


def train_classifier(
    task: Task,
    *,
    splits_dir: Path | None = None,
    output_dir: Path | None = None,
    max_length: int | None = None,
    max_steps: int | None = None,
    dry_run: bool = False,
    hyper_overrides: dict | None = None,
    skip_test: bool = False,
    tuning: bool | None = None,
    run_name: str | None = None,
    report_to_wandb: bool | None = None,
) -> dict:
    cfg = _training_config()
    model_id = cfg.get("model_id", "jhu-clsp/mmBERT-small")
    cache_dir = ROOT / cfg.get("cache_dir", "models/cache")
    max_length = max_length or int(cfg.get("max_length", 128))
    output_dir = output_dir or MODELS_DIR / task

    device = _log_device()

    splits = load_splits(splits_dir)
    train_frame = prepare_task_frame(splits["train"], task)
    val_frame = prepare_task_frame(splits["val"], task)
    test_frame = prepare_task_frame(splits["test"], task)

    if train_frame.empty or val_frame.empty:
        raise ValueError(f"Train/val splits are empty for task={task}")

    label_names = _task_labels(task)
    id_to_label = _id_to_label(task)
    num_labels = len(label_names)

    tokenizer = AutoTokenizer.from_pretrained(model_id, cache_dir=cache_dir)
    model = AutoModelForSequenceClassification.from_pretrained(
        model_id,
        num_labels=num_labels,
        id2label=id_to_label,
        label2id={label: index for index, label in enumerate(label_names)},
        cache_dir=cache_dir,
    )

    train_dataset = _frame_to_dataset(train_frame, tokenizer, max_length)
    val_dataset = _frame_to_dataset(val_frame, tokenizer, max_length)
    test_dataset = _frame_to_dataset(test_frame, tokenizer, max_length)

    training_overrides = {}
    if max_steps is not None:
        training_overrides["max_steps"] = max_steps
        training_overrides["num_train_epochs"] = 1
    if run_name:
        training_overrides["run_name"] = run_name
    if report_to_wandb is False:
        training_overrides["report_to"] = "none"

    if tuning is None:
        tuning = skip_test

    training_args = _build_training_args(
        task,
        output_dir,
        num_labels,
        training_overrides,
        hyper_overrides,
        tuning=tuning,
    )
    compute_metrics = _compute_metrics_builder(id_to_label)

    callbacks = [EarlyStoppingCallback(early_stopping_patience=2)]
    if report_to_wandb is not False and os.getenv("WANDB_DISABLED") != "true":
        callbacks.insert(0, WandbEpochCallback())

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=val_dataset,
        processing_class=tokenizer,
        compute_metrics=compute_metrics,
        callbacks=callbacks,
    )

    if dry_run:
        return {
            "task": task,
            "model_id": model_id,
            "train_rows": len(train_frame),
            "val_rows": len(val_frame),
            "test_rows": len(test_frame),
            "output_dir": str(output_dir),
        }

    train_result = trainer.train()
    val_metrics = trainer.evaluate()
    test_metrics = {}
    report = {}

    output_dir.mkdir(parents=True, exist_ok=True)
    trainer.save_model(str(output_dir))
    tokenizer.save_pretrained(str(output_dir))
    if tuning:
        for checkpoint in output_dir.glob("checkpoint-*"):
            shutil.rmtree(checkpoint)

    if not skip_test:
        test_metrics = trainer.evaluate(test_dataset, metric_key_prefix="test")

        predictions = trainer.predict(test_dataset)
        y_true = predictions.label_ids
        y_pred = np.argmax(predictions.predictions, axis=-1)
        report = classification_report(
            y_true,
            y_pred,
            target_names=[id_to_label[i] for i in range(num_labels)],
            zero_division=0,
            output_dict=True,
        )

    metrics_path = output_dir / "metrics.json"
    payload = {
        "task": task,
        "model_id": model_id,
        "input_text_mode": input_text_mode(),
        "train_rows": len(train_frame),
        "val_rows": len(val_frame),
        "test_rows": len(test_frame),
        "train_loss": train_result.training_loss,
        "val_metrics": val_metrics,
        "test_metrics": test_metrics,
        "classification_report": report,
    }
    if not skip_test:
        metrics_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    return payload


def evaluate_saved_model(
    task: Task,
    model_dir: Path,
    *,
    splits_dir: Path | None = None,
    max_length: int | None = None,
    run_name: str | None = None,
    report_to_wandb: bool | None = None,
) -> dict:
    """Evaluate a saved checkpoint on val+test without retraining."""
    cfg = _training_config()
    model_id = cfg.get("model_id", "jhu-clsp/mmBERT-small")
    max_length = max_length or int(cfg.get("max_length", 128))
    splits_dir = splits_dir or ROOT / "data" / "splits"
    model_dir = Path(model_dir)

    _log_device()
    splits = load_splits(splits_dir)
    train_frame = prepare_task_frame(splits["train"], task)
    val_frame = prepare_task_frame(splits["val"], task)
    test_frame = prepare_task_frame(splits["test"], task)

    id_to_label = _id_to_label(task)
    num_labels = len(_task_labels(task))

    tokenizer = AutoTokenizer.from_pretrained(model_dir)
    model = AutoModelForSequenceClassification.from_pretrained(model_dir)
    val_dataset = _frame_to_dataset(val_frame, tokenizer, max_length)
    test_dataset = _frame_to_dataset(test_frame, tokenizer, max_length)
    compute_metrics = _compute_metrics_builder(id_to_label)

    training_overrides: dict = {"do_train": False}
    if run_name:
        training_overrides["run_name"] = run_name
    if report_to_wandb is False or os.getenv("WANDB_DISABLED") == "true":
        training_overrides["report_to"] = "none"

    training_args = _build_training_args(
        task,
        model_dir,
        num_labels,
        training_overrides,
        eval_only=True,
    )

    callbacks = []
    if report_to_wandb is not False and os.getenv("WANDB_DISABLED") != "true":
        callbacks.append(WandbEpochCallback())

    trainer = Trainer(
        model=model,
        args=training_args,
        eval_dataset=val_dataset,
        processing_class=tokenizer,
        compute_metrics=compute_metrics,
        callbacks=callbacks,
    )

    val_metrics = trainer.evaluate()
    test_metrics = trainer.evaluate(test_dataset, metric_key_prefix="test")
    predictions = trainer.predict(test_dataset)
    y_true = predictions.label_ids
    y_pred = np.argmax(predictions.predictions, axis=-1)
    report = classification_report(
        y_true,
        y_pred,
        target_names=[id_to_label[i] for i in range(num_labels)],
        zero_division=0,
        output_dict=True,
    )

    payload = {
        "task": task,
        "model_id": model_id,
        "input_text_mode": input_text_mode(),
        "train_rows": len(train_frame),
        "val_rows": len(val_frame),
        "test_rows": len(test_frame),
        "val_metrics": val_metrics,
        "test_metrics": test_metrics,
        "classification_report": report,
        "promoted_from_checkpoint": True,
    }
    (model_dir / "metrics.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload
