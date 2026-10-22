
import time

import httpx
import pytest


BASE_URL = "http://127.0.0.1:8000"
TIMEOUT_SECONDS = 180
POLL_INTERVAL_SECONDS = 2


@pytest.mark.e2e
def test_evaluacion_con_aprobacion_humana():
    """
    Comprueba el recorrido real:
    solicitud -> supervisor -> aprobación humana -> evaluador.
    Requiere API, worker, Redis, Pinecone y proveedores LLM activos.
    """

    consulta = """
    Quiero que evalúes la siguiente respuesta de un estudiante.

    Pregunta: ¿Qué es la correlación?

    Respuesta del estudiante:
    "La correlacion consiste en el calculo de un promedio entre dos grupos distintos "
    "para ver que grupo tiene mayor promedio"

    Indicá si la respuesta es correcta y justificá brevemente
    la evaluación.
    """

    response = httpx.post(
        f"{BASE_URL}/process",
        json={"query": consulta},
        timeout=15,
    )
    response.raise_for_status()

    job_id = response.json()["job_id"]
    assert job_id

    deadline = time.monotonic() + TIMEOUT_SECONDS
    estado = None
    aprobaciones_enviadas = 0

    while time.monotonic() < deadline:
        response = httpx.get(
            f"{BASE_URL}/status/{job_id}",
            timeout=15,
        )
        response.raise_for_status()
        tarea = response.json()
        estado = tarea["status"]

        if estado == "waiting_approval":
            response = httpx.post(
                f"{BASE_URL}/approve/{job_id}",
                json={
                    "decision": "approve",
                    "feedback": (
                        "Continuá con la evaluación de la respuesta "
                        "agrega un ejemplo que involucre niveles de ansiedad y frecuencia de palabras recordadas"
                    ),
                },
                timeout=15,
            )
            response.raise_for_status()
            aprobaciones_enviadas += 1

        elif estado == "completed":
            break

        elif estado == "failed":
            pytest.fail(
                f"La tarea falló. Detalle: {tarea.get('error')}"
            )

        time.sleep(POLL_INTERVAL_SECONDS)

    assert estado == "completed", (
        f"La tarea no terminó dentro de {TIMEOUT_SECONDS} segundos. "
        f"Último estado: {estado}"
    )

    assert aprobaciones_enviadas >= 1, ("La tarea terminó sin pasar por la aprobación humana.")

    resultado = tarea.get("result")
    assert resultado, "La tarea terminó sin resultado."

    if isinstance(resultado, str):
        texto_resultado = resultado
    else:
        texto_resultado = str(resultado)

    assert "Evaluación:" in texto_resultado, (
        "El resultado final no contiene la clasificación esperada. "
        f"Resultado recibido: {texto_resultado}"
    )
