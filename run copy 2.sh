#!/usr/bin/env bash
set -Eeuo pipefail

echo "==> Activando entorno virtual..."
source .venv/Scripts/activate

echo "==> Iniciando Redis..."
docker compose -f compose.yml up -d redis

echo "==> Esperando a que Redis esté disponible..."
until docker compose -f compose.yml exec -T redis redis-cli ping 2>/dev/null | grep -q PONG; do
    sleep 1
done

export REDIS_URL="${REDIS_URL:-redis://localhost:6379}"

PHOENIX_PID=""
API_PID=""
WORKER_PID=""

cleanup() {
    echo "==> Deteniendo procesos..."

    for pid in "$API_PID" "$WORKER_PID" "$PHOENIX_PID"; do
        if [[ -n "$pid" ]]; then
            kill "$pid" 2>/dev/null || true
        fi
    done

    for pid in "$API_PID" "$WORKER_PID" "$PHOENIX_PID"; do
        if [[ -n "$pid" ]]; then
            wait "$pid" 2>/dev/null || true
        fi
    done
}

trap cleanup EXIT INT TERM

echo "==> Iniciando Phoenix..."
python -m phoenix.server.main serve &
PHOENIX_PID=$!

echo "==> Iniciando FastAPI..."
python -m uvicorn app.main:app --reload &
API_PID=$!

echo "==> Iniciando worker..."
python -m app.worker &
WORKER_PID=$!



echo "==> Servicios iniciados."
echo "==> Phoenix: http://localhost:6006"
echo "==> Swagger: http://127.0.0.1:8000/docs"

wait -n "$API_PID" "$WORKER_PID" "$PHOENIX_PID"