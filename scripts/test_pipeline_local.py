#!/usr/bin/env python3
"""Local end-to-end pipeline test: DB → scrape/seed → API batch → verify."""
from __future__ import annotations

import argparse
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests

from mindful_news.config import load_config
from mindful_news.db import count_unclassified, fetch_headlines, init_db, save_headlines, stats
from mindful_news.log import get_logger
from mindful_news.models import Headline
from mindful_news.portal.api_client import api_base_url
from mindful_news.portal.poller import classify_unclassified, scrape_latest

SAMPLE_HEADLINES = [
    (
        "Peñarol goleó 3-0 y es líder del Apertura",
        "deportes",
        "El Observador",
    ),
    (
        "Balacera en el Cerro deja dos heridos",
        "Noticias, Policiales",
        "Montevideo Portal",
    ),
    (
        "Gobierno anunció ajuste en jubilaciones",
        "Noticias, Política",
        "El País",
    ),
    (
        "Uruguay avanza en acuerdo comercial regional",
        "internacional",
        "La Diaria",
    ),
    (
        "Festival de jazz reunió a miles en el Velódromo",
        "cultura",
        "La Diaria",
    ),
]


def check_api(timeout: float = 3.0) -> None:
    url = f"{api_base_url()}/ready"
    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise SystemExit(
            f"API no disponible en {url}\n"
            f"  → Levantá primero: python scripts/run_api.py\n"
            f"  Error: {exc}"
        ) from exc
    print(f"✓ API lista en {api_base_url()}")


def seed_fake_headlines(n: int) -> int:
    run_id = uuid.uuid4().hex[:8]
    headlines: list[Headline] = []
    for index in range(n):
        titulo, seccion, medio = SAMPLE_HEADLINES[index % len(SAMPLE_HEADLINES)]
        headlines.append(
            Headline(
                titulo=f"[test-{run_id}] {titulo}",
                url=f"https://test.mindful-news.local/{run_id}/{index}",
                medio=medio,
                seccion=seccion,
                fecha=datetime.now(timezone.utc).replace(tzinfo=None),
                external_id=f"test-{run_id}-{index}",
            )
        )
    saved = save_headlines(headlines, source_run="pipeline_test")
    print(f"✓ Insertados {saved} titulares de prueba (run={run_id})")
    return saved


def print_stats() -> None:
    db_stats = stats()
    print(f"  Sin clasificar: {db_stats['unclassified']}")
    print(f"  Por medio: {db_stats['by_medio']}")


def print_sample_classified(limit: int = 5) -> None:
    rows = fetch_headlines(
        temas=["deportes", "seguridad", "politica", "internacional", "cultura"],
        cargas=["baja", "media", "alta"],
        limit=limit,
    )
    test_rows = [r for r in rows if "test.mindful-news.local" in r.get("url", "")]
    if not test_rows:
        test_rows = rows[:limit]
    print(f"\n=== Muestra clasificada ({len(test_rows)} filas) ===")
    for row in test_rows:
        print(
            f"  [{row['tema']}|{row['carga']}] {row['medio']}: "
            f"{row['titulo'][:70]}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Probar pipeline local scrape → API → DB.")
    parser.add_argument(
        "--fake",
        type=int,
        default=0,
        help="Insertar N titulares sintéticos (sin Playwright)",
    )
    parser.add_argument(
        "--scrape-limit",
        type=int,
        default=0,
        help="Scrape real por fuente (Playwright). 0 = omitir.",
    )
    parser.add_argument(
        "--classify-limit",
        type=int,
        default=50,
        help="Máximo de titulares sin clasificar a mandar a la API",
    )
    parser.add_argument("--skip-api-check", action="store_true")
    parser.add_argument("--skip-classify", action="store_true")
    args = parser.parse_args()

    if args.fake <= 0 and args.scrape_limit <= 0:
        parser.error("Indicá --fake N y/o --scrape-limit N")

    cfg = load_config()
    logger = get_logger("test_pipeline", int(cfg["log_level"]))

    print("==> 1. MySQL")
    init_db()
    print_stats()

    if not args.skip_api_check:
        print("\n==> 2. API")
        check_api()

    print("\n==> 3. Ingesta")
    if args.fake > 0:
        seed_fake_headlines(args.fake)
    if args.scrape_limit > 0:
        print(f"   Scrape real (limit={args.scrape_limit} por fuente)...")
        scraped = scrape_latest(logger, limit=args.scrape_limit)
        print(f"✓ Scrape guardó {scraped} filas")
    print(f"   Pendientes de clasificar: {count_unclassified()}")

    if args.skip_classify:
        print("\n(Omitida clasificación --skip-classify)")
        return

    print("\n==> 4. Clasificación vía API (batch)")
    classified = classify_unclassified(logger, limit=args.classify_limit)
    print(f"✓ Clasificados: {classified}")
    print_stats()

    print("\n==> 5. Verificación")
    print_sample_classified()
    print("\n✓ Pipeline OK. Abrí el portal: python scripts/run_portal.py")


if __name__ == "__main__":
    main()
