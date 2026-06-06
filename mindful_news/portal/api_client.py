from __future__ import annotations

import os
import time
from typing import Any

import requests


def api_base_url() -> str:
    return os.getenv("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")


def predict_one(titulo: str, seccion: str | None = None) -> dict[str, Any]:
    response = requests.post(
        f"{api_base_url()}/predict",
        json={"titulo": titulo, "seccion": seccion},
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


def predict_batch(
    items: list[dict[str, str | None]],
    *,
    poll_interval: float = 0.5,
    timeout: float = 300,
) -> list[dict[str, Any]]:
    response = requests.post(
        f"{api_base_url()}/predict/batch",
        json={"items": items},
        timeout=60,
    )
    response.raise_for_status()
    job_id = response.json()["job_id"]

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status_response = requests.get(
            f"{api_base_url()}/predict/batch/{job_id}",
            timeout=30,
        )
        status_response.raise_for_status()
        payload = status_response.json()
        if payload["status"] == "completed":
            return payload["results"] or []
        if payload["status"] == "failed":
            raise RuntimeError(payload.get("error") or "batch job failed")
        time.sleep(poll_interval)

    raise TimeoutError(f"batch job {job_id} did not complete within {timeout}s")
