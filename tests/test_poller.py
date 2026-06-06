"""Tests for the hourly poller pipeline."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from mindful_news.portal.poller import classify_unclassified


def test_classify_unclassified_uses_api_results() -> None:
    rows = [
        {"id": 1, "titulo": "Titular A", "seccion": "deportes"},
        {"id": 2, "titulo": "Titular B", "seccion": None},
    ]
    predict_fn = MagicMock(
        return_value=[
            {"tema": "deportes", "carga": "baja"},
            {"tema": "politica", "carga": "media"},
        ]
    )
    logger = MagicMock()

    with patch("mindful_news.portal.poller.fetch_unclassified", return_value=rows):
        with patch("mindful_news.portal.poller.update_classifications", return_value=2) as save:
            count = classify_unclassified(logger, predict_fn=predict_fn)

    assert count == 2
    predict_fn.assert_called_once()
    save.assert_called_once_with(
        [
            {"id": 1, "tema": "deportes", "carga": "baja"},
            {"id": 2, "tema": "politica", "carga": "media"},
        ]
    )


def test_classify_unclassified_empty() -> None:
    logger = MagicMock()
    with patch("mindful_news.portal.poller.fetch_unclassified", return_value=[]):
        assert classify_unclassified(logger) == 0
