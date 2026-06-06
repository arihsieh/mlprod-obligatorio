#!/usr/bin/env python3
"""Optuna hyperparameter search with Weights & Biases logging (resumable)."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv()

from mindful_news.training.tune import Task, run_tuning, train_final_best


def main() -> None:
    parser = argparse.ArgumentParser(description="Tune mmBERT hyperparameters with Optuna + W&B.")
    parser.add_argument(
        "--task",
        choices=("temas", "carga", "all"),
        default="all",
        help="Which classifier to tune",
    )
    parser.add_argument("--trials", type=int, help="Target completed trials per task")
    parser.add_argument(
        "--phase",
        type=int,
        choices=(1, 2, 3, 4),
        default=1,
        help="Phase 1: broad (15). Phase 2: refined (30). Phase 3: corrected (15). Phase 4: temas+seccion (30).",
    )
    parser.add_argument("--splits-dir", type=Path, default=Path("data/splits"))
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Create a fresh Optuna study instead of continuing the sqlite study",
    )
    parser.add_argument(
        "--skip-final-train",
        action="store_true",
        help="Only run Optuna trials; do not retrain best config on test set",
    )
    parser.add_argument(
        "--final-only",
        action="store_true",
        help="Promote best trial checkpoint + evaluate test (no retrain from scratch)",
    )
    args = parser.parse_args()

    if args.final_only:
        tasks: list[Task] = ["temas", "carga"] if args.task == "all" else [args.task]
        for task in tasks:
            print(f"\n=== Promote best trial {task} phase {args.phase} ===")
            result = train_final_best(task, splits_dir=args.splits_dir, phase=args.phase)
            print(json.dumps(result, indent=2, default=str))
        return

    tasks: list[Task] = ["temas", "carga"] if args.task == "all" else [args.task]
    results = {}

    for task in tasks:
        print(f"\n=== Tuning {task} (phase {args.phase}) ===")
        results[task] = run_tuning(
            task,
            phase=args.phase,
            n_trials=args.trials,
            splits_dir=args.splits_dir,
            resume=not args.no_resume,
            final_train=not args.skip_final_train,
        )
        print(json.dumps(results[task], indent=2, default=str))

    print("\nDone. Resume later with the same command if interrupted.")


if __name__ == "__main__":
    main()
