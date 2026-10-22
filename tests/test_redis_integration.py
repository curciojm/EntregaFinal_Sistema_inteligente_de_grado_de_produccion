import json
import os
import uuid

import httpx
import pytest
import pytest_asyncio
from redis import asyncio as aioredis

import app.main as main

QUEUE_NAME = "multiagent_tasks"
STATUS_PREFIX = "task_status:"
APPROVAL_QUEUE = "multiagent_approvals"
APPROVAL_PREFIX = "approval_data:"

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

@pytest_asyncio.fixture(autouse=True)
async def fresh_app_redis_client(monkeypatch):
    client = aioredis.from_url(
        REDIS_URL,
        decode_responses=True,
    )

    await client.ping()
    monkeypatch.setattr(main, "redis_client", client)

    try:
        yield client
    finally:
        await client.aclose()

@pytest_asyncio.fixture
async def async_client(fresh_app_redis_client):
    transport = httpx.ASGITransport(app=main.app)

    async with httpx.AsyncClient(transport=transport,base_url="http://test") as client:
        yield client

@pytest_asyncio.fixture
async def redis_client():
    """Conecta con Redis real, sin mocks."""
    connection = aioredis.from_url(
        REDIS_URL,
        decode_responses=True,
    )

    try:
        await connection.ping()
    except Exception as exc:
        await connection.aclose()
        pytest.fail(f"No se pudo conectar con Redis en {REDIS_URL}: {exc}")

    try:
        yield connection
    finally:
        await connection.aclose()

@pytest.mark.asyncio
async def test_process_persiste_estado_y_encola_tarea(redis_client,async_client):
    response = await async_client.post(
        "/process",
        json={"query": "Explicá qué es la media."},
    )

    assert response.status_code == 200

    job_id = response.json()["job_id"]
    status_key = f"{STATUS_PREFIX}{job_id}"

    try:
        raw_data = await redis_client.get(status_key)
        assert raw_data is not None

        task_data = json.loads(raw_data)

        assert task_data["job_id"] == job_id
        assert task_data["query"] == "Explicá qué es la media."
        assert task_data["status"] == "pending"
        assert task_data["result"] is None
        assert task_data["error"] is None

        queued_jobs = await redis_client.lrange(
            QUEUE_NAME, 0, -1
        )
        assert job_id in queued_jobs

    finally:
        await redis_client.delete(status_key)
        await redis_client.lrem(QUEUE_NAME, 0, job_id)


@pytest.mark.asyncio
async def test_status_recupera_estado_persistido(redis_client, async_client):
    job_id = f"test-{uuid.uuid4()}"
    status_key = f"{STATUS_PREFIX}{job_id}"

    task_data = {
        "job_id": job_id,
        "query": "Consulta de integración",
        "status": "processing",
        "result": None,
        "error": None,
    }

    await redis_client.set(
        status_key,
        json.dumps(task_data),
    )

    try:
        response = await async_client.get(f"/status/{job_id}")

        assert response.status_code == 200
        assert response.json() == task_data

    finally:
        await redis_client.delete(status_key)

@pytest.mark.asyncio
async def test_status_devuelve_404_para_job_inexistente(
    redis_client,
    async_client,
):
    job_id = f"missing-{uuid.uuid4()}"
    status_key = f"{STATUS_PREFIX}{job_id}"

    await redis_client.delete(status_key)

    response = await async_client.get(f"/status/{job_id}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Job not found"

@pytest.mark.asyncio
async def test_approve_rechaza_tarea_que_no_espera_aprobacion(redis_client, async_client):
    job_id = f"test-{uuid.uuid4()}"
    status_key = f"{STATUS_PREFIX}{job_id}"
    approval_key = f"{APPROVAL_PREFIX}{job_id}"

    task_data = {
        "job_id": job_id,
        "query": "Consulta de integración",
        "status": "pending",
        "result": None,
        "error": None,
    }

    await redis_client.set(
        status_key,
        json.dumps(task_data),
    )

    try:
        response = await async_client.post(
            f"/approve/{job_id}",
            json={
                "decision": "approve",
                "feedback": "La respuesta es correcta.",
            },
        )

        assert response.status_code == 400
        assert response.json()["detail"] == ("Job is not waiting for approval")

        assert await redis_client.get(approval_key) is None

        queued_approvals = await redis_client.lrange(
            APPROVAL_QUEUE,
            0,
            -1,
        )
        assert job_id not in queued_approvals

    finally:
        await redis_client.delete(status_key, approval_key)
        await redis_client.lrem(APPROVAL_QUEUE, 0, job_id)


@pytest.mark.asyncio
async def test_approve_devuelve_404_para_job_inexistente(redis_client, async_client):
    job_id = f"missing-{uuid.uuid4()}"
    status_key = f"{STATUS_PREFIX}{job_id}"
    approval_key = f"{APPROVAL_PREFIX}{job_id}"

    await redis_client.delete(status_key, approval_key)

    try:
        response = await async_client.post(
            f"/approve/{job_id}",
            json={
                "decision": "approve",
                "feedback": "La respuesta es correcta.",
            },
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "Job not found"

        assert await redis_client.get(approval_key) is None

        queued_approvals = await redis_client.lrange(
            APPROVAL_QUEUE,
            0,
            -1,
        )
        assert job_id not in queued_approvals

    finally:
        await redis_client.delete(status_key, approval_key)
        await redis_client.lrem(APPROVAL_QUEUE, 0, job_id)

@pytest.mark.asyncio
async def test_process_rechaza_request_invalido_sin_crear_tarea(redis_client, async_client):
    initial_queue_length = await redis_client.llen(QUEUE_NAME)

    initial_status_keys = set(
        await redis_client.keys(f"{STATUS_PREFIX}*")
    )

    response = await async_client.post("/process", json={})

    assert response.status_code == 422

    final_queue_length = await redis_client.llen(QUEUE_NAME)
    final_status_keys = set(
        await redis_client.keys(f"{STATUS_PREFIX}*")
    )

    assert final_queue_length == initial_queue_length
    assert final_status_keys == initial_status_keys