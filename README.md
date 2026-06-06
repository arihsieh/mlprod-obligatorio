# Mindful News — Scraper & Classifier

Uruguayan news headline pipeline (Fase 1–2 of [mindful-news.md](./mindful-news.md)).  
**Estado y próximos pasos:** [STATUS.md](./STATUS.md)

**Sources:** Montevideo Portal · El País · La Diaria · El Observador

Each headline stores: `titulo`, `url`, `thumbnail_url`, `fecha`, `medio`, `seccion`, plus GPT labels `tema` / `carga`.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
cp .env.example .env   # add OPENAI_API_KEY
brew services start mysql   # or: docker compose up -d
```

## Usage

```bash
# Dry run
python scripts/scrape_bulk.py --target 5 --sources la_diaria el_observador
python scripts/classify.py --limit 10

# Full training dataset (3000 per source by default)
python scripts/scrape_bulk.py

# Classify all unclassified headlines (~25 per API call, gpt-5.4-mini)
python scripts/classify.py

# Hourly live updates
python scripts/scrape_hourly.py

# Inspect DB
python scripts/inspect_db.py

# Backfill missing thumbnail/fecha from article pages
python scripts/enrich_metadata.py --sources el_pais el_observador
```

## ML training (Fase 3)

```bash
# GPU PyTorch first (PyPI default on Windows is CPU-only)
pip install torch==2.12.0+cu126 --index-url https://download.pytorch.org/whl/cu126
pip install -r requirements-ml.txt

# Export + temporal split (needs MySQL or data/exports/headlines_*.csv)
python scripts/export_dataset.py
python scripts/split_dataset.py

# Download base model + fine-tune (logs to Weights & Biases)
python scripts/download_model.py

# Phase 1: broad search (15 trials/task)
python scripts/tune_models.py --task all --phase 1 --trials 15

# Phase 2: first refinement (30 trials/task)
python scripts/tune_models.py --task all --phase 2 --trials 30

# Phase 3: corrected search around phase-1 winners (15 trials/task)
python scripts/tune_models.py --task all --phase 3 --trials 15 --no-resume

# Resume after interrupt (same command; sqlite study in data/tuning/)
python scripts/tune_models.py --task temas --phase 2 --trials 30

# Fixed-hyperparameter baseline (no search)
python scripts/train_temas.py
python scripts/train_carga.py
```

Resume artifacts: `data/tuning/{temas,carga}.db`, `{task}_study.json`, `{task}_best.json`.  
Trial checkpoints: `models/tuning/{task}/trial-NNN/`. Final models: `models/{temas,carga}/`.

## Layout

```
config.yml              # targets, DB, models
scripts/                # CLI entry points
mindful_news/
  db.py                 # MySQL
  scrape/               # one module per source
  classify/             # GPT batch labeling
```

## Scraping strategy

| Source | Bulk | Metadata |
|---|---|---|
| Montevideo Portal | Category scroll + article-ID backfill | Article page (date, og:image) |
| El País | Últimas noticias + section pagination | Listing date + thumbnail |
| La Diaria | Sitemap URLs + listing thumbnails | News sitemap dates; ~recent thumbs from homepage |
| El Observador | Section seed + `-n{id}` backfill | JSON-LD / span date, og:image |
