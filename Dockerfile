FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-ml.txt requirements-api.txt ./
RUN pip install --no-cache-dir -r requirements-api.txt

COPY mindful_news/ mindful_news/
COPY portal/index.html portal/index.html
COPY data/splits/ data/splits/
COPY config.yml .
COPY scripts/run_api.py scripts/run_api.py

ENV MODEL_TEMAS_PATH=/app/models/temas-phase4
ENV MODEL_CARGA_PATH=/app/models/carga-phase3

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/ready')"

CMD ["python", "scripts/run_api.py"]
