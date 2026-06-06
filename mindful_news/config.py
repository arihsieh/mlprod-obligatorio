import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from yaml import load
from yaml.loader import SafeLoader

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.yml"


def load_config() -> dict[str, Any]:
    with open(CONFIG_PATH, encoding="utf-8") as file:
        config = load(file, Loader=SafeLoader)

    env_map = {
        "bulk_target_per_source": "BULK_TARGET_PER_SOURCE",
        "hourly_limit_per_source": "HOURLY_LIMIT_PER_SOURCE",
        "log_level": "LOG_LEVEL",
        "request_delay_min": "REQUEST_DELAY_MIN",
        "request_delay_max": "REQUEST_DELAY_MAX",
        "classification_model": "CLASSIFICATION_MODEL",
        "prompt_model": "PROMPT_MODEL",
        "classification_batch_size": "CLASSIFICATION_BATCH_SIZE",
    }
    for key, env_key in env_map.items():
        if os.getenv(env_key):
            config[key] = os.getenv(env_key)

    db = config.setdefault("database", {})
    for field, env_key in (
        ("host", "DB_HOST"),
        ("port", "DB_PORT"),
        ("user", "DB_USER"),
        ("password", "DB_PASSWORD"),
        ("name", "DB_NAME"),
    ):
        if os.getenv(env_key):
            db[field] = os.getenv(env_key)

    return config
