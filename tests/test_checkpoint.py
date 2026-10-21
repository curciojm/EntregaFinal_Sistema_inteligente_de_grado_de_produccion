
import os
from uuid import uuid4

import pytest
import pytest_asyncio
from dotenv import load_dotenv
from langgraph.checkpoint.redis.aio import AsyncRedisSaver
from langgraph.graph import END, START, StateGraph
from redis import asyncio as aioredis
from typing_extensions import TypedDict

load_dotenv()

REDIS_URL = os.getenv(
    "REDIS_URL",
    "redis://localhost:6379",
)


class CheckpointState(TypedDict):
    mensaje: str


@pytest_asyncio.fixture
async def redis_client():
    """Conecta con Redis real para la prueba de integración."""
    client = aioredis.from_url(
        REDIS_URL,
        decode_responses=True,
    )

    try:
        await client.ping()
        yield client
    except Exception as exc:
        pytest.fail(
            f"No se pudo conectar con Redis en {REDIS_URL}: {exc}"
        )
    finally:
        await client.aclose()


def crear_grafo():
    """Crea un grafo mínimo para probar la persistencia."""

    builder = StateGraph(CheckpointState)

    def guardar_mensaje(state: CheckpointState):
        return {"mensaje": state["mensaje"]}

    builder.add_node("guardar", guardar_mensaje)
    builder.add_edge(START, "guardar")
    builder.add_edge("guardar", END)

    return builder


@pytest.mark.asyncio
@pytest.mark.integration
async def test_checkpoint_persiste_tras_reabrir_checkpointer(
    redis_client,
):
    thread_id = f"test-checkpoint-{uuid4()}"
    config = {
        "configurable": {
            "thread_id": thread_id,
        }
    }

    builder = crear_grafo()

    # Primera instancia: ejecuta el grafo y guarda el checkpoint.
    async with AsyncRedisSaver.from_conn_string(
        REDIS_URL
    ) as checkpointer:
        app = builder.compile(checkpointer=checkpointer)

        await app.ainvoke(
            {"mensaje": "estado persistido en Redis"},
            config=config,
        )

        estado = await app.aget_state(config)

        assert estado.values["mensaje"] == (
            "estado persistido en Redis"
        )

    # Segunda instancia: simula la reapertura del Checkpointer.
    async with AsyncRedisSaver.from_conn_string(
        REDIS_URL
    ) as checkpointer:
        app = builder.compile(checkpointer=checkpointer)

        estado_recuperado = await app.aget_state(config)

        assert estado_recuperado.values["mensaje"] == (
            "estado persistido en Redis"
        )
        assert (
            estado_recuperado.config["configurable"]["thread_id"]
            == thread_id
        )
        assert estado_recuperado.created_at is not None
