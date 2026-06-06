# Plan de proyecto — Clasificador de noticias uruguayas
### Sistema de ML para salud mental informativa

> **Estado (jun 2026):** Fases **1 y 2 completas** — 12.005 titulares de 4 medios en MySQL, 100% clasificados con GPT.  
> Detalle de implementación, métricas y próximos pasos: **[STATUS.md](./STATUS.md)** · Comandos: **[README.md](./README.md)**

---

## Problema que resolvemos

El consumo de noticias genera ansiedad no solo por el contenido sino por cómo está presentado. Los medios usan titulares diseñados para el click, no para informar. Este proyecto construye un sistema que clasifica titulares de noticias uruguayas por **tema** y **carga emocional**, y los expone en un portal propio que actualiza cada hora con links a los medios originales.

No filtramos contenido. No editamos. Solo clasificamos y damos control al lector.

---

## Arquitectura del sistema

```
┌─────────────────────────────────────────────────────────────────┐
│              FASE 1 — SCRAPING  ✅ IMPLEMENTADA                  │
│                                                                 │
│  Mvd Portal  ·  El Observador  ·  El País  ·  La Diaria        │
│        │               │               │           │            │
│        └───────────────┴───────────────┴───────────┘            │
│                              │                                  │
│         Playwright + requests + BeautifulSoup                   │
│         extrae: título · URL · thumbnail · medio · fecha       │
│                              │                                  │
│              MySQL (tabla headlines) — 12.005 titulares         │
│              ~3.000 por fuente · upsert por URL                 │
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│         FASE 2 — TAGGING CON GPT  ✅ IMPLEMENTADA               │
│                                                                 │
│   Lotes síncronos a gpt-5.4-mini (~25 titulares/llamada)        │
│   Prompt optimizado con gpt-5.5 → tema + carga en MySQL         │
│   (Plan original: Batch API async — ver nota en Fase 2)        │
│                              │                                  │
│              EDA + validación de distribución de clases  ⏳      │
│              Split train/val/test estratificado por fecha  ⏳    │
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│                    FASE 3 — ENTRENAMIENTO                       │
│                                                                 │
│   Modelo A (temas · 10 clases)     Modelo B (carga · 3 clases) │
│   base: jhu-clsp/mmBERT-small      base: jhu-clsp/mmBERT-small  │
│   fine-tuning con HF Trainer       fine-tuning independiente    │
│                                                                 │
│   Optimización: quantization INT8 · hyperparameter tuning       │
│   Trazabilidad: MLflow · experimentos, modelos, datos           │
│   Explicabilidad: SHAP sobre predicciones del test set          │
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│                    FASE 4 — API + DOCKER                        │
│                                                                 │
│   POST /predict          →  online, respuesta inmediata         │
│   POST /predict/batch    →  async, devuelve job_id + polling    │
│   GET  /predict/batch/{id} →  estado + resultados               │
│                                                                 │
│   FastAPI · Dockerfile · docker-compose · Swagger docs          │
│   Despliegue en AWS Academy                                     │
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│                    FASE 5 — PORTAL WEB                          │
│                                                                 │
│   APScheduler: scrape + clasifica + guarda cada hora            │
│   Streamlit: filtros por tema y carga · link al medio original  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Fase 1 — Scraping de datos ✅

### Fuentes (las cuatro implementadas)

| Medio | URL | Estado | Estrategia | Notas |
|---|---|---|---|---|
| Montevideo Portal | montevideo.com.uy | ✅ | Scroll + backfill `-uc{id}` | Thumbnail y fecha desde artículo |
| El Observador | elobservador.com.uy | ✅ | Secciones + backfill `-n{id}` | Fecha en `.news-detail__date` |
| El País | elpais.com.uy | ✅ | Últimas + secciones + enrich | Headers + enrich desde artículo |
| La Diaria | ladiaria.com.uy | ✅ | Sitemap URLs | Paywall: fechas vía sitemap; thumbs limitados |

### Qué extraer por titular

```python
{
  "titulo":        "Balacera en el Cerro deja dos heridos",
  "url":           "https://www.elobservador.com.uy/...",
  "thumbnail_url": "https://media.elobservador.com.uy/.../imagen.webp",
  "medio":         "El Observador",
  "seccion":       "nacional",      # URL o HTML cuando está disponible
  "fecha":         "2026-06-04T22:01:00",
  "tema":          "seguridad",     # Fase 2 — GPT
  "carga":         "alta"           # Fase 2 — GPT
}
```

### Stack técnico (implementado)

```
Playwright (Chromium) + requests + BeautifulSoup4
→ rotación de User-Agent
→ delay aleatorio entre requests (1–3s)
→ guardado incremental en MySQL (upsert por URL, evita duplicados)
→ scripts: scrape_bulk.py · scrape_hourly.py · enrich_metadata.py
```

### Volumen objetivo

**Alcanzado:** 12.005 titulares (3.000+ por fuente). Suficiente para entrenar y hacer EDA. Si alguna clase queda desbalanceada, oversampling o ejemplos extra a mano en Fase 2.

---

## Fase 2 — Tagging automático con GPT ✅ / EDA ⏳

### Implementación actual (completada)

- **12.005 titulares** etiquetados en MySQL (`tema`, `carga`, `classified_at`)
- **Modelo:** `gpt-5.4-mini` · ~25 titulares por llamada · JSON estructurado
- **Prompt:** optimizado con `gpt-5.5` → `mindful_news/classify/prompt_config.json`
- **Comando:** `python scripts/classify.py`

### Plan original — OpenAI Batch API (referencia)

El tagging manual de miles de titulares es inviable. La **OpenAI Batch API** procesa un JSONL de forma asíncrona (hasta 24 h, ~50% costo). Durante el desarrollo se usaron **lotes síncronos** para iterar más rápido; la Batch API sigue siendo opción para re-runs masivos.

### Prompt de tagging (base del obligatorio)

```python
SYSTEM = """
Sos un clasificador de noticias uruguayas.
Respondé SOLO con JSON válido, sin texto adicional.
"""

USER = """
Titular: "{titulo}"

Clasificá en:
- tema: política | seguridad | economía | salud | deportes |
        cultura | tecnología | medioambiente | internacional | sociedad
- carga: baja | media | alta

La "carga" mide el potencial de generar ansiedad o estrés en el lector,
independientemente del tono del titular.

Respuesta:
{{"tema": "...", "carga": "..."}}
"""
```

### Flujo Batch API (referencia — no implementado aún)

```python
# 1. Armar el archivo batch
import json

requests = []
for i, row in df.iterrows():
    requests.append({
        "custom_id": f"titular-{i}",
        "method": "POST",
        "url": "/v1/chat/completions",
        "body": {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": USER.format(titulo=row["titulo"])}
            ],
            "response_format": {"type": "json_object"},
            "max_tokens": 50
        }
    })

with open("batch_input.jsonl", "w") as f:
    for r in requests:
        f.write(json.dumps(r) + "\n")

# 2. Enviar y esperar
client = OpenAI()
batch_file = client.files.create(file=open("batch_input.jsonl", "rb"), purpose="batch")
batch_job  = client.batches.create(
    input_file_id=batch_file.id,
    endpoint="/v1/chat/completions",
    completion_window="24h"
)

# 3. Polling (correr después)
job = client.batches.retrieve(batch_job.id)
if job.status == "completed":
    result = client.files.content(job.output_file_id)
    # parsear JSONL → agregar tema y carga al dataset
```

### EDA post-tagging ⏳ pendiente

Antes de entrenar, validar:

- Distribución de clases (que no haya desbalance extremo)
- Ejemplos por categoría (mínimo ~200 por clase para entrenar bien)
- Casos confusos (titulares que podrían ser dos temas a la vez)
- Bias por medio (si un medio produce 80% de titulares de "seguridad")

Herramientas: pandas + matplotlib + seaborn → `eda/exploratory.ipynb` (por crear).  
Distribución preliminar en [STATUS.md](./STATUS.md).

### Split del dataset ⏳ pendiente

```python
# Split por fecha, NO aleatorio — evita data leakage temporal
# Titulares del mismo evento no quedan en train y test a la vez

train_df = df[df["fecha"] < "2025-05-01"]
val_df   = df[(df["fecha"] >= "2025-05-01") & (df["fecha"] < "2025-05-20")]
test_df  = df[df["fecha"] >= "2025-05-20"]

# Verificar distribución estratificada por clase en cada split
```

---

## Fase 3 — Entrenamiento de modelos

### Elección del modelo base: `jhu-clsp/mmBERT-small`

BETO (el BERT en español) era la opción obvia, pero hay algo mejor para este caso.

**mmBERT-small** es un encoder multilingual publicado en septiembre 2025, construido sobre la arquitectura **ModernBERT**. Es la primera mejora significativa sobre XLM-R en tareas multilingüe, con resultados superiores en clasificación de texto en español.

| Modelo | Parámetros | Tamaño aprox. | Español | Velocidad |
|---|---|---|---|---|
| BETO (bert-base-spanish) | 110M | ~440MB | Solo español | Lenta |
| XLM-RoBERTa-base | 278M | ~1.1GB | Multilingual | Lenta |
| distilbert-multilingual | 134M | ~540MB | Multilingual | Media |
| **mmBERT-small** | **42M** | **~140MB** | **Multilingual (1800+ langs)** | **Rápida** |

Las ventajas concretas:
- Flash Attention 2 → entrenamiento 3x más rápido que BERT clásico
- 42M parámetros no-embedding → liviano en producción
- Contexto de 8.192 tokens (irrelevante para títulos, pero muestra la arquitectura moderna)
- MIT License → sin restricciones para el proyecto
- Supera a mDEBERTa y mDistilBERT en benchmarks multilingüe recientes

### Dos modelos independientes

**Por qué dos y no uno con dos cabezas:** tema y carga son tareas distintas. Un titular de economía puede ser verde o rojo. Entrenándolos por separado podés iterar cada uno independientemente, mostrar métricas separadas en la entrega, y debuggear sin que una tarea afecte a la otra.

#### Modelo A — Clasificador de temas

```
Clases (10):
  política · seguridad · economía · salud · deportes ·
  cultura · tecnología · medioambiente · internacional · sociedad
```

```python
from transformers import AutoTokenizer, AutoModelForSequenceClassification, Trainer, TrainingArguments
from datasets import Dataset

MODEL_ID = "jhu-clsp/mmBERT-small"
tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)

model_temas = AutoModelForSequenceClassification.from_pretrained(
    MODEL_ID, num_labels=10
)

training_args = TrainingArguments(
    output_dir="./model-temas",
    num_train_epochs=5,
    per_device_train_batch_size=32,
    learning_rate=2e-5,
    warmup_ratio=0.1,
    evaluation_strategy="epoch",
    save_strategy="best",
    load_best_model_at_end=True,
    metric_for_best_model="f1_macro",
    fp16=True,            # mixed precision
    report_to="mlflow"    # trazabilidad
)
```

#### Modelo B — Clasificador de carga emocional

```
Clases (3):
  baja · media · alta
```

Mismo proceso, mismo modelo base, distinto fine-tuning. La carga es más subjetiva que el tema, así que es esperable que tenga F1 un poco menor — está bien documentarlo así en el informe.

### Optimizaciones (electivo — implementar las dos para sumar puntos)

**Quantization INT8** — reduce el modelo de ~140MB a ~35MB sin pérdida significativa de accuracy:

```python
from optimum.quanto import quantize, freeze, qint8

quantize(model, weights=qint8)
freeze(model)
# Medir latencia antes y después → incluir en informe
```

**Hyperparameter tuning** con Optuna:

```python
from ray import tune
# Buscar sobre: learning_rate, batch_size, num_epochs, warmup_ratio
# Reportar el mejor trial en MLflow
```

### Evaluación

```python
from sklearn.metrics import classification_report, ConfusionMatrixDisplay
import shap

# F1 macro y por clase (no solo accuracy — las clases pueden estar desbalanceadas)
print(classification_report(y_test, y_pred))

# Matriz de confusión → qué clases se confunden entre sí
ConfusionMatrixDisplay.from_predictions(y_test, y_pred)

# SHAP para explicabilidad (electivo)
explainer = shap.Explainer(model, tokenizer)
shap_values = explainer(test_samples)
shap.plots.text(shap_values[0])   # qué palabras empujan cada clase
```

### Trazabilidad con MLflow (electivo)

```python
import mlflow

mlflow.set_experiment("noticias-clasificador")

with mlflow.start_run(run_name="mmBERT-small-temas-v1"):
    mlflow.log_params(training_args.to_dict())
    mlflow.log_metrics({"f1_macro": 0.87, "accuracy": 0.89})
    mlflow.log_artifact("model-temas/")
    mlflow.log_artifact("data/train.csv")     # versionar el dato también
```

Versionamos: experimentos, modelos, y el dataset de entrenamiento.

---

## Fase 4 — API con FastAPI

### Endpoints

```
POST /predict
  body: { "titulo": "Balacera en el Cerro deja dos heridos" }
  response: { "tema": "seguridad", "carga": "alta", "latencia_ms": 45 }

POST /predict/batch
  body: { "titulares": ["...", "...", "..."] }
  response: { "job_id": "abc123" }

GET  /predict/batch/{job_id}
  response: { "status": "completed", "results": [...] }
```

### Implementación

```python
from fastapi import FastAPI, BackgroundTasks
from transformers import pipeline
import uuid, asyncio

app = FastAPI(title="Clasificador de Noticias UY", version="1.0")

# Cargar modelos al arrancar (no en cada request)
clf_temas = pipeline("text-classification", model="./model-temas")
clf_carga = pipeline("text-classification", model="./model-carga")

jobs = {}  # en producción: Redis o DB

@app.post("/predict")
def predict(body: PredictRequest):
    tema = clf_temas(body.titulo)[0]
    carga = clf_carga(body.titulo)[0]
    return {"tema": tema["label"], "carga": carga["label"]}

@app.post("/predict/batch")
def predict_batch(body: BatchRequest, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "pending", "results": []}
    background_tasks.add_task(run_batch, job_id, body.titulares)
    return {"job_id": job_id}

@app.get("/predict/batch/{job_id}")
def get_batch_result(job_id: str):
    return jobs.get(job_id, {"error": "job no encontrado"})
```

### Prevención de training-serving skew

El texto de entrada en producción pasa exactamente por el mismo preprocesamiento que en entrenamiento. Se encapsula en una función `preprocess(texto: str) -> str` compartida entre el pipeline de entrenamiento y la API. Nada de normalización "extra" en producción.

```python
def preprocess(texto: str) -> str:
    texto = texto.strip()
    texto = re.sub(r"\s+", " ", texto)
    # NO hacer: lowercase, stemming, quitar puntuación
    # el tokenizador del modelo lo maneja solo
    return texto
```

### Docker

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

```yaml
# docker-compose.yml
services:
  api:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - ./models:/app/models
    environment:
      - MODEL_TEMAS_PATH=/app/models/temas
      - MODEL_CARGA_PATH=/app/models/carga
```

La documentación de la API la genera FastAPI automáticamente en `/docs` (Swagger UI) y `/redoc`.

---

## Fase 5 — Portal web con Streamlit

### Poller por hora

```python
from apscheduler.schedulers.background import BackgroundScheduler

def poll_and_classify():
    titulares = scrape_all_sources()           # scraper de Fase 1
    resultados = requests.post(
        "http://api:8000/predict/batch",
        json={"titulares": [t["titulo"] for t in titulares]}
    ).json()
    # guardar en MySQL con labels
    save_to_db(titulares, resultados)

scheduler = BackgroundScheduler()
scheduler.add_job(poll_and_classify, "interval", hours=1)
scheduler.start()
```

### Portal Streamlit

```python
import streamlit as st
import pandas as pd
from mindful_news.db import connection  # MySQL

st.title("Noticias UY — Clasificadas")

col1, col2 = st.columns(2)
with col1:
    temas_sel = st.multiselect(
        "Temas",
        ["política","seguridad","economía","salud","deportes",
         "cultura","tecnología","medioambiente","internacional","sociedad"],
        default=["deportes","cultura","tecnología"]
    )
with col2:
    cargas_sel = st.multiselect(
        "Carga emocional",
        ["baja","media","alta"],
        default=["baja","media"]
    )

df = load_from_db(temas=temas_sel, cargas=cargas_sel)

for _, row in df.iterrows():
    st.markdown(f"**[{row['titulo']}]({row['url']})**")
    st.caption(f"{row['medio']} · {row['tema']} · carga {row['carga']} · {row['fecha']}")
    st.divider()
```

El portal solo muestra el titular y linkea al medio original. No reproduce el artículo.

---

## Requerimientos del obligatorio — cobertura

| Requerimiento | Tipo | Cómo se cubre |
|---|---|---|
| Dataset no estructurado propio | Mínimo | Titulares scrapeados de medios UY |
| Análisis EDA | Mínimo | Jupyter Notebook post-tagging |
| Clasificación multiclase | Mínimo | 10 clases de tema + 3 de carga |
| Target definido por el equipo | Mínimo | Tema y carga emocional |
| Dependencias (dev + prod) | Mínimo | `requirements.txt` + `requirements-dev.txt` |
| Docker | Mínimo | Dockerfile + docker-compose |
| Git + GitHub | Mínimo | Repositorio público con commits |
| Prevención data leakage | Mínimo | Split temporal por fecha |
| Prevención training-serving skew | Mínimo | Función `preprocess()` compartida |
| API online + batch | Mínimo | FastAPI con `/predict` y `/predict/batch` |
| Documentación API | Mínimo | Swagger UI automático de FastAPI |
| Scraper web | Electivo ✅ | BeautifulSoup sobre 4 medios UY |
| Trazabilidad ML | Electivo ✅ | MLflow: experimentos, modelos, datos |
| Explicabilidad | Electivo ✅ | SHAP sobre predicciones del test set |
| Visualización Streamlit | Electivo ✅ | Portal web con filtros |
| Optimización de modelos | Electivo ✅ | Quantization INT8 + hyperparameter tuning |

**Electivos implementados: 5 de 6.** Solo se requieren 3.

---

## Stack técnico completo

```
Lenguaje:       Python 3.11+
Scraping:       Playwright · requests · BeautifulSoup4
Almacenamiento: MySQL (mindful_news.headlines)
ML:             transformers · datasets · torch · optimum  (Fase 3)
Tagging:        openai — gpt-5.4-mini en lotes (Fase 2 ✅)
Trazabilidad:   mlflow  (Fase 3)
Explicabilidad: shap  (Fase 3)
API:            fastapi · uvicorn · pydantic  (Fase 4)
Scheduler:      scrape_hourly.py + apscheduler  (Fase 5)
Portal:         streamlit  (Fase 5)
Infra:          Docker · docker-compose · AWS Academy
Versionado:     git · GitHub
```

---

## Estructura de repositorio (actual)

```
mlprod-obligatorio/
├── config.yml
├── mindful-news.md          # este plan
├── STATUS.md                # estado + próximos pasos
├── README.md                # setup y comandos
├── scripts/
│   ├── scrape_bulk.py
│   ├── scrape_hourly.py
│   ├── classify.py
│   ├── enrich_metadata.py
│   └── inspect_db.py
├── mindful_news/
│   ├── db.py
│   ├── http.py · dates.py · browser.py
│   ├── scrape/              # montevideo_portal · el_pais · la_diaria · el_observador
│   └── classify/            # client · runner · prompts · prompt_config.json
├── eda/                     # ⏳ exploratory.ipynb
├── training/                # ⏳ train_temas.py · train_carga.py
├── api/                     # ⏳ FastAPI
├── portal/                  # ⏳ Streamlit
├── Dockerfile · docker-compose.yml
└── requirements.txt
```

<details>
<summary>Estructura sugerida original (referencia)</summary>

```
clasificador-noticias-uy/
├── scraper/
│   ├── scraper.py           # lógica de scraping por fuente
│   └── sources.py           # config de URLs y selectores CSS
├── tagging/
│   ├── batch_send.py        # envío a OpenAI Batch API
│   ├── batch_receive.py     # procesamiento del resultado
│   └── prompts.py           # prompts de clasificación
├── eda/
│   └── exploratory.ipynb    # análisis del dataset
├── training/
│   ├── train_temas.py
│   ├── train_carga.py
│   └── evaluate.py
├── api/
│   ├── main.py              # FastAPI app
│   ├── models.py            # Pydantic schemas
│   └── classifier.py        # wrapper de inferencia
├── portal/
│   └── app.py               # Streamlit
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── requirements-dev.txt
└── README.md
```

</details>

---

## Cronograma tentativo

| Semana | Tarea | Estado |
|---|---|---|
| 1 | Scraper funcionando, dataset crudo recolectado | ✅ 4 medios · 12.005 titulares |
| 2 | Tagging GPT, EDA, split train/val/test | 🟡 Tagging ✅ · EDA y split ⏳ |
| 3 | Fine-tuning Modelo A (temas) + evaluación | ⏳ |
| 4 | Fine-tuning Modelo B (carga) + optimización | ⏳ |
| 5 | API FastAPI + Docker + despliegue AWS | ⏳ |
| 6 | Portal Streamlit + MLflow + SHAP + informe | ⏳ |

---

## Notas de diseño y decisiones tomadas

**Por qué solo títulos y no el artículo completo:** el título es exactamente donde está la carga emocional manipulada. Los medios optimizan los títulos para el click, no el cuerpo. Clasificar el título es más rápido, más barato, y ataca el problema real. El cuerpo del artículo queda para trabajo futuro.

**Por qué mmBERT-small y no BETO:** BETO solo entiende español. mmBERT-small entiende 1.800+ idiomas, pesa 3x menos (140MB vs 440MB), usa Flash Attention que lo hace 3x más rápido en entrenamiento, y en benchmarks multilingüe recientes supera a mDistilBERT y XLM-R-base. No hay razón académica ni práctica para usar BETO en 2025.

**Por qué GPT para el tagging y no hacerlo a mano:** 3.000 titulares anotados a mano son semanas de trabajo. GPT via API los etiqueta en horas, a bajo costo, con consistencia. En este proyecto se usó `gpt-5.4-mini` en lotes síncronos; el plan original proponía Batch API para mayor escala.

**Por qué MySQL y no SQLite/CSV:** upsert por URL, consultas para titulares sin clasificar, y preparación para el portal horario que actualiza la misma base.

**Por qué dos modelos y no uno multi-output:** tema y carga son tareas independientes. Un titular de economía puede ser baja, media o alta carga. Entrenarlos juntos complica el entrenamiento, dificulta el debugging, y no agrega valor real para este tamaño de dataset.

**Por qué split temporal y no aleatorio:** si el split es aleatorio, el mismo evento (una elección, un accidente, una crisis) puede tener titulares en train y en test. Eso infla el accuracy artificialmente porque el modelo "ya vio" el tema. El split temporal es más honesto sobre el rendimiento real.
