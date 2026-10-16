
#!/usr/bin/env bash
set -Eeuo pipefail

echo "==> Activando entorno virtual..."
source .venv/bin/activate

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
    trap - EXIT INT TERM
    echo
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

    echo "==> Procesos detenidos."
}

trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

echo "==> Iniciando Phoenix..."
python -m phoenix.server.main serve &
PHOENIX_PID=$!

echo "==> Iniciando FastAPI..."
python -m uvicorn app.main:app --reload &
API_PID=$!

echo "==> Iniciando worker..."
python -m app.worker &
WORKER_PID=$!

echo "==> Esperando a que FastAPI esté disponible..."
SWAGGER_READY=0

for ((attempt=1; attempt<=60; attempt++)); do
    if curl -fsS http://127.0.0.1:8000/openapi.json >/dev/null 2>&1; then
        SWAGGER_READY=1
        break
    fi

    if ! kill -0 "$API_PID" 2>/dev/null; then
        echo "ERROR: FastAPI terminó antes de estar disponible."
        exit 1
    fi

    sleep 1
done

if [[ "$SWAGGER_READY" -eq 1 ]]; then
    echo "==> FastAPI está lista. Abriendo Swagger..."
    if command -v xdg-open >/dev/null 2>&1; then
        xdg-open "http://127.0.0.1:8000/docs" >/dev/null 2>&1 &
    else
        echo "No se encontró xdg-open. Abrí http://127.0.0.1:8000/docs manualmente."
    fi
else
    echo "ADVERTENCIA: FastAPI no respondió en 60 segundos."
fi

echo "==> Phoenix: http://localhost:6006"
echo "==> Swagger: http://127.0.0.1:8000/docs"
echo "==> Presioná Ctrl+C para detener los procesos."

wait -n "$API_PID" "$WORKER_PID" "$PHOENIX_PID"
