import asyncio
import json
import os

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.redis.aio import AsyncRedisSaver
from langgraph.types import Command
from redis import asyncio as aioredis

from app.graph_config import grafo
from app.logging_config import logger
from app.observability import configurar_observabilidad
from app.trace_utils import guardar_traza, serializar_traza

# Si la variable no esta disponible, toma la segunda
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

QUEUE_NAME = "multiagent_tasks"
STATUS_PREFIX = "task_status:"

APPROVAL_QUEUE = "multiagent_approvals"
APPROVAL_PREFIX = "approval_data:"

HUMAN_EVENTS_PREFIX = "human_events:"


redis_client = aioredis.from_url(
    REDIS_URL,
    decode_responses=True
)

logger.info("Configurando Phoenix...")
configurar_observabilidad()
logger.info("Phoenix configurado correctamente.")

async def guardar_evento_humano(job_id: str, decision: str, feedback: str):
    """
    Guarda cada intervención humana en Redis.

    Se utiliza una lista para conservar todas las
    intervenciones realizadas durante el workflow.
    """

    evento = {
        "tipo": "HumanApproval",
        "decision": decision,
        "feedback": feedback,
    }

    await redis_client.rpush(
        f"{HUMAN_EVENTS_PREFIX}{job_id}",
        json.dumps(
            evento,
            ensure_ascii=False
        ),
    )


async def obtener_eventos_humanos(job_id: str) -> list[dict]:
    """
    Recupera todas las intervenciones humanas
    registradas para el job.
    """

    raw_events = await redis_client.lrange(
        f"{HUMAN_EVENTS_PREFIX}{job_id}",
        0,
        -1,
    )

    return [
        json.loads(evento)
        for evento in raw_events
    ]

async def procesar_aprobacion(job_id, app):
    key = f"{STATUS_PREFIX}{job_id}"

    raw_data = await redis_client.get(key)

    if not raw_data:
        logger.warning(
            "Approval processing skipped: job %s not found",
            job_id,
        )
        return

    task_data = json.loads(raw_data)

    if task_data["status"] != "waiting_approval":
        logger.warning(
            "Approval processing skipped for job %s: status is %s",
            job_id,
            task_data["status"]
            )
        return

    approval_key = f"{APPROVAL_PREFIX}{job_id}"

    raw_approval = await redis_client.get(
        approval_key
    )

    if not raw_approval:
        logger.warning(
            "Approval processing skipped: no approval data for job %s",
            job_id,
            )
        return

    approval_data = json.loads(raw_approval)

    decision = approval_data["decision"]
    feedback = approval_data["feedback"]

    try:

        logger.info(
            "Human decision received for job %s: decision=%s",
            job_id,
            decision
            )

        await guardar_evento_humano(
            job_id=job_id,
            decision=decision,
            feedback=feedback,
        )

        config = {
            "configurable": {
                "thread_id": job_id
            },
            "recursion_limit": 10,
        }

        resultado = await app.ainvoke(
            Command(
                resume={
                    "decision": decision,
                    "feedback": feedback,
                }
            ),
            config=config,
        )

        if "__interrupt__" in resultado:

            task_data["status"] = "waiting_approval"
            task_data["result"] = None
            task_data["error"] = None

            logger.info("Job %s is waiting for human approval again", job_id,)


        else:

            eventos_humanos = await obtener_eventos_humanos(
                job_id
            )

            traza = serializar_traza(
                resultado["messages"]
            )

            traza.extend(eventos_humanos)

            guardar_traza(
                traza,
                job_id
            )

            response = (
                resultado["messages"][-1].content
            )

            task_data["status"] = "completed"
            task_data["result"] = response
            task_data["error"] = None

            logger.info(
                "Job %s completed successfully after human approval",
                job_id,
            )

            await redis_client.delete(
                f"{HUMAN_EVENTS_PREFIX}{job_id}"
            )

        await redis_client.delete(
            approval_key
        )

    except Exception as e:
        task_data["status"] = "failed"
        task_data["result"] = None
        task_data["error"] = str(e)
        logger.exception(
            "Error processing approval for job %s",
            job_id,
        )

    await redis_client.set(
        key,
        json.dumps(task_data)
    )


async def main_worker():

    logger.info("Worker started and listening for tasks")

    # Redis checkpointer
    async with AsyncRedisSaver.from_conn_string(
        REDIS_URL
    ) as checkpointer:

        app = grafo.compile(
            checkpointer=checkpointer
        )

        while True:

            job_id = await redis_client.lpop(
                QUEUE_NAME
            )

            if job_id is not None:
                logger.info(
                    "Starting processing for job %s",
                    job_id,
                )

                key = f"{STATUS_PREFIX}{job_id}"

                raw_data = await redis_client.get(
                    key
                )

                if not raw_data:

                    logger.warning(
                        "Task skipped: data for job %s not found in Redis",
                        job_id,
                    )

                    continue

                task_data = json.loads(raw_data)

                task_data["status"] = "processing"

                await redis_client.set(
                    key,
                    json.dumps(task_data)
                )

                consulta = task_data["query"]

                config = {
                    "configurable": {
                        "thread_id": job_id
                    },
                    "recursion_limit": 10,
                }

                try:

                    resultado = await app.ainvoke(
                        {
                            "messages": [
                                HumanMessage(
                                    content=consulta
                                )
                            ],
                            "job_id": job_id,
                        },
                        config=config,
                    )

                    if "__interrupt__" in resultado:


                        task_data["status"] = (
                            "waiting_approval"
                        )

                        task_data["result"] = None
                        task_data["error"] = None
                        logger.info(
                            "Job %s is waiting for human approval",
                            job_id,
                        )

                    else:

                        traza = serializar_traza(
                            resultado["messages"]
                        )

                        guardar_traza(
                            traza,
                            job_id,
                        )

                        response = (
                            resultado["messages"][-1]
                            .content
                        )

                        task_data["status"] = (
                            "completed"
                        )

                        task_data["result"] = response
                        task_data["error"] = None

                except Exception as e:
                    task_data["status"] = "failed"
                    task_data["result"] = None
                    task_data["error"] = str(e)

                    logger.exception(
                        "Error processing job %s",
                        job_id,
                    )

                await redis_client.set(
                    key,
                    json.dumps(task_data)
                )

                if task_data["status"] == "completed":
                    logger.info(
                        "Job %s completed successfully",
                        job_id,
                    )
                elif task_data["status"] == "failed":
                    logger.error(
                        "Job %s failed: %s",
                        job_id,
                        task_data["error"],
                    )
                else:
                    logger.info(
                        "Job %s processing finished with status %s",
                        job_id,
                        task_data["status"],
                    )

                continue


            approval_job_id = await redis_client.lpop(
                APPROVAL_QUEUE
            )

            if approval_job_id is not None:
                logger.info(
                    "Resuming job %s after human approval",
                    approval_job_id,
                )

                await procesar_aprobacion(
                    approval_job_id,
                    app
                )

                continue

            await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main_worker())