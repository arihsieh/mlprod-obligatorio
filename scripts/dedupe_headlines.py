#!/usr/bin/env python3
"""Remove duplicate headlines that share medio + numeric external_id."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mindful_news.db import init_db, merge_duplicate_external_ids


def main() -> None:
    init_db()
    removed = merge_duplicate_external_ids()
    print(f"Removed {removed} duplicate rows")


if __name__ == "__main__":
    main()
