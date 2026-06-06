#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mindful_news.db import connection, init_db, stats


def main() -> None:
    init_db()
    summary = stats()
    print("Headlines by source:")
    for row in summary["by_medio"]:
        print(f"  {row['medio']}: {row['total']}")
    print(f"\nUnclassified: {summary['unclassified']}")
    print("\nLabel distribution:")
    for row in summary["labels"]:
        print(f"  {row['tema']:15} {row['carga']:6} {row['total']}")

    with connection() as conn:
        with conn.cursor() as cursor:
            for medio in ("Montevideo Portal", "El País", "La Diaria", "El Observador"):
                cursor.execute(
                    "SELECT titulo, fecha, thumbnail_url, tema, carga FROM headlines "
                    "WHERE medio = %s ORDER BY COALESCE(fecha, scraped_at) DESC LIMIT 3",
                    (medio,),
                )
                rows = cursor.fetchall()
                print(f"\nLatest from {medio}:")
                for row in rows:
                    thumb = "yes" if row["thumbnail_url"] else "no"
                    print(f"  [{row['fecha']}] ({thumb}) {row['titulo'][:65]}")
                    if row["tema"]:
                        print(f"    -> {row['tema']} / {row['carga']}")


if __name__ == "__main__":
    main()
