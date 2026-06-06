#!/usr/bin/env python3
"""Export headlines to portable SQL dump + CSV for moving the project."""
import argparse
import csv
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mindful_news.config import load_config
from mindful_news.db import connection, init_db

EXPORT_DIR = Path(__file__).resolve().parents[1] / "data" / "exports"

CSV_COLUMNS = (
    "id",
    "external_id",
    "titulo",
    "url",
    "thumbnail_url",
    "medio",
    "seccion",
    "fecha",
    "scraped_at",
    "source_run",
    "tema",
    "carga",
    "classified_at",
)


def export_csv(path: Path) -> int:
    query = f"SELECT {', '.join(CSV_COLUMNS)} FROM headlines ORDER BY id"
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: (value.isoformat(sep=" ") if hasattr(value, "isoformat") else value)
                    for key, value in row.items()
                }
            )
    return len(rows)


def export_sql(path: Path) -> None:
    db = load_config()["database"]
    cmd = [
        "mysqldump",
        f"-h{db['host']}",
        f"-P{db['port']}",
        f"-u{db['user']}",
        f"-p{db['password']}",
        "--skip-lock-tables",
        "--no-tablespaces",
        db["name"],
        "headlines",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "mysqldump failed")
    path.write_text(result.stdout, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Export headlines for backup or transfer.")
    parser.add_argument("--csv-only", action="store_true")
    parser.add_argument("--sql-only", action="store_true")
    args = parser.parse_args()

    init_db()
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d")
    csv_path = EXPORT_DIR / f"headlines_{stamp}.csv"
    sql_path = EXPORT_DIR / f"mindful_news_{stamp}.sql"

    do_csv = not args.sql_only
    do_sql = not args.csv_only

    if do_csv:
        count = export_csv(csv_path)
        print(f"CSV:  {csv_path} ({count} rows)")

    if do_sql:
        export_sql(sql_path)
        size_mb = sql_path.stat().st_size / (1024 * 1024)
        print(f"SQL:  {sql_path} ({size_mb:.1f} MB)")

    print(f"\nCopy the whole repo plus {EXPORT_DIR}/ to the new machine.")
    print("Restore SQL: mysql -u mindful -pmindful mindful_news < data/exports/mindful_news_*.sql")


if __name__ == "__main__":
    main()
