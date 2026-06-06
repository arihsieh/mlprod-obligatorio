#!/usr/bin/env python3
"""Launch the Streamlit portal."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "portal" / "app.py"


def main() -> None:
    subprocess.run(
        [sys.executable, "-m", "streamlit", "run", str(APP), "--server.address", "0.0.0.0"],
        check=True,
    )


if __name__ == "__main__":
    main()
