"""Integration tests for the Mindful News API."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from mindful_news.api import main as api_main
from mindful_news.inference import HeadlinePrediction


@pytest.fixture
def mock_classifier() -> MagicMock:
    classifier = MagicMock()
    classifier.predict.return_value = HeadlinePrediction(
        tema="seguridad",
        carga="alta",
        tema_confidence=0.95,
        carga_confidence=0.88,
        input_text_temas="Noticias, Policiales | Balacera en el Cerro",
    )
    classifier.predict_batch.return_value = [
        HeadlinePrediction(
            tema="deportes",
            carga="baja",
            tema_confidence=0.91,
            carga_confidence=0.82,
            input_text_temas="deportes | Peñarol ganó",
        ),
        HeadlinePrediction(
            tema="politica",
            carga="media",
            tema_confidence=0.87,
            carga_confidence=0.79,
            input_text_temas="politica | El gobierno anunció",
        ),
    ]
    return classifier


@pytest.fixture
def client(mock_classifier: MagicMock):
    api_main._jobs.clear()
    with patch("mindful_news.api.main.NewsClassifier", return_value=mock_classifier):
        with TestClient(api_main.app) as test_client:
            yield test_client
    api_main._classifier = None
    api_main._jobs.clear()


def test_health_when_models_loaded(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["models_loaded"] is True


def test_ready(client: TestClient) -> None:
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"


def test_ready_without_models(mock_classifier: MagicMock) -> None:
    with patch("mindful_news.api.main.NewsClassifier", return_value=mock_classifier):
        with TestClient(api_main.app) as test_client:
            api_main._classifier = None
            response = test_client.get("/ready")
            assert response.status_code == 503
    api_main._classifier = None


def test_predict(client: TestClient, mock_classifier: MagicMock) -> None:
    response = client.post(
        "/predict",
        json={
            "titulo": "Balacera en el Cerro deja dos heridos",
            "seccion": "Noticias, Policiales",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["tema"] == "seguridad"
    assert payload["carga"] == "alta"
    assert payload["tema_confidence"] == pytest.approx(0.95)
    assert payload["latencia_ms"] >= 0
    mock_classifier.predict.assert_called_once_with(
        "Balacera en el Cerro deja dos heridos",
        "Noticias, Policiales",
    )


def test_predict_requires_titulo(client: TestClient) -> None:
    response = client.post("/predict", json={"titulo": ""})
    assert response.status_code == 422


def test_batch_with_items(client: TestClient, mock_classifier: MagicMock) -> None:
    response = client.post(
        "/predict/batch",
        json={
            "items": [
                {"titulo": "Peñarol ganó", "seccion": "deportes"},
                {"titulo": "El gobierno anunció medidas", "seccion": "politica"},
            ]
        },
    )
    assert response.status_code == 200
    job_id = response.json()["job_id"]

    status = client.get(f"/predict/batch/{job_id}")
    assert status.status_code == 200
    payload = status.json()
    assert payload["status"] == "completed"
    assert payload["results"] is not None
    assert len(payload["results"]) == 2
    assert payload["results"][0]["tema"] == "deportes"
    assert payload["results"][1]["carga"] == "media"
    mock_classifier.predict_batch.assert_called_once()


def test_batch_with_titulares(client: TestClient) -> None:
    response = client.post(
        "/predict/batch",
        json={"titulares": ["Titular uno", "Titular dos"]},
    )
    assert response.status_code == 200
    job_id = response.json()["job_id"]
    status = client.get(f"/predict/batch/{job_id}")
    assert status.json()["status"] == "completed"


def test_batch_requires_payload(client: TestClient) -> None:
    response = client.post("/predict/batch", json={})
    assert response.status_code == 422


def test_batch_job_not_found(client: TestClient) -> None:
    response = client.get("/predict/batch/does-not-exist")
    assert response.status_code == 404
