import os
import json
import uuid

from fastapi import FastAPI, HTTPException
from redis import asyncio as aioredis

from app.schemas import TaskRequest, TaskResponse, ApprovalRequest

# Si la variable no esta disponible, toma la segunda
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
QUEUE_NAME = "multiagent_tasks"
STATUS_PREFIX = "task_status:"
APPROVAL_QUEUE = "multiagent_approvals"
APPROVAL_PREFIX = "approval_data:"


app = FastAPI(
    title="Entrega Final - Inteligent System"
)


redis_client = aioredis.from_url(
    REDIS_URL,
    decode_responses=True
)

@app.post("/process", response_model=TaskResponse)
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
        raise HTTPException(
            status_code=404,
            detail="Job not found",
        )

    task_data = json.loads(data)

    if task_data["status"] != "waiting_approval":
        raise HTTPException(
            status_code=400,
            detail="Job is not waiting for approval",
        )

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

    return {
        "job_id": job_id,
        "status": "approval_submitted",
    }