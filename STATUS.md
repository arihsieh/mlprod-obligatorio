# Mindful News — Estado del proyecto

Resumen de lo implementado hasta junio 2026 y próximos pasos.  
Plan completo del obligatorio: [mindful-news.md](./mindful-news.md) · Guía técnica: [README.md](./README.md)

---

## Resumen ejecutivo

| Fase | Estado | Notas |
|---|---|---|
| **1 — Scraping** | ✅ Completada | 4 medios · ~3.000 titulares c/u · MySQL |
| **2 — Tagging GPT** | ✅ Completada | 12.005 titulares clasificados · `tema` + `carga` |
| **3 — Entrenamiento mmBERT** | ⏳ Pendiente | EDA, split temporal, fine-tuning |
| **4 — API FastAPI + Docker** | ⏳ Pendiente | `/predict` online y batch |
| **5 — Portal Streamlit** | ⏳ Pendiente | Filtros + poller horario |

---

## Dónde están los resultados

Los datos **no** están en CSV ni en el repo. Viven en **MySQL local**:

| Parámetro | Valor |
|---|---|
| Host | `127.0.0.1:3306` |
| Base | `mindful_news` |
| Usuario / clave | `mindful` / `mindful` |
| Tabla | `headlines` |

```bash
source .venv/bin/activate
python scripts/inspect_db.py

mysql -u mindful -pmindful mindful_news -e "SELECT COUNT(*) FROM headlines;"
```

Logs de ejecución (no son el dataset): `data/logs/`

---

## Dataset actual (12.005 titulares)

| Medio | Titulares | Thumbnail | Fecha publicación | Clasificados |
|---|---:|---:|---:|---:|
| Montevideo Portal | 3.004 | 100% | 99,8% | 3.004 |
| El País | 3.001 | 100% | 100% | 3.001 |
| La Diaria | 3.000 | 0,9% | 100% | 3.000 |
| El Observador | 3.000 | 99,9% | 100% | 3.000 |
| **Total** | **12.005** | — | — | **12.005 (100%)** |

### Distribución de labels (GPT)

| Tema | Baja | Media | Alta | Total aprox. |
|---|---:|---:|---:|---:|
| política | 534 | 1.837 | 15 | ~2.386 |
| economía | 602 | 973 | 20 | ~1.595 |
| sociedad | 666 | 977 | 86 | ~1.729 |
| seguridad | 37 | 848 | 826 | ~1.711 |
| deportes | 912 | 450 | 12 | ~1.374 |
| internacional | 317 | 720 | 142 | ~1.179 |
| medioambiente | 207 | 417 | 38 | ~662 |
| cultura | 551 | 78 | 12 | ~641 |
| salud | 91 | 303 | 51 | ~445 |
| tecnología | 163 | 113 | 7 | ~283 |

*Los labels usan nombres sin tilde en código (`politica`, `economia`); en la DB pueden aparecer con tilde según la respuesta del modelo.*

---

## Qué se construyó

### Infraestructura

- **Python 3.11+** con venv, `requirements.txt`
- **MySQL** (`docker-compose.yml` disponible; en dev se usó Homebrew MySQL)
- **Playwright** (Chromium) para listados dinámicos
- **OpenAI** (`OPENAI_API_KEY` en `.env`) para clasificación

### Estructura del repo

```
mlprod-obligatorio/
├── config.yml                 # targets, DB, modelos GPT
├── mindful-news.md            # plan del obligatorio (actualizado)
├── STATUS.md                  # este archivo
├── README.md                  # setup y comandos
├── scripts/
│   ├── scrape_bulk.py         # ~3000 titulares por fuente
│   ├── scrape_hourly.py       # actualización incremental
│   ├── classify.py            # etiquetado GPT en lotes
│   ├── enrich_metadata.py     # backfill thumbnail + fecha
│   └── inspect_db.py          # resumen de la DB
└── mindful_news/
    ├── db.py                  # schema + upsert MySQL
    ├── http.py                # fetch artículos, og:image, fechas
    ├── dates.py               # parsers de fecha por medio
    ├── scrape/                # un módulo por fuente
    └── classify/              # prompts, schema, runner GPT
```

### Scraping por fuente

| Fuente | Estrategia bulk | Metadata |
|---|---|---|
| **Montevideo Portal** | Scroll por categoría + backfill concurrente por ID `-uc{id}` | Página de artículo: `og:image`, fecha, h1 |
| **El País** | Últimas noticias + secciones paginadas + enrich desde artículo | `article:published_time`, og:image |
| **La Diaria** | Sitemap de URLs (paywall bloquea artículo) | Fecha desde news sitemap; thumbnails solo en listado reciente |
| **El Observador** | Seed de secciones + backfill `-n{id}` | `.news-detail__date`, og:image |

Campos guardados por titular: `titulo`, `url`, `thumbnail_url`, `medio`, `seccion`, `fecha`, `tema`, `carga`, `classified_at`, `source_run`.

### Clasificación (Fase 2)

- Modelo: **`gpt-5.4-mini`** (~25 titulares por llamada, JSON estructurado)
- Prompt optimizado con **`gpt-5.5`** → `mindful_news/classify/prompt_config.json`
- 10 temas + 3 niveles de carga (ver `mindful_news/classify/labels.py`)
- **12.005 / 12.005** etiquetados (0 pendientes)

> **Nota:** El plan original mencionaba OpenAI Batch API (async, 24 h). Se implementó clasificación **síncrona en lotes** para iterar más rápido durante el desarrollo. Para producción o re-etiquetado masivo conviene migrar a Batch API.

### Problemas resueltos durante el desarrollo

- Listados MVD con links basura → selectores `article.noticia h2`
- Thumbnails MVD → imagen en el `article` padre
- El País paginaba de más → stop temprano al alcanzar `target`
- La Diaria paywall → sitemap en lugar de fetch de artículo
- EO `seccion` demasiado larga → columna `VARCHAR(255)` + truncado
- EO fechas vacías → selector CSS corregido (contenedor vacío matcheaba antes)
- El País sin fecha/thumb en listados → `enrich_metadata.py` + enrich en bulk

### Limitaciones conocidas

1. **La Diaria — thumbnails (~1%)**: el paywall redirige a login; solo ~26 thumbs del homepage/listado.
2. **La Diaria — fechas antiguas**: algunas vienen aproximadas (año/mes desde URL del sitemap).
3. **Sin export CSV/Parquet**: hay que exportar desde MySQL o agregar script.
4. **Sin EDA notebook** todavía: distribución arriba es inspección rápida, falta análisis formal.
5. **Split train/val/test** no generado aún.

---

## Comandos útiles

```bash
# Entorno
source .venv/bin/activate
brew services start mysql    # o: docker compose up -d

# Re-scrapear una fuente
python scripts/scrape_bulk.py --sources la_diaria --target 100

# Clasificar titulares nuevos
python scripts/classify.py

# Backfill metadata faltante
python scripts/enrich_metadata.py --sources el_pais el_observador

# Actualización horaria (scrape + classify pendientes)
python scripts/scrape_hourly.py
```

---

## Próximos pasos (orden sugerido)

### 1. Exportar dataset para ML

- [ ] Script `scripts/export_dataset.py` → CSV/Parquet en `data/exports/`
- [ ] Incluir columnas: `titulo`, `tema`, `carga`, `fecha`, `medio`, `url`, `thumbnail_url`
- [ ] Versionar el export (fecha en el nombre del archivo)

### 2. EDA + validación de labels (Fase 2 — cierre)

- [ ] Notebook `eda/exploratory.ipynb`
- [ ] Distribución por tema/carga y por medio (detectar sesgo)
- [ ] Muestreo manual de casos dudosos (~50–100 titulares)
- [ ] Decidir si re-etiquetar outliers o unificar tildes (`economia` vs `economía`)

### 3. Split temporal (evitar leakage)

- [ ] Split por `fecha`: train / val / test (no aleatorio)
- [ ] Verificar mínimo ~200 ejemplos por clase en train
- [ ] Guardar splits en `data/splits/` o tablas MySQL

### 4. Entrenamiento mmBERT-small (Fase 3)

- [ ] `training/train_temas.py` — 10 clases
- [ ] `training/train_carga.py` — 3 clases
- [ ] Métricas: F1 macro, matriz de confusión
- [ ] MLflow (electivo): experimentos y artefactos
- [ ] SHAP en test set (electivo)
- [ ] Quantization INT8 + Optuna (electivo)

### 5. API + Docker (Fase 4)

- [ ] FastAPI: `POST /predict`, `POST /predict/batch`, `GET /predict/batch/{id}`
- [ ] Función `preprocess()` compartida train/serve
- [ ] Dockerfile + docker-compose con modelos montados
- [ ] Swagger en `/docs`

### 6. Portal + pipeline horario (Fase 5)

- [ ] Conectar `scrape_hourly.py` → API → MySQL
- [ ] Streamlit: filtros por tema/carga, link al medio original
- [ ] Thumbnails en UI donde existan

### 7. Mejoras opcionales de scraping

- [ ] La Diaria: sesión autenticada para thumbnails completos
- [ ] Export periódico automático post-scrape
- [ ] Migrar clasificación a OpenAI Batch API para costo menor en re-runs

---

## Referencia rápida de archivos clave

| Archivo | Rol |
|---|---|
| `config.yml` | Target 3000/fuente, credenciales DB, modelos GPT |
| `mindful_news/scrape/*.py` | Lógica de scraping por medio |
| `mindful_news/classify/prompt_config.json` | Prompt optimizado |
| `mindful_news/db.py` | Schema `headlines` + upsert |
| `data/logs/*.log` | Historial de corridas bulk/classify/enrich |

---

*Última actualización: junio 2026 — Fases 1 y 2 completas, dataset listo para EDA y entrenamiento.*
