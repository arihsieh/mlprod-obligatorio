from datetime import datetime
from logging import FileHandler, Formatter, Logger, StreamHandler, getLogger
from pathlib import Path

from mindful_news.config import ROOT


def get_logger(name: str, level: int = 20) -> Logger:
    log_dir = ROOT / "data" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    logger = getLogger(name)
    logger.setLevel(level)

    if not logger.handlers:
        formatter = Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        stream = StreamHandler()
        stream.setFormatter(formatter)
        file_handler = FileHandler(log_dir / f"{datetime.now():%Y-%m-%d}.log")
        file_handler.setFormatter(formatter)
        logger.addHandler(stream)
        logger.addHandler(file_handler)

    logger.propagate = False
    return logger
