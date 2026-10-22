import os
import time
import uuid

import httpx
import pytest

BASE_URL = os.getenv(
    "TEST_BASE_URL",
    "http://127.0.0.1:8000",
)

TIMEOUT_SECONDS = 180
POLL_INTERVAL_SECONDS = 2


@pytest.mark.e2e
def test_consulta_real_completa_end_to_end():
    """
    Prueba el flujo real:
    FastAPI -> Redis -> Worker -> LangGraph/RAG -> respuesta.
    Requiere que run.sh esté ejecutándose y que las credenciales
    de los servicios externos estén configuradas.
    """

    query = (
        "Explicá brevemente qué es la regresión y cómo se calcula."
    )

    with httpx.Client(base_url=BASE_URL,timeout=30) as client:

        # 1. Enviar una consulta real.
        response = client.post(
            "/process",
            json={"query": query},
        )

        assert response.status_code == 200, (
            f"Error al crear la tarea: {response.text}"
        )

        task = response.json()

        assert task.get("job_id")
        assert task["status"] == "pending"

        job_id = task["job_id"]

        # 2. Esperar a que el worker termine.
        deadline = time.monotonic() + TIMEOUT_SECONDS
        last_status = None

        while time.monotonic() < deadline:
            status_response = client.get(
                f"/status/{job_id}",
            )

            assert status_response.status_code == 200, (
                f"Error consultando estado: "
                f"{status_response.text}"
            )

            task_status = status_response.json()
            last_status = task_status["status"]

            if last_status == "completed":
                break

            if last_status == "failed":
                pytest.fail(
                    "El procesamiento falló: "
                    f"{task_status.get('error')}"
                )

            if last_status == "waiting_approval":
                pytest.fail(
                    "La tarea quedó esperando aprobación humana; "
                    "esta prueba esperaba una respuesta automática."
                )

            time.sleep(POLL_INTERVAL_SECONDS)

        else:
            pytest.fail(
                f"La tarea {job_id} no terminó en "
                f"{TIMEOUT_SECONDS} segundos. "
                f"Último estado: {last_status}"
            )

        # 3. Verificar el resultado persistido.
        final_response = client.get(
            f"/status/{job_id}",
        )

        assert final_response.status_code == 200

        result = final_response.json()

        
    assert result["status"] == "completed"

    respuesta = result.get("result")

    assert respuesta, "La tarea terminó sin respuesta."

    # Aceptar tanto respuestas de texto como bloques de contenido.
    if isinstance(respuesta, str):
        texto_respuesta = respuesta
    elif isinstance(respuesta, list):
        textos = [
            bloque["text"]
            for bloque in respuesta
            if isinstance(bloque, dict)
            and bloque.get("type") == "text"
            and isinstance(bloque.get("text"), str)
        ]
        texto_respuesta = "\n".join(textos)
    else:
        pytest.fail(
            f"Formato de respuesta inesperado: "
            f"{type(respuesta).__name__}"
        )

    assert texto_respuesta.strip(), ("La tarea terminó sin una respuesta de texto útil.")
    assert result.get("error") is None

