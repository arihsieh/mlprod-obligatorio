#!/usr/bin/env python3
"""Fine-tune mmBERT-small for carga emocional (3 classes)."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv()

from mindful_news.training.train import train_classifier


def main() -> None:
    parser = argparse.ArgumentParser(description="Train carga classifier.")
    parser.add_argument("--splits-dir", type=Path, default=Path("data/splits"))
    parser.add_argument("--output-dir", type=Path, default=Path("models/carga"))
    parser.add_argument("--max-steps", type=int, help="Debug: limit training steps")
    parser.add_argument("--dry-run", action="store_true", help="Validate data + model load only")
    parser.add_argument("--no-wandb", action="store_true", help="Disable Weights & Biases logging")
    args = parser.parse_args()

    import os
    if args.no_wandb:
        os.environ["WANDB_DISABLED"] = "true"

    result = train_classifier(
        "carga",
        splits_dir=args.splits_dir,
        output_dir=args.output_dir,
        max_steps=args.max_steps,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
