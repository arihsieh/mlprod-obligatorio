#!/usr/bin/env python3
"""Hourly scrape + ML classification via API."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from apscheduler.schedulers.blocking import BlockingScheduler

from mindful_news.config import load_config
from mindful_news.log import get_logger
from mindful_news.portal.poller import run_hourly_pipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape and classify headlines hourly.")
    parser.add_argument("--once", action="store_true", help="Run one cycle and exit")
    parser.add_argument("--interval-hours", type=float, default=0.5)
    parser.add_argument("--scrape-limit", type=int, default=None)
    parser.add_argument("--classify-limit", type=int, default=None, help="Max per batch; default=all pending")
    args = parser.parse_args()

    cfg = load_config()
    logger = get_logger("run_poller", int(cfg["log_level"]))

    def job() -> None:
        result = run_hourly_pipeline(
            logger,
            scrape_limit=args.scrape_limit,
            classify_limit=args.classify_limit,
        )
        logger.info("Pipeline listo: %s", result)

    if args.once:
        job()
        return

    scheduler = BlockingScheduler()
    scheduler.add_job(job, "interval", hours=args.interval_hours, id="hourly_pipeline")
    logger.info("Poller iniciado (cada %.1f h)", args.interval_hours)
    scheduler.start()


if __name__ == "__main__":
    main()
