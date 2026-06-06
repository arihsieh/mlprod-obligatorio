#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mindful_news.classify.runner import run_classification
from mindful_news.config import load_config
from mindful_news.db import init_db, stats
from mindful_news.log import get_logger


def main() -> None:
    parser = argparse.ArgumentParser(description="Classify headlines with GPT.")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--batch-size", type=int, default=None)
    parser.add_argument("--sleep", type=float, default=0.5)
    args = parser.parse_args()

    cfg = load_config()
    logger = get_logger("classify", int(cfg["log_level"]))
    init_db()
    run_classification(logger, limit=args.limit, batch_size=args.batch_size, sleep_s=args.sleep)
    summary = stats()
    logger.info("Unclassified remaining: %d", summary["unclassified"])


if __name__ == "__main__":
    main()
