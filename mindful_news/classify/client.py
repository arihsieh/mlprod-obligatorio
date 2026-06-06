import json
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from mindful_news.config import ROOT, load_config

load_dotenv()
PROMPT_CONFIG_PATH = Path(__file__).with_name("prompt_config.json")


def get_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set.")
    return OpenAI(api_key=api_key)


def load_prompt_config() -> dict:
    if PROMPT_CONFIG_PATH.exists():
        return json.loads(PROMPT_CONFIG_PATH.read_text(encoding="utf-8"))
    from mindful_news.classify.prompts import DEFAULT_BATCH_USER_TEMPLATE, DEFAULT_SYSTEM_PROMPT

    return {
        "system_prompt": DEFAULT_SYSTEM_PROMPT,
        "batch_user_template": DEFAULT_BATCH_USER_TEMPLATE,
        "recommended_batch_size": load_config().get("classification_batch_size", 25),
    }


def save_prompt_config(config: dict) -> None:
    PROMPT_CONFIG_PATH.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
