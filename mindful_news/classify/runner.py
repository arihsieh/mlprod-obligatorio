import json
import time
from logging import Logger

from mindful_news.classify.client import get_client, load_prompt_config
from mindful_news.classify.labels import CARGA_SET, TEMA_SET
from mindful_news.classify.schema import CLASSIFICATION_RESPONSE_SCHEMA
from mindful_news.config import load_config
from mindful_news.db import count_unclassified, fetch_unclassified, update_classifications


def _chunk(items: list, size: int) -> list[list]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def classify_batch(client, config: dict, batch: list[dict], model: str) -> list[dict]:
    payload = [{"id": row["id"], "titulo": row["titulo"]} for row in batch]
    user_content = config["batch_user_template"].format(
        batch_json=json.dumps(payload, ensure_ascii=False)
    )
    response = client.responses.create(
        model=model,
        reasoning={"effort": "none"},
        text={
            "verbosity": "low",
            "format": {
                "type": "json_schema",
                "name": "headline_classification_batch",
                "schema": CLASSIFICATION_RESPONSE_SCHEMA,
            },
        },
        input=[
            {"role": "system", "content": config["system_prompt"]},
            {"role": "user", "content": user_content},
        ],
    )
    parsed = json.loads(response.output_text)
    expected = {row["id"] for row in batch}
    results = []
    for item in parsed["items"]:
        headline_id = int(item["id"])
        tema, carga = item["tema"], item["carga"]
        if headline_id not in expected:
            raise ValueError(f"Unexpected id {headline_id}")
        if tema not in TEMA_SET or carga not in CARGA_SET:
            raise ValueError(f"Invalid labels {tema}/{carga}")
        results.append({"id": headline_id, "tema": tema, "carga": carga})
    if len(results) != len(batch):
        raise ValueError(f"Batch mismatch sent={len(batch)} got={len(results)}")
    return results


def run_classification(
    logger: Logger,
    limit: int | None = None,
    batch_size: int | None = None,
    sleep_s: float = 0.5,
) -> int:
    cfg = load_config()
    config = load_prompt_config()
    model = cfg.get("classification_model", "gpt-5.4-mini")
    batch_size = batch_size or int(config.get("recommended_batch_size", cfg.get("classification_batch_size", 25)))
    client = get_client()
    pending = fetch_unclassified(limit=limit)
    logger.info(
        "Classifying %d headlines (pending=%d, batch=%d, model=%s)",
        len(pending),
        count_unclassified(),
        batch_size,
        model,
    )
    classified = 0
    for index, batch in enumerate(_chunk(pending, batch_size), start=1):
        results = classify_batch(client, config, batch, model)
        update_classifications(results)
        classified += len(results)
        logger.info("Batch %d: %d/%d done", index, classified, len(pending))
        if index * batch_size < len(pending):
            time.sleep(sleep_s)
    logger.info("Classification finished: %d labeled", classified)
    return classified
