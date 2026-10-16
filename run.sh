
#!/usr/bin/env bash
# -E herencia de errores -e el script termina si hay alguna falla y el error no esta controlado -u solo se usan variables definidas
# -o si falla algo de la tuveria falla todo
set -Eeuo pipefail

echo "==> Activando entorno virtual..."

# source modifica variables de entorno, afecta PATH
source .venv/Scripts/activate

echo "==> Iniciando Redis..."
# -f indica que archivo de configuracion utilizar -d deja la ejecucion en segundo plano -redis significa del compose ejecutar redis
docker compose -f compose.yml up -d redis

echo "==> Esperando a que Redis esté disponible..."
# until es como un while mientras se ejecute -T se desactiva la terminal interactiva, redis redis-cli para preguntar si redis responde
# grep busca PONG sin mostrarlo -q
until docker compose -f compose.yml exec -T redis redis-cli ping 2>/dev/null | grep -q PONG; do
    sleep 1
done

export REDIS_URL="${REDIS_URL:-redis://localhost:6379}"

PHOENIX_PID=""
API_PID=""
WORKER_PID=""

# clean up declara una funcion de bash
# trap - EXIT INT TERM: elimina temporalmente las trampas para evitar que la propia limpieza vuelva a activarlas.

cleanup() {
    # Evita que las señales vuelvan a ejecutar la limpieza.
    trap - EXIT INT TERM

    echo
    echo "==> Deteniendo procesos..."

    # Cierra también los procesos hijos, incluido Uvicorn --reload.
    for pid in "$API_PID" "$WORKER_PID" "$PHOENIX_PID"; do
    # [[ -n "$pid" ]] si la variable pid no esta vacia -n
        if [[ -n "$pid" ]]; then
        # fuerza el cierre del proceso
            taskkill.exe //PID "$pid" //T //F >/dev/null 2>&1 || true
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

# se limpian los errores
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# 2- SE INICIAN LOS SERVICIOS
# asociacion de las variables a los servicios
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

# esperar a que fast api este lista max 60 sec 1 x segundo
for ((attempt=1; attempt<=60; attempt++)); do
# curl realiza una solicitud HTTP
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
    explorer.exe "http://127.0.0.1:8000/docs" >/dev/null 2>&1 &
else
    echo "ADVERTENCIA: FastAPI no respondió en 60 segundos."
    echo "Swagger: http://127.0.0.1:8000/docs"
fi

echo "==> Phoenix: http://localhost:6006"
echo "==> Swagger: http://127.0.0.1:8000/docs"
echo "==> Presioná Ctrl+C para detener los procesos."

wait -n "$API_PID" "$WORKER_PID" "$PHOENIX_PID"
