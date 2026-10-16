import json
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_create_task():
    fake_redis = AsyncMock()

    with patch("app.main.redis_client", fake_redis):
        response = client.post(
            "/process",
            json={
                "query": "Explicá qué es la media."
            },
        )

    assert response.status_code == 200

    data = response.json()

    assert "job_id" in data
    assert data["status"] == "pending"

    fake_redis.set.assert_awaited_once()
    fake_redis.rpush.assert_awaited_once()

    # Verificar que se encoló el job en la cola correcta
    args = fake_redis.rpush.await_args.args

    assert args[0] == "multiagent_tasks"
    assert args[1] == data["job_id"]

    # Verificar que se guardó el estado inicial
    set_args = fake_redis.set.await_args.args

    assert set_args[0].startswith("task_status:")

    task_data = json.loads(set_args[1])

    assert task_data["job_id"] == data["job_id"]
    assert task_data["query"] == "Explicá qué es la media."
    assert task_data["status"] == "pending"

def test_get_status_devuelve_tarea_existente():
    job_id = "test-job-123"

    task_data = {
        "job_id": job_id,
        "query": "Explicá qué es la media.",
        "status": "processing",
        "result": None,
        "error": None,
    }

    fake_redis = AsyncMock()
    fake_redis.get.return_value = json.dumps(task_data)

    with patch("app.main.redis_client", fake_redis):
        response = client.get(f"/status/{job_id}")

    assert response.status_code == 200
    assert response.json() == task_data

    fake_redis.get.assert_awaited_once_with(
        f"task_status:{job_id}"
    )


def test_get_status_devuelve_404_si_no_existe():
    job_id = "job-inexistente"

    fake_redis = AsyncMock()
    fake_redis.get.return_value = None

    with patch("app.main.redis_client", fake_redis):
        response = client.get(f"/status/{job_id}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Job not found"


def test_approve_task_encola_aprobacion_valida():
    job_id = "test-job-123"

    task_data = {
        "job_id": job_id,
        "query": "Explicá qué es la media.",
        "status": "waiting_approval",
        "result": None,
        "error": None,
    }

    fake_redis = AsyncMock()
    fake_redis.get.return_value = json.dumps(task_data)

    with patch("app.main.redis_client", fake_redis):
        response = client.post(
            f"/approve/{job_id}",
            json={
                "decision": "approve",
                "feedback": "La respuesta es correcta.",
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "job_id": job_id,
        "status": "approval_submitted",
    }

    # Verifica que se guardó la decisión.
    fake_redis.set.assert_awaited_once()

    set_args = fake_redis.set.await_args.args

    assert set_args[0] == f"approval_data:{job_id}"

    approval_data = json.loads(set_args[1])

    assert approval_data == {
        "decision": "approve",
        "feedback": "La respuesta es correcta.",
    }

    # Verifica que se encoló la aprobación.
    fake_redis.rpush.assert_awaited_once_with(
        "multiagent_approvals",
        job_id,
    )


def test_approve_task_rechaza_tarea_que_no_espera_aprobacion():
    job_id = "test-job-123"

    task_data = {
        "job_id": job_id,
        "query": "Explicá qué es la media.",
        "status": "processing",
        "result": None,
        "error": None,
    }

    fake_redis = AsyncMock()
    fake_redis.get.return_value = json.dumps(task_data)

    with patch("app.main.redis_client", fake_redis):
        response = client.post(
            f"/approve/{job_id}",
            json={
                "decision": "approve",
                "feedback": "",
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "Job is not waiting for approval"
    )

    # No debe registrar ni encolar la aprobación.
    fake_redis.set.assert_not_awaited()
    fake_redis.rpush.assert_not_awaited()