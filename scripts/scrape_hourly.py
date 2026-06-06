#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mindful_news.config import load_config
from mindful_news.db import init_db, save_headlines
from mindful_news.log import get_logger
from mindful_news.scrape import ALL_SOURCES, LATEST_SCRAPERS


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape latest headlines.")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--sources", nargs="*", default=ALL_SOURCES)
    args = parser.parse_args()

    cfg = load_config()
    logger = get_logger("scrape_hourly", int(cfg["log_level"]))
    limit = args.limit or int(cfg["hourly_limit_per_source"])

    init_db()
    for key in args.sources:
        headlines = LATEST_SCRAPERS[key](logger, limit)
        save_headlines(headlines, source_run="hourly")
        logger.info("%s: %d headlines", key, len(headlines))


if __name__ == "__main__":
    main()
