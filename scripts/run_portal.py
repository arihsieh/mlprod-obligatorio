#!/usr/bin/env python3
"""Launch the API server and open the portal in the browser."""
from __future__ import annotations

import sys
import threading
import time
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import uvicorn

PORTAL_URL = "http://localhost:8000/portal"


def _open_browser() -> None:
    time.sleep(2.5)
    webbrowser.open(PORTAL_URL)


def main() -> None:
    threading.Thread(target=_open_browser, daemon=True).start()
    print(f"Portal disponible en: {PORTAL_URL}")
    uvicorn.run("mindful_news.api.main:app", host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":
    main()
