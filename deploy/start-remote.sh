#!/usr/bin/env bash
set -euo pipefail
cd ~/mlprod-obligatorio

echo "==> Extracting models..."
mkdir -p models/temas-phase4 models/carga-phase3
tar -xzf ~/models-deploy.tar.gz -C models/

echo "==> Building and starting containers (first build ~15-20 min)..."
export MYSQL_ROOT_PASSWORD="${MYSQL_ROOT_PASSWORD:-MindfulRoot2026!}"
export MYSQL_PASSWORD="${MYSQL_PASSWORD:-MindfulDb2026!}"
sudo docker system prune -af || true
rm -f ~/models-deploy.tar.gz || true
sudo docker compose -f docker-compose.prod.yml build api
sudo docker compose -f docker-compose.prod.yml build poller
sudo docker compose -f docker-compose.prod.yml up -d

echo "==> Waiting for API..."
for i in $(seq 1 60); do
  if curl -sf http://localhost:8000/ready >/dev/null 2>&1; then
    echo "API ready."
    sudo docker compose -f docker-compose.prod.yml ps
    exit 0
  fi
  echo "  attempt $i/60..."
  sleep 15
done

echo "API not ready yet — check logs:"
sudo docker compose -f docker-compose.prod.yml logs api --tail 40
exit 1
