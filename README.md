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
