
#!/usr/bin/env bash
set -Eeuo pipefail

echo "==> Iniciando Redis..."
docker compose -f compose.yml up -d redis

echo "==> Esperando a que Redis esté disponible..."
until docker compose -f compose.yml exec -T redis redis-cli ping 2>/dev/null | grep -q PONG; do
    sleep 1
done

echo "==> Verificando REDIS_URL..."
export REDIS_URL="${REDIS_URL:-redis://localhost:6379}"

echo "==> Iniciando FastAPI y el worker..."

cleanup() {
    echo "==> Deteniendo procesos..."
    kill "$API_PID" "$WORKER_PID" 2>/dev/null || true
    wait "$API_PID" "$WORKER_PID" 2>/dev/null || true
    kill "$API_PID" "$WORKER_PID" "$PHOENIX_PID" 2>/dev/null || true
    wait "$API_PID" "$WORKER_PID" "$PHOENIX_PID" 2>/dev/null || true
}

trap cleanup EXIT INT TERM

echo "==> Iniciando Phoenix..."
python -m phoenix.server.main serve &
PHOENIX_PID=$!

python -m uvicorn app.main:app --reload &
API_PID=$!

python -m app.worker &
WORKER_PID=$!

wait -n "$API_PID" "$WORKER_PID"
