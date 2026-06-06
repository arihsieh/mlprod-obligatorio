#!/usr/bin/env python3
"""Generate analysis notebooks for Mindful News."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NB = ROOT / "notebooks"
NB.mkdir(exist_ok=True)


def nb(cells: list[dict]) -> dict:
    return {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {"name": "python", "pygments_lexer": "ipython3"},
        },
        "cells": cells,
    }


def md(source: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": [source]}


def code(source: str) -> dict:
    return {
        "cell_type": "code",
        "metadata": {},
        "outputs": [],
        "execution_count": None,
        "source": [source],
    }


def write(name: str, cells: list[dict]) -> None:
    path = NB / name
    path.write_text(json.dumps(nb(cells), ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Wrote {path}")


SETUP = """import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
from IPython.display import display

ROOT = Path.cwd()
if not (ROOT / "config.yml").exists():
    ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

import importlib
import mindful_news.training.data as _data
import mindful_news.training.preprocess as _preprocess

importlib.reload(_preprocess)
importlib.reload(_data)

sns.set_theme(style="whitegrid", palette="muted")
plt.rcParams["figure.figsize"] = (10, 5)
plt.rcParams["figure.dpi"] = 110
"""

# --- 1. EDA ---
write(
    "01_eda_datos_scrapeados.ipynb",
    [
        md(
            "# Análisis exploratorio — datos scrapeados\n\n"
            "Exploración del dataset de titulares uruguayos: volumen, fuentes, "
            "etiquetas GPT y distribución temporal.\n\n"
            "**Fuente:** export CSV más reciente en `data/exports/`."
        ),
        code(
            SETUP
            + """
from mindful_news.training.data import latest_export_csv, load_labeled_headlines, make_temporal_splits

export_path = latest_export_csv()
print("Export:", export_path)
df = load_labeled_headlines(str(export_path) if export_path else None)
df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
df["scraped_at"] = pd.to_datetime(df["scraped_at"], errors="coerce")
df["titulo_len"] = df["titulo"].str.len()
df.head(3)
"""
        ),
        code(
            """summary = {
    "filas": len(df),
    "medios": df["medio"].nunique(),
    "temas": df["tema"].nunique(),
    "cargas": df["carga"].nunique(),
    "desde": df["split_date"].min(),
    "hasta": df["split_date"].max(),
}
pd.Series(summary)
"""
        ),
        code(
            """fig, axes = plt.subplots(1, 2, figsize=(12, 4))

medio_counts = df["medio"].value_counts()
axes[0].barh(medio_counts.index, medio_counts.values, color=sns.color_palette()[0])
axes[0].set_title("Titulares por medio")
axes[0].set_xlabel("Cantidad")

tema_counts = df["tema"].value_counts()
sns.barplot(x=tema_counts.values, y=tema_counts.index, ax=axes[1], orient="h")
axes[1].set_title("Distribución de temas (GPT)")
axes[1].set_xlabel("Cantidad")
plt.tight_layout()
plt.show()
"""
        ),
        code(
            """order = ["baja", "media", "alta"]
fig, axes = plt.subplots(1, 2, figsize=(12, 4))

sns.countplot(data=df, x="carga", order=order, ax=axes[0])
axes[0].set_title("Distribución de carga emocional")

ct = pd.crosstab(df["tema"], df["carga"]).loc[:, order]
sns.heatmap(ct, annot=True, fmt="d", cmap="Blues", ax=axes[1])
axes[1].set_title("Tema × carga")
plt.tight_layout()
plt.show()
"""
        ),
        code(
            """daily = df.set_index("split_date").resample("D").size()
weekly_medio = df.groupby([pd.Grouper(key="split_date", freq="W"), "medio"]).size().unstack(fill_value=0)

fig, axes = plt.subplots(2, 1, figsize=(12, 7), sharex=False)
daily.plot(ax=axes[0], color="#4C72B0")
axes[0].set_title("Titulares por día")
axes[0].set_ylabel("Cantidad")

weekly_medio.plot(kind="area", stacked=True, ax=axes[1], alpha=0.85)
axes[1].set_title("Volumen semanal por medio")
axes[1].set_ylabel("Cantidad")
plt.tight_layout()
plt.show()
"""
        ),
        code(
            """fig, axes = plt.subplots(1, 2, figsize=(12, 4))

sns.histplot(df["titulo_len"], bins=30, kde=True, ax=axes[0])
med = df["titulo_len"].median()
axes[0].axvline(med, ls="--", c="red", label=f"mediana={med:.0f}")
axes[0].set_title("Longitud de titulares (chars)")
axes[0].legend()

tema_medio = pd.crosstab(df["medio"], df["tema"], normalize="index") * 100
sns.heatmap(tema_medio, cmap="YlOrRd", ax=axes[1])
axes[1].set_title("% tema por medio (filas normalizadas)")
plt.tight_layout()
plt.show()

print("Longitud min/med/max:", df["titulo_len"].min(), med, df["titulo_len"].max())
"""
        ),
        code(
            """splits = make_temporal_splits(df)
split_sizes = pd.Series({k: len(v) for k, v in splits.items()})
display(split_sizes)

print("Rango temporal por split:")
for name, part in splits.items():
    start = part["split_date"].min()
    end = part["split_date"].max()
    print(f"  {name:5s}: {start} -> {end} ({len(part)} filas)")
"""
        ),
        code(
            """for label_col in ["tema", "carga"]:
    print(f"\\n=== Ejemplos por {label_col} ===")
    for label, group in df.groupby(label_col):
        sample = group.sample(min(2, len(group)), random_state=42)
        print(f"\\n-- {label} --")
        for _, row in sample.iterrows():
            print(f"  [{row['medio']}] {row['titulo'][:100]}")
"""
        ),
    ],
)

# --- 2. Training results ---
write(
    "02_resultados_training.ipynb",
    [
        md(
            "# Resultados de training — Optuna + mmBERT\n\n"
            "Comparación de las 3 fases de tuning para **temas** y **carga**: "
            "trials Optuna, mejor modelo por fase y métricas en test.\n\n"
            "Archivos en `data/tuning/*_study.json` y `*_best.json`."
        ),
        code(
            SETUP
            + """
import json
from matplotlib.ticker import MaxNLocator

TUNING = ROOT / "data" / "tuning"
TASKS = ["temas", "carga"]
PHASES = [1, 2, 3]


def study_path(task: str, phase: int) -> Path:
    suffix = "" if phase == 1 else f"_phase{phase}"
    return TUNING / f"{task}{suffix}_study.json"


def best_path(task: str, phase: int) -> Path:
    suffix = "" if phase == 1 else f"_phase{phase}"
    return TUNING / f"{task}{suffix}_best.json"


def load_studies() -> pd.DataFrame:
    rows = []
    for task in TASKS:
        for phase in PHASES:
            path = study_path(task, phase)
            if not path.exists():
                continue
            payload = json.loads(path.read_text(encoding="utf-8"))
            for trial in payload.get("trials", []):
                if trial.get("state") != "COMPLETE" or trial.get("value") is None:
                    continue
                row = {"task": task, "phase": phase, "trial": trial["number"], "val_f1": trial["value"]}
                row.update(trial.get("params", {}))
                rows.append(row)
    return pd.DataFrame(rows)


def load_bests() -> pd.DataFrame:
    rows = []
    for task in TASKS:
        for phase in PHASES:
            path = best_path(task, phase)
            if not path.exists():
                continue
            best = json.loads(path.read_text(encoding="utf-8"))
            test = best.get("final_test_metrics", {})
            rows.append(
                {
                    "task": task,
                    "phase": phase,
                    "trial": best.get("trial_number"),
                    "val_f1": best.get("val_f1_macro"),
                    "test_f1": test.get("test_f1_macro"),
                    "test_acc": test.get("test_accuracy"),
                    "model_dir": best.get("final_model_dir"),
                    **best.get("params", {}),
                }
            )
    return pd.DataFrame(rows)


trials = load_studies()
bests = load_bests()
print(f"Trials cargados: {len(trials)} | Mejores por fase: {len(bests)}")
bests
"""
        ),
        code(
            """fig, axes = plt.subplots(1, 2, figsize=(14, 5), sharey=True)

for ax, task in zip(axes, TASKS):
    subset = trials[trials["task"] == task]
    sns.boxplot(data=subset, x="phase", y="val_f1", ax=ax)
    sns.stripplot(data=subset, x="phase", y="val_f1", color="black", alpha=0.45, size=4, ax=ax)
    ax.set_title(f"Val F1 macro — {task}")
    ax.set_xlabel("Fase Optuna")
    ax.set_ylabel("F1 macro (val)")
    ax.xaxis.set_major_locator(MaxNLocator(integer=True))

plt.tight_layout()
plt.show()
"""
        ),
        code(
            """fig, axes = plt.subplots(1, 2, figsize=(14, 5))

for ax, task in zip(axes, TASKS):
    subset = bests[bests["task"] == task].sort_values("phase")
    x = subset["phase"].astype(str)
    width = 0.35
    idx = range(len(subset))
    ax.bar([i - width / 2 for i in idx], subset["val_f1"], width, label="val F1")
    ax.bar([i + width / 2 for i in idx], subset["test_f1"], width, label="test F1")
    ax.set_xticks(list(idx), [f"Fase {p}" for p in subset["phase"]])
    ax.set_ylim(0.65, 0.85)
    ax.set_title(f"Mejor trial por fase — {task}")
    ax.set_ylabel("F1 macro")
    ax.legend()

plt.tight_layout()
plt.show()

# Mejor en test por tarea
for task in TASKS:
    best_row = bests[bests["task"] == task].sort_values("test_f1", ascending=False).iloc[0]
    print(
        f"{task}: fase {int(best_row['phase'])} | "
        f"test F1={best_row['test_f1']:.3f} | val F1={best_row['val_f1']:.3f} | "
        f"trial {int(best_row['trial'])}"
    )
"""
        ),
        code(
            """fig, axes = plt.subplots(2, 2, figsize=(13, 9))

for ax, task in zip(axes[0], TASKS):
    subset = trials[trials["task"] == task]
    sns.scatterplot(
        data=subset,
        x="learning_rate",
        y="val_f1",
        hue="phase",
        style="batch_size",
        ax=ax,
        alpha=0.85,
    )
    ax.set_xscale("log")
    ax.set_title(f"Learning rate vs val F1 — {task}")

for ax, task in zip(axes[1], TASKS):
    subset = trials[trials["task"] == task]
    sns.scatterplot(
        data=subset,
        x="num_epochs",
        y="val_f1",
        hue="phase",
        size="batch_size",
        ax=ax,
        alpha=0.85,
    )
    ax.set_title(f"Épocas vs val F1 — {task}")

plt.tight_layout()
plt.show()
"""
        ),
        code(
            """# Métricas por clase del modelo final (metrics.json)
from sklearn.metrics import classification_report

rows = []
for task in TASKS:
    best = bests[bests["task"] == task].sort_values("test_f1", ascending=False).iloc[0]
    metrics_path = Path(best["model_dir"]) / "metrics.json"
    if not metrics_path.exists():
        print("Missing", metrics_path)
        continue
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    report = metrics.get("classification_report", {})
    for label, scores in report.items():
        if label in ("accuracy", "macro avg", "weighted avg"):
            continue
        rows.append(
            {
                "task": task,
                "label": label,
                "f1": scores["f1-score"],
                "precision": scores["precision"],
                "recall": scores["recall"],
                "support": scores["support"],
            }
        )

per_class = pd.DataFrame(rows)
per_class.sort_values(["task", "f1"])
"""
        ),
        code(
            """fig, axes = plt.subplots(1, 2, figsize=(14, 6), sharex=False)

for ax, task in zip(axes, TASKS):
    subset = per_class[per_class["task"] == task].sort_values("f1")
    sns.barplot(data=subset, x="f1", y="label", ax=ax, orient="h")
    ax.set_xlim(0, 1)
    ax.set_title(f"F1 por clase (test) — {task}")
    ax.set_xlabel("F1")

plt.tight_layout()
plt.show()
"""
        ),
        code(
            """# Gap val-test del mejor modelo por fase (overfitting proxy)
bests["gap"] = bests["val_f1"] - bests["test_f1"]

fig, ax = plt.subplots(figsize=(8, 4))
sns.barplot(data=bests, x="task", y="gap", hue="phase", ax=ax)
ax.axhline(0, ls="--", c="gray")
ax.set_title("Brecha val − test F1 (mayor = más overfit a val)")
ax.set_ylabel("Δ F1")
plt.tight_layout()
plt.show()

bests[["task", "phase", "trial", "val_f1", "test_f1", "gap", "learning_rate", "batch_size", "num_epochs"]]
"""
        ),
    ],
)

# --- 3. Sanity check ---
write(
    "03_sanity_check_modelos.ipynb",
    [
        md(
            "# Sanity check — errores en test set\n\n"
            "Análisis cualitativo y cuantitativo de clasificaciones incorrectas "
            "con los mejores modelos (`models/temas`, `models/carga-phase3`).\n\n"
            "Equivalente a `python scripts/show_misclassified.py`."
        ),
        code(
            SETUP
            + """
import importlib
import mindful_news.training.evaluate as _evaluate
importlib.reload(_evaluate)

from sklearn.metrics import ConfusionMatrixDisplay, confusion_matrix

from mindful_news.training.evaluate import _default_model_dir, predict_test_errors

TASKS = ["temas", "carga"]
results = {}
for task in TASKS:
    frame = predict_test_errors(task)
    results[task] = frame
    errors = (~frame["correct"]).sum()
    print(f"{task}: {errors}/{len(frame)} errores ({errors/len(frame):.1%}) | model={_default_model_dir(task)}")
"""
        ),
        code(
            """fig, axes = plt.subplots(1, 2, figsize=(16, 6))

for ax, task in zip(axes, TASKS):
    frame = results[task]
    labels = sorted(frame["true_label"].unique())
    cm = confusion_matrix(frame["true_label"], frame["pred_label"], labels=labels)
    disp = ConfusionMatrixDisplay(confusion_matrix=cm, display_labels=labels)
    disp.plot(ax=ax, cmap="Blues", xticks_rotation=45, colorbar=False)
    ax.set_title(f"Matriz de confusión — {task}")

plt.tight_layout()
plt.show()
"""
        ),
        code(
            """def top_confusion_pairs(frame: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    errors = frame[~frame["correct"]]
    pairs = (
        errors.groupby(["true_label", "pred_label"])
        .size()
        .reset_index(name="count")
        .sort_values("count", ascending=False)
    )
    return pairs.head(n)


for task in TASKS:
    print(f"\\n=== {task.upper()} — pares más frecuentes ===")
    display(top_confusion_pairs(results[task]))
"""
        ),
        code(
            """fig, axes = plt.subplots(1, 2, figsize=(14, 4))

for ax, task in zip(axes, TASKS):
    frame = results[task]
    sns.histplot(
        data=frame,
        x="confidence",
        hue="correct",
        bins=25,
        stat="density",
        common_norm=False,
        ax=ax,
    )
    ax.set_title(f"Confianza del modelo — {task}")
    ax.set_xlabel("Probabilidad máxima (softmax)")

plt.tight_layout()
plt.show()
"""
        ),
        code(
            """def show_examples(frame: pd.DataFrame, n: int = 8) -> pd.DataFrame:
    errors = frame[~frame["correct"]].head(n)
    cols = ["true_label", "pred_label", "confidence", "medio", "split_date", "titulo", "url"]
    return errors[cols]


for task in TASKS:
    print(f"\\n=== {task.upper()} — ejemplos mal clasificados (alta confianza) ===")
    display(show_examples(results[task]))
"""
        ),
        code(
            """# Errores con baja confianza (el modelo duda)
LOW_CONF = 0.55

for task in TASKS:
    frame = results[task]
    borderline = frame[(~frame["correct"]) & (frame["confidence"] < LOW_CONF)].sort_values("confidence")
    print(f"\\n{task}: {len(borderline)} errores con confianza < {LOW_CONF}")
    if not borderline.empty:
        display(borderline[["true_label", "pred_label", "confidence", "titulo"]].head(8))
"""
        ),
        code(
            """# Tasa de error por etiqueta verdadera
rows = []
for task, frame in results.items():
    for label, group in frame.groupby("true_label"):
        err_rate = (~group["correct"]).mean()
        rows.append({"task": task, "label": label, "error_rate": err_rate, "support": len(group)})

error_by_label = pd.DataFrame(rows)
fig, axes = plt.subplots(1, 2, figsize=(14, 5))

for ax, task in zip(axes, TASKS):
    subset = error_by_label[error_by_label["task"] == task].sort_values("error_rate", ascending=False)
    sns.barplot(data=subset, x="error_rate", y="label", ax=ax, orient="h")
    ax.set_xlim(0, 1)
    ax.set_title(f"Tasa de error por clase — {task}")
    ax.set_xlabel("Proporción mal clasificada")

plt.tight_layout()
plt.show()
"""
        ),
        code(
            """# Export opcional (descomentar)
# out = ROOT / "data" / "exports" / "test_errors_notebook.csv"
# combined = []
# for task, frame in results.items():
#     part = frame[~frame["correct"]].copy()
#     part.insert(0, "task", task)
#     combined.append(part)
# pd.concat(combined, ignore_index=True).to_csv(out, index=False)
# print("Exportado:", out)
"""
        ),
        md(
            "## Input del modelo: sección + título\n\n"
            "Desde la **fase 4 de tuning (temas)** el clasificador ya no ve solo el titular. "
            "El texto que entra a mmBERT se arma así:\n\n"
            "```\n"
            "{seccion} | {titulo}\n"
            "```\n\n"
            "Ejemplo real:\n\n"
            "> `Noticias, Policiales | Dos veces en dos semanas: balearon casa en Jardines del Hipódromo`\n\n"
            "**Por qué:** la sección del medio (cuando existe) ayuda a desambiguar temas "
            "(`deporte`→deportes, `Noticias, Policiales`→seguridad). "
            "En el dataset, **99.98%** de titulares tienen `seccion`; si falta, se usa solo el título.\n\n"
            "**Config** (`config.yml` → `training.input`):\n"
            "- `include_seccion: true`\n"
            "- `separator: \" | \"`\n"
            "- `template: \"{seccion}{sep}{titulo}\"`\n\n"
            "**Tuning fase 4:** 30 trials Optuna solo para **temas**, con anchor del ganador "
            "de fase 1. Modelo final en `models/temas-phase4/`. "
            "W&B group: `temas-optuna-v4`.\n\n"
            "**Compatibilidad:** modelos viejos (solo título) guardan "
            "`input_text_mode: titulo` en `metrics.json`; la inferencia respeta eso. "
            "Los nuevos guardan `seccion_titulo`.\n\n"
            "> Si ves `ImportError` tras editar código, **reiniciá el kernel** y corré desde la celda 1."
        ),
        code(
            """import importlib
import mindful_news.training.data as data_mod
import mindful_news.training.preprocess as preprocess_mod

importlib.reload(preprocess_mod)
importlib.reload(data_mod)

sample = data_mod.prepare_task_frame(data_mod.load_splits()["test"], "temas").head(5)
sample[["seccion", "titulo", "input_text", "tema"]]
"""
        ),
        code(
            """# Comparar formato de input (si existe modelo fase 4)
import json

phase4_best = ROOT / "data" / "tuning" / "temas_phase4_best.json"
phase1_best = ROOT / "data" / "tuning" / "temas_best.json"

for label, path in [("Fase 1 (solo título)", phase1_best), ("Fase 4 (sección+título)", phase4_best)]:
    if not path.exists():
        print(f"{label}: aún no disponible ({path.name})")
        continue
    best = json.loads(path.read_text(encoding="utf-8"))
    test = best.get("final_test_metrics", {})
    print(
        f"{label} | trial {best.get('trial_number')} | "
        f"val F1={best.get('val_f1_macro', 0):.3f} | "
        f"test F1={test.get('test_f1_macro', 0):.3f}"
    )
    print(f"  model_dir: {best.get('final_model_dir')}")
"""
        ),
    ],
)

print("Done.")
