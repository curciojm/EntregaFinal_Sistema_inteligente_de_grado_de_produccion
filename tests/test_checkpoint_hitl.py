
import os
from uuid import uuid4

import pytest
from dotenv import load_dotenv
from langgraph.checkpoint.redis.aio import AsyncRedisSaver
from langgraph.types import Command

from app.graph_config import grafo

load_dotenv()

REDIS_URL = os.getenv(
    "REDIS_URL",
    "redis://localhost:6379",
)

@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.e2e
async def test_checkpoint_hitl_se_reanuda_tras_reabrir_checkpointer():
    thread_id = f"test-hitl-{uuid4()}"
    config = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": 10,
    }

    async with AsyncRedisSaver.from_conn_string(REDIS_URL) as checkpointer:
        app = grafo.compile(checkpointer=checkpointer)

        # El grafo debe interrumpirse esperando aprobación humana.
        resultado = await app.ainvoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "Evaluá mi respuesta sobre la media: "
                            "es la suma de los valores dividida "
                            "por la cantidad de observaciones."
                        ),
                    }
                ],
                "job_id": thread_id,
                "revision_humana": True,
            },
            config=config,
        )

        assert resultado.get("__interrupt__"), ("El grafo no quedó interrumpido como se esperaba.")

        estado = await app.aget_state(config)
        assert estado.next, "El checkpoint no indica nodos pendientes."

    async with AsyncRedisSaver.from_conn_string(REDIS_URL) as checkpointer:
        app = grafo.compile(checkpointer=checkpointer)

        estado_recuperado = await app.aget_state(config)

        assert estado_recuperado.next, ("No se recuperaron los nodos pendientes.")

        # Reanudar con una aprobación humana.
        resultado_final = await app.ainvoke(
            Command(
                resume={
                    "decision": "approve",
                    "feedback": "Aprobación de prueba.",
                }
            ),
            config=config,
        )

        assert not resultado_final.get("__interrupt__"), ("El grafo volvió a interrumpirse.")

        estado_final = await app.aget_state(config)
        assert not estado_final.next, ("El grafo no terminó después de la aprobación.")
