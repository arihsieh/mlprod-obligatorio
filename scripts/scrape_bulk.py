#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mindful_news.config import load_config
from mindful_news.db import init_db, save_headlines
from mindful_news.log import get_logger
from mindful_news.scrape import ALL_SOURCES, BULK_SCRAPERS


def main() -> None:
    parser = argparse.ArgumentParser(description="Bulk scrape headlines for training.")
    parser.add_argument("--target", type=int, default=None)
    parser.add_argument("--sources", nargs="*", default=ALL_SOURCES)
    args = parser.parse_args()

    cfg = load_config()
    logger = get_logger("scrape_bulk", int(cfg["log_level"]))
    target = args.target or int(cfg["bulk_target_per_source"])

    init_db()
    logger.info("Bulk scrape target=%d sources=%s", target, args.sources)

    for key in args.sources:
        if key not in BULK_SCRAPERS:
            raise SystemExit(f"Unknown source: {key}")
        headlines = BULK_SCRAPERS[key](logger, target)
        saved = save_headlines(headlines, source_run="bulk")
        logger.info("%s: scraped=%d saved=%d", key, len(headlines), saved)

    logger.info("Bulk scrape complete")


if __name__ == "__main__":
    main()
