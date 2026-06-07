#!/usr/bin/env python3
"""Fetch article pages to backfill missing thumbnail_url and fecha."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mindful_news.config import load_config
from mindful_news.db import init_db
from mindful_news.enrich import enrich_pending_from_db
from mindful_news.log import get_logger


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill thumbnail and fecha from article pages.")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    cfg = load_config()
    logger = get_logger("enrich_metadata", int(cfg["log_level"]))
    init_db()
    enrich_pending_from_db(logger, limit=args.limit)


if __name__ == "__main__":
    main()
