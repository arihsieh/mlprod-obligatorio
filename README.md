# Mindful News — Scraper & Classifier

Uruguayan news headline pipeline ([mindful-news.md](./mindful-news.md)).  
**Estado y próximos pasos:** [STATUS.md](./STATUS.md)

**Sources:** Montevideo Portal · El País · La Diaria · El Observador

Each headline stores: `titulo`, `url`, `thumbnail_url`, `fecha`, `medio`, `seccion`, plus labels `tema` / `carga`.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
cp .env.example .env   # add OPENAI_API_KEY
docker compose up -d mysql   # or local MySQL on :3306
```

## Usage — scraping & GPT tagging

```bash
# Dry run
python scripts/scrape_bulk.py --target 5 --sources la_diaria el_observador
python scripts/classify.py --limit 10

# Full training dataset (3000 per source by default)
python scripts/scrape_bulk.py

# Classify all unclassified headlines (~25 per API call, gpt-5.4-mini)
python scripts/classify.py

# Hourly live updates (scrape only)
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

# Phase 4: temas with seccion+título input (30 trials)
python scripts/tune_models.py --task temas --phase 4 --trials 30

# Resume after interrupt (same command; sqlite study in data/tuning/)
python scripts/tune_models.py --task temas --phase 2 --trials 30

# Fixed-hyperparameter baseline (no search)
python scripts/train_temas.py
python scripts/train_carga.py
```

Production models: `models/temas-phase4/` (temas) · `models/carga-phase3/` (carga).  
Resume artifacts: `data/tuning/{task}_phase{N}_best.json`, trial checkpoints in `models/tuning/`.

Analysis notebooks: `notebooks/01_eda` … `04_checks_finales`.

## API (Fase 4)

```bash
pip install -r requirements-api.txt
python scripts/run_api.py
# Swagger: http://localhost:8000/docs
```

Endpoints:

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/health` | Liveness (`models_loaded`) |
| GET | `/ready` | Readiness (503 hasta cargar modelos) |
| POST | `/predict` | `{ "titulo", "seccion?" }` → tema + carga |
| POST | `/predict/batch` | Async batch → `job_id` |
| GET | `/predict/batch/{id}` | Resultados del job |

```bash
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{"titulo": "Balacera en el Cerro", "seccion": "Noticias, Policiales"}'
```

Tests (sin cargar modelos reales):

```bash
pip install -r requirements-dev.txt
python -m pytest tests/ -q
```

## Portal + poller (Fase 5)

```bash
pip install -r requirements-portal.txt

# Terminal 1 — API (si no corre ya)
python scripts/run_api.py

# Terminal 2 — portal Streamlit
python scripts/run_portal.py
# → http://localhost:8501

# Poller: scrape + clasificar vía API cada hora
python scripts/run_poller.py --once          # un ciclo
python scripts/run_poller.py                 # loop cada 1 h
```

El poller toma titulares sin clasificar de MySQL, los manda a `POST /predict/batch` y guarda `tema`/`carga` del modelo ML.

### Probar pipeline local (antes de AWS)

```bash
# Terminal 1 — MySQL
docker compose up -d mysql

# Terminal 2 — API
python scripts/run_api.py

# Terminal 3 — test end-to-end
# Opción A: titulares sintéticos (rápido, sin Playwright)
python scripts/test_pipeline_local.py --fake 5

# Opción B: scrape real mínimo + clasificar
python scripts/test_pipeline_local.py --scrape-limit 2

# Opción C: ambos
python scripts/test_pipeline_local.py --fake 3 --scrape-limit 2

# Terminal 4 — portal
python scripts/run_portal.py
```

El script verifica MySQL → API `/ready` → ingesta → batch → muestra titulares clasificados.

## Docker — stack completo

Requiere modelos entrenados en `models/temas-phase4/` y `models/carga-phase3/`.

**Incremental (recomendado):**

```powershell
# Windows — un paso a la vez, espera health entre cada uno
.\scripts\docker_up.ps1 -Step mysql   # ~30s
.\scripts\docker_up.ps1 -Step api     # primera build ~10-15 min
.\scripts\docker_up.ps1 -Step portal  # opcional
.\scripts\docker_up.ps1 -Step poller  # opcional
```

**Todo junto (solo mysql + api por defecto; portal/poller con profile):**

```bash
docker compose up --build -d              # mysql + api
docker compose --profile portal up -d     # + Streamlit
docker compose --profile poller up -d     # + poller horario
```

| Servicio | Puerto | Rol |
|----------|--------|-----|
| `mysql` | 3306 | Base de datos |
| `api` | 8000 | FastAPI + mmBERT |
| `portal` | 8501 | Streamlit |
| `poller` | — | Scrape + clasificación horaria |

Solo MySQL: `docker compose up -d mysql`  
Solo API: `docker compose up --build api`

### EC2 (Learner Lab — sin Lightsail)

Guía paso a paso: **[deploy/README.md](./deploy/README.md)**

Resumen: **1× EC2 t3.large + Docker Compose** (`docker-compose.prod.yml`).

```bash
# En EC2 (Ubuntu 22.04)
bash deploy/ec2-setup.sh
docker compose -f docker-compose.prod.yml up --build -d
```

Desde Windows, empaquetar modelos: `.\scripts\pack_models.ps1`

Variables útiles (`.env`): `API_BASE_URL`, `DB_HOST`, `MODEL_TEMAS_PATH`, `MODEL_CARGA_PATH`.  
**No commitees** credenciales AWS del Learner Lab.

## Layout

```
config.yml
scripts/                  # CLI entry points
notebooks/                # EDA, training, sanity checks
portal/app.py             # Streamlit UI
mindful_news/
  db.py                   # MySQL
  inference.py            # predictor compartido train ↔ serve
  api/                    # FastAPI
  portal/                 # poller + cliente API
  scrape/                 # one module per source
  classify/               # GPT batch labeling
  training/               # fine-tuning + evaluate
models/
  temas-phase4/           # producción temas
  carga-phase3/           # producción carga
```

## Scraping strategy

| Source | Bulk | Metadata |
|---|---|---|
| Montevideo Portal | Category scroll + article-ID backfill | Article page (date, og:image) |
| El País | Últimas noticias + section pagination | Listing date + thumbnail |
| La Diaria | Sitemap URLs + listing thumbnails | News sitemap dates; ~recent thumbs from homepage |
| El Observador | Section seed + `-n{id}` backfill | JSON-LD / span date, og:image |
