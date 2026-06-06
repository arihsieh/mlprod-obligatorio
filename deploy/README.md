# Deploy en EC2 (Learner Lab)

Un solo **EC2 + Docker Compose**. No hace falta ECS ni Elastic Beanstalk.

## 1. Crear la instancia (consola AWS)

| Campo | Valor |
|-------|-------|
| AMI | **Ubuntu Server 22.04 LTS** |
| Tipo | **t3.large** (8 GB) recomendado; **t3.medium** (4 GB) justo |
| Disco | **40 GB** gp3 |
| Key pair | Crear/descargar `.pem` |
| Security group | Ver abajo |

### Security group (inbound)

| Puerto | Origen | Uso |
|--------|--------|-----|
| 22 | Tu IP | SSH |
| 8501 | 0.0.0.0/0 | Portal Streamlit (Mindful) |
| 8000 | 0.0.0.0/0 | API `/docs` (obligatorio) |

MySQL **no** se expone (solo red interna de Docker).

## 2. Bootstrap en el server

```bash
ssh -i mindful.pem ubuntu@<EC2_PUBLIC_IP>
curl -fsSL https://raw.githubusercontent.com/<tu-user>/mlprod-obligatorio/main/deploy/ec2-setup.sh | bash
# o, si clonaste el repo:
bash deploy/ec2-setup.sh
exit
ssh -i mindful.pem ubuntu@<EC2_PUBLIC_IP>   # re-login para grupo docker
```

## 3. Subir código + modelos

Los modelos **no están en git** (~1.1 GB sin checkpoints).

**Desde tu PC (PowerShell):**

```powershell
# Empaquetar modelos (sin checkpoints duplicados)
.\scripts\pack_models.ps1

# Subir repo (sin models/ ni .env)
scp -i mindful.pem -r `
  config.yml docker-compose.prod.yml Dockerfile Dockerfile.portal `
  mindful_news portal scripts requirements*.txt `
  ubuntu@<EC2_IP>:~/mlprod-obligatorio/

scp -i mindful.pem models-deploy.tar.gz ubuntu@<EC2_IP>:~/
```

**En EC2:**

```bash
mkdir -p ~/mlprod-obligatorio/models
cd ~/mlprod-obligatorio
tar -xzf ~/models-deploy.tar.gz -C models/
```

## 4. Levantar el stack

```bash
cd ~/mlprod-obligatorio
docker compose -f docker-compose.prod.yml up --build -d
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -f api   # esperar "Application startup complete"
```

- Portal: `http://<EC2_IP>:8501`
- API docs: `http://<EC2_IP>:8000/docs`

Primera build: **10–20 min** (PyTorch + transformers).

## 5. Cargar datos iniciales (opcional)

Si MySQL en EC2 está vacío, importá desde tu PC:

```powershell
# Con túnel o export/import CSV vía scripts existentes apuntando DB_HOST al EC2
$env:DB_HOST = "<EC2_IP>"   # abrir 3306 solo temporalmente si hace falta
python scripts/export_dataset.py  # local
# luego import en EC2 — o correr scrape + poller local contra API remota
```

Más simple para demo: correr `run_poller.py --once` desde tu PC con:

```
DB_HOST=<EC2_IP>
API_BASE_URL=http://<EC2_IP>:8000
```

(solo si abrís MySQL al mundo temporalmente — mejor usar poller vía API batch sin DB remota, o importar dump).

## 6. Apagar sin quemar créditos

```bash
# En EC2 — parar contenedores
docker compose -f docker-compose.prod.yml down
```

En consola AWS: **EC2 → Instance state → Stop** (no Terminate).

## Credenciales Learner Lab

- Las keys del lab **expiran** al cerrar sesión (~4 h).
- **No las commitees** en git (`.env` ya está en `.gitignore`).
- No van en el server EC2; solo las usás vos para AWS CLI si hace falta.

## Poller en EC2 (opcional, 8 GB)

```bash
docker compose -f docker-compose.prod.yml --profile poller up -d
```

En 4 GB (`t3.medium`): scrape desde tu PC, no poller en el server.
