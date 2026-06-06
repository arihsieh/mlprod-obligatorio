#!/usr/bin/env python3
"""Create temporal train/val/test splits from classified headlines."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mindful_news.training.data import (
    latest_export_csv,
    load_labeled_headlines,
    make_temporal_splits,
    save_splits,
    split_summary,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Temporal split for ML training.")
    parser.add_argument(
        "--source",
        help="CSV export path (default: latest data/exports/headlines_*.csv or MySQL)",
    )
    parser.add_argument("--train-ratio", type=float, help="Override config training.train_ratio")
    parser.add_argument("--val-ratio", type=float, help="Override config training.val_ratio")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/splits"),
        help="Directory for train.csv, val.csv, test.csv",
    )
    args = parser.parse_args()

    source = args.source
    if source is None:
        latest = latest_export_csv()
        if latest is not None:
            source = str(latest)
            print(f"Using latest export: {latest}")

    frame = load_labeled_headlines(source)
    splits = make_temporal_splits(frame, train_ratio=args.train_ratio, val_ratio=args.val_ratio)
    output_dir = save_splits(splits, args.output_dir)

    summary = {
        "source": source or "mysql",
        "total_rows": len(frame),
        "splits": {
            name: {
                "rows": len(split),
                "date_min": split["split_date"].min(),
                "date_max": split["split_date"].max(),
            }
            for name, split in splits.items()
        },
        "temas": split_summary(splits, "temas"),
        "carga": split_summary(splits, "carga"),
    }
    summary_path = output_dir / "summary.json"

    def _default(value):
        if hasattr(value, "isoformat"):
            return value.isoformat(sep=" ")
        raise TypeError(type(value))

    summary_path.write_text(json.dumps(summary, indent=2, default=_default), encoding="utf-8")

    print(f"Saved splits to {output_dir}")
    for name, split in splits.items():
        print(f"  {name:5s}: {len(split):5d} rows")
    print(f"Summary: {summary_path}")


if __name__ == "__main__":
    main()
