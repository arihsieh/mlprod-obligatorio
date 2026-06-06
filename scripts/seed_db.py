#!/usr/bin/env python3
"""Seed MySQL from data/splits/*.csv (classified headlines)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mindful_news.db import init_db, stats
from mindful_news.seed import (
    SPLITS_DIR,
    count_real_headlines,
    load_split_rows,
    purge_test_headlines,
    seed_from_splits,
    seed_from_splits_if_needed,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Load classified headlines from data/splits into MySQL.")
    parser.add_argument(
        "--splits-dir",
        type=Path,
        default=SPLITS_DIR,
        help="Directory with train.csv, val.csv, test.csv",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Load even if real headlines already exist (upsert by URL)",
    )
    parser.add_argument(
        "--purge-test",
        action="store_true",
        help="Delete test.mindful-news.local rows before seeding",
    )
    args = parser.parse_args()

    init_db()

    if args.purge_test:
        removed = purge_test_headlines()
        print(f"Removed {removed} test headlines")

    if args.force:
        rows = load_split_rows(args.splits_dir)
        print(f"Loaded {len(rows)} rows from CSV (deduped by URL)")
        inserted = seed_from_splits(args.splits_dir)
        print(f"Inserted {inserted} new rows (rest updated or unchanged)")
    else:
        inserted = seed_from_splits_if_needed(args.splits_dir)
        if inserted:
            print(f"Seeded {inserted} headlines from {args.splits_dir}")
        elif count_real_headlines() > 0:
            print("DB already has real headlines — nothing to do (use --force to upsert)")
        else:
            print(f"No rows found in {args.splits_dir}")

    db_stats = stats()
    real = count_real_headlines()
    print(f"Real headlines in DB: {real}")
    print(f"Unclassified: {db_stats['unclassified']}")


if __name__ == "__main__":
    main()
