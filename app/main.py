# FastAPI se encarga de gran parte del manejo de HTTP para que vos puedas concentrarte en la lógica de tu aplicación. 
# Y sí, una diferencia importante con Django es que en FastAPI podés definir endpoints directamente con funciones, 
# sin necesidad de crear una clase para cada vista

# ¿Qué hace FastAPI?
# Cuando llega una petición HTTP, FastAPI se encarga, entre otras cosas, de:
# - Identificar la ruta y el método HTTP (GET, POST, PUT, DELETE, etc.).
# - Extraer y validar los datos de entrada mediante modelos de Pydantic.
# - Ejecutar la función correspondiente.
# - Convertir el resultado en una respuesta HTTP, normalmente JSON.
# - Generar la documentación OpenAPI que Swagger utiliza.

# Redis se usa mucho como caché, pero no es solamente una caché. Es un almacén de datos en memoria que también puede persistir información en disco y 
# que ofrece estructuras de datos como listas, conjuntos, hashes y colas implementadas sobre ellas

# ¿Por qué Redis y no una variable de Python?
# Imaginá que guardás las tareas en una lista de Python dentro de FastAPI. Si el proceso se reinicia, 
# esa información se pierde; además, otro proceso, como tu worker independiente, no podría acceder directamente a esa lista.

# Con Redis, FastAPI y el worker pueden compartir los mismos datos, aunque sean procesos distintos

# En síntesis: en tu arquitectura, Redis funciona como un intermediario compartido entre FastAPI y el worker, 
# almacenando los estados y las tareas pendientes. No lo estás usando principalmente como caché.

import os
import json
import uuid

from fastapi import FastAPI, HTTPException
from redis import asyncio as aioredis

from app.schemas import TaskRequest, TaskResponse, ApprovalRequest
from app.logging_config import logger


REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
QUEUE_NAME = "multiagent_tasks"
STATUS_PREFIX = "task_status:"
APPROVAL_QUEUE = "multiagent_approvals"
APPROVAL_PREFIX = "approval_data:"


app = FastAPI(
    title="Entrega Final - Intelligent System"
)


redis_client = aioredis.from_url(
    REDIS_URL,
    decode_responses=True
)


@app.post("/process", response_model=TaskResponse)
# FAST API VALIDA SEGUN EL ESQUEMA CREADO Y PUEDE CREAR EL JSON
# Cada caja de fast api sera visualizada con el swagger
async def create_task(request: TaskRequest):
    job_id = str(uuid.uuid4())

    task_data = {
        "job_id": job_id,
        "query": request.query,
        "status": "pending",
        "result": None,
        "error": None
    }

    await redis_client.set(
        f"{STATUS_PREFIX}{job_id}",
        json.dumps(task_data)
    )

    await redis_client.rpush(
        QUEUE_NAME,
        job_id
    )

    logger.info(
        "Job %s created and enqueued",
        job_id
    )

    return TaskResponse(
        job_id=job_id,
        status="pending"
    )


@app.get("/status/{job_id}")
async def get_status(job_id: str):
    data = await redis_client.get(
        f"{STATUS_PREFIX}{job_id}"
    )

    if not data:
        raise HTTPException(
            status_code=404,
            detail="Job not found"
        )

    return json.loads(data)


@app.post("/approve/{job_id}")
async def approve_task(
    job_id: str,
    request: ApprovalRequest,
):
    key = f"{STATUS_PREFIX}{job_id}"

    data = await redis_client.get(key)

    if not data:
        logger.warning(
            "Approval request rejected: job %s not found",
            job_id
        )
        raise HTTPException(
            status_code=404,
            detail="Job not found",
        )

    task_data = json.loads(data)

    if task_data["status"] != "waiting_approval":
        logger.warning(
            "Approval request rejected for job %s: status is %s",
            job_id,
            task_data["status"]
        )
        raise HTTPException(
            status_code=400,
            detail="Job is not waiting for approval",
        )
    # approve, reject, failed etc
    approval_data = {
        "decision": request.decision,
        "feedback": request.feedback,
    }

    await redis_client.set(
        f"{APPROVAL_PREFIX}{job_id}",
        json.dumps(approval_data),
    )

    await redis_client.rpush(
        APPROVAL_QUEUE,
        job_id,
    )

    logger.info(
        "Human approval submitted for job %s: decision=%s",
        job_id,
        request.decision
    )

    return {
        "job_id": job_id,
        "status": "approval_submitted",
    }