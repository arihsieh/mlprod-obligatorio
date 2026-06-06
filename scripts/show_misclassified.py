#!/usr/bin/env python3
"""Show misclassified headlines on the test split."""
import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv()

from mindful_news.training.evaluate import _default_model_dir, predict_test_errors


def _configure_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _safe_print(text: str) -> None:
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(
            sys.stdout.encoding or "utf-8", errors="replace"
        ))


def _print_samples(frame, task: str, limit: int, by_pair: int) -> None:
    errors = frame[~frame["correct"]]
    print(f"\n=== {task.upper()} ===")
    print(f"Test rows: {len(frame)} | Errors: {len(errors)} ({len(errors)/len(frame):.1%})")
    print(f"Model: {_default_model_dir(task)}")

    if errors.empty:
        print("No misclassifications.")
        return

    print("\nConfusion pairs (true -> pred):")
    pairs = (
        errors.groupby(["true_label", "pred_label"])
        .size()
        .reset_index(name="count")
        .sort_values("count", ascending=False)
    )
    for _, row in pairs.head(by_pair).iterrows():
        _safe_print(f"  {row['true_label']:14s} -> {row['pred_label']:14s}  ({row['count']})")

    print(f"\nSample misclassified headlines (top {limit}):")
    for _, row in errors.head(limit).iterrows():
        _safe_print(
            f"\n- [{row['true_label']} -> {row['pred_label']}] "
            f"conf={row['confidence']:.2f} | {row['medio']} | {row['split_date']}"
        )
        _safe_print(f"  {row['titulo']}")
        if row.get("url"):
            _safe_print(f"  {row['url']}")


def main() -> None:
    _configure_stdout()
    parser = argparse.ArgumentParser(description="Inspect misclassified test headlines.")
    parser.add_argument("--task", choices=("temas", "carga", "all"), default="all")
    parser.add_argument("--limit", type=int, default=15, help="Examples per task")
    parser.add_argument("--pairs", type=int, default=8, help="Top confusion pairs to show")
    parser.add_argument("--export", type=Path, help="Optional CSV export path")
    parser.add_argument("--splits-dir", type=Path, default=Path("data/splits"))
    args = parser.parse_args()

    tasks = ["temas", "carga"] if args.task == "all" else [args.task]
    exports = {}

    for task in tasks:
        frame = predict_test_errors(task, splits_dir=args.splits_dir)
        _print_samples(frame, task, args.limit, args.pairs)
        exports[task] = frame[~frame["correct"]]

    if args.export:
        args.export.parent.mkdir(parents=True, exist_ok=True)
        if args.task == "all":
            combined = []
            for task, frame in exports.items():
                part = frame.copy()
                part.insert(0, "task", task)
                combined.append(part)
            pd.concat(combined, ignore_index=True).to_csv(args.export, index=False)
        else:
            exports[args.task].to_csv(args.export, index=False)
        print(f"\nExported errors to {args.export}")


if __name__ == "__main__":
    main()
