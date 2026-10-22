import json
from unittest.mock import AsyncMock, patch
from langchain_core.messages import HumanMessage
from app.worker import main_worker

import pytest

from app.worker import procesar_aprobacion


@pytest.mark.asyncio
async def test_procesar_aprobacion_marca_failed_si_falla_el_grafo():

    job_id = "test-job-123"

    task_data = {
        "job_id": job_id,
        "query": "Evaluar una respuesta sobre la media.",
        "status": "waiting_approval",
        "result": None,
        "error": None,
    }

    approval_data = {
        "decision": "approve",
        "feedback": "",
    }

    fake_redis = AsyncMock()

    fake_redis.get.side_effect = [
        json.dumps(task_data),
        json.dumps(approval_data),
    ]

    fake_app = AsyncMock()
    fake_app.ainvoke.side_effect = Exception(
        "Error simulado del grafo"
    )

    with patch(
        "app.worker.redis_client",
        fake_redis,
    ):
        await procesar_aprobacion(
            job_id,
            fake_app,
        )

    llamadas_set = fake_redis.set.await_args_list

    ultima_llamada = llamadas_set[-1]

    key_guardada = ultima_llamada.args[0]
    datos_guardados = json.loads(
        ultima_llamada.args[1]
    )

    assert key_guardada == f"task_status:{job_id}"
    assert datos_guardados["status"] == "failed"
    assert datos_guardados["result"] is None
    assert datos_guardados["error"] == "Error simulado del grafo"

    fake_app.ainvoke.assert_awaited_once()

@pytest.mark.asyncio
async def test_main_worker_completa_tarea_exitosamente():

    job_id = "test-job-success"

    task_data = {
        "job_id": job_id,
        "query": "Explicá qué es la media.",
        "status": "pending",
        "result": None,
        "error": None,
    }

    respuesta = "La media es el promedio aritmético."


    fake_redis = AsyncMock()
    fake_redis.lpop.side_effect = [
        job_id,
        None,
        None,
    ]
    fake_redis.get.return_value = json.dumps(task_data)

    # Simula el grafo compilado.
    fake_app = AsyncMock()
    fake_app.ainvoke.return_value = {
        "messages": [
            HumanMessage(content=respuesta)
        ]
    }

    fake_grafo = type(
        "FakeGraph",
        (),
        {"compile": lambda self, checkpointer: fake_app},
    )()

    class FakeSaver:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    class StopWorker(Exception):
        pass

    with (
        patch("app.worker.redis_client", fake_redis),
        patch("app.worker.grafo", fake_grafo),
        patch(
            "app.worker.AsyncRedisSaver.from_conn_string",
            return_value=FakeSaver(),
        ),
        patch("app.worker.serializar_traza", return_value=[]),
        patch("app.worker.guardar_traza"),
        patch(
            "app.worker.asyncio.sleep",
            side_effect=StopWorker,
        ),
    ):
        with pytest.raises(StopWorker):
            await main_worker()

    fake_app.ainvoke.assert_awaited_once()

    assert fake_redis.set.await_count == 2

    ultimo_set = fake_redis.set.await_args_list[-1]
    key_guardada = ultimo_set.args[0]
    estado_final = json.loads(ultimo_set.args[1])

    assert key_guardada == f"task_status:{job_id}"
    assert estado_final["status"] == "completed"
    assert estado_final["result"] == respuesta
    assert estado_final["error"] is None

@pytest.mark.asyncio
async def test_main_worker_deja_tarea_esperando_aprobacion():

    job_id = "test-job-approval"

    task_data = {
        "job_id": job_id,
        "query": "Evaluá mi respuesta sobre la media.",
        "status": "pending",
        "result": None,
        "error": None,
    }

    fake_redis = AsyncMock()
    fake_redis.lpop.side_effect = [
        job_id,
        None,
        None,
    ]
    fake_redis.get.return_value = json.dumps(task_data)

    fake_app = AsyncMock()
    fake_app.ainvoke.return_value = {
        "__interrupt__": ["Esperando aprobación humana"]
    }

    fake_grafo = type(
        "FakeGraph",
        (),
        {"compile": lambda self, checkpointer: fake_app},
    )()

    class FakeSaver:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    class StopWorker(Exception):
        pass

    with (
        patch("app.worker.redis_client", fake_redis),
        patch("app.worker.grafo", fake_grafo),
        patch(
            "app.worker.AsyncRedisSaver.from_conn_string",
            return_value=FakeSaver(),
        ),
        patch("app.worker.asyncio.sleep", side_effect=StopWorker),
    ):
        with pytest.raises(StopWorker):
            await main_worker()

    fake_app.ainvoke.assert_awaited_once()

    ultimo_set = fake_redis.set.await_args_list[-1]
    estado_final = json.loads(ultimo_set.args[1])

    assert estado_final["status"] == "waiting_approval"
    assert estado_final["result"] is None
    assert estado_final["error"] is None

@pytest.mark.asyncio
async def test_procesar_aprobacion_completa_tarea_exitosamente():

    job_id = "test-job-approved"

    task_data = {
        "job_id": job_id,
        "query": "Evaluar una respuesta sobre la media.",
        "status": "waiting_approval",
        "result": None,
        "error": None,
    }

    approval_data = {
        "decision": "approve",
        "feedback": "La respuesta es correcta.",
    }

    fake_redis = AsyncMock()

    fake_redis.get.side_effect = [
        json.dumps(task_data),
        json.dumps(approval_data),
    ]

    respuesta = "La media es el promedio aritmético."

    fake_app = AsyncMock()
    fake_app.ainvoke.return_value = {
        "messages": [
            HumanMessage(content=respuesta)
        ]
    }

    with (
        patch("app.worker.redis_client", fake_redis),
        patch(
            "app.worker.guardar_evento_humano",
            new_callable=AsyncMock,
        ) as guardar_evento,
        patch(
            "app.worker.obtener_eventos_humanos",
            new_callable=AsyncMock,
            return_value=[
                {
                    "tipo": "HumanApproval",
                    "decision": "approve",
                    "feedback": "La respuesta es correcta.",
                }
            ],
        ),
        patch("app.worker.serializar_traza", return_value=[]),
        patch("app.worker.guardar_traza") as guardar_traza,
    ):
        await procesar_aprobacion(job_id, fake_app)

    guardar_evento.assert_awaited_once_with(
        job_id=job_id,
        decision="approve",
        feedback="La respuesta es correcta.",
    )

    fake_app.ainvoke.assert_awaited_once()

    args, kwargs = fake_app.ainvoke.await_args

    assert args[0].resume == {
        "decision": "approve",
        "feedback": "La respuesta es correcta.",
    }
    assert kwargs["config"]["configurable"]["thread_id"] == job_id

    guardar_traza.assert_called_once()

    ultimo_set = fake_redis.set.await_args_list[-1]
    estado_final = json.loads(ultimo_set.args[1])

    assert ultimo_set.args[0] == f"task_status:{job_id}"
    assert estado_final["status"] == "completed"
    assert estado_final["result"] == respuesta
    assert estado_final["error"] is None


    fake_redis.delete.assert_any_await(f"approval_data:{job_id}")
    fake_redis.delete.assert_any_await(f"human_events:{job_id}")

@pytest.mark.asyncio
async def test_procesar_aprobacion_no_hace_nada_si_job_no_existe():

    job_id = "job-inexistente"

    fake_redis = AsyncMock()
    fake_redis.get.return_value = None

    fake_app = AsyncMock()

    with patch("app.worker.redis_client", fake_redis):
        await procesar_aprobacion(job_id, fake_app)

    fake_redis.get.assert_awaited_once_with(
        f"task_status:{job_id}"
    )

    fake_app.ainvoke.assert_not_awaited()
    fake_redis.set.assert_not_awaited()

@pytest.mark.asyncio
async def test_procesar_aprobacion_no_hace_nada_si_no_hay_aprobacion():

    job_id = "test-job-sin-aprobacion"

    task_data = {
        "job_id": job_id,
        "query": "Explicá la media.",
        "status": "waiting_approval",
        "result": None,
        "error": None,
    }

    fake_redis = AsyncMock()
    fake_redis.get.side_effect = [
        json.dumps(task_data),
        None,
    ]

    fake_app = AsyncMock()

    with patch("app.worker.redis_client", fake_redis):
        await procesar_aprobacion(job_id, fake_app)

    assert fake_redis.get.await_count == 2

    fake_app.ainvoke.assert_not_awaited()
    fake_redis.set.assert_not_awaited()


@pytest.mark.asyncio
async def test_procesar_aprobacion_vuelve_a_esperar_aprobacion():

    job_id = "test-job-segunda-aprobacion"

    task_data = {
        "job_id": job_id,
        "query": "Evaluar una respuesta sobre la media.",
        "status": "waiting_approval",
        "result": None,
        "error": None,
    }

    approval_data = {
        "decision": "reject",
        "feedback": "La respuesta necesita una corrección.",
    }

    fake_redis = AsyncMock()

    fake_redis.get.side_effect = [
        json.dumps(task_data),
        json.dumps(approval_data),
    ]

    # Simulamos que el grafo vuelve a interrumpirse.
    fake_app = AsyncMock()
    fake_app.ainvoke.return_value = {
        "__interrupt__": ["Se necesita otra aprobación"]
    }

    with (
        patch("app.worker.redis_client", fake_redis),
        patch(
            "app.worker.guardar_evento_humano",
            new_callable=AsyncMock,
        ) as guardar_evento,
    ):
        await procesar_aprobacion(job_id, fake_app)

    guardar_evento.assert_awaited_once_with(
        job_id=job_id,
        decision="reject",
        feedback="La respuesta necesita una corrección.",
    )

    ultimo_set = fake_redis.set.await_args_list[-1]
    estado_final = json.loads(ultimo_set.args[1])

    assert ultimo_set.args[0] == f"task_status:{job_id}"
    assert estado_final["status"] == "waiting_approval"
    assert estado_final["result"] is None
    assert estado_final["error"] is None

    fake_redis.delete.assert_awaited_once_with(f"approval_data:{job_id}")

    fake_app.ainvoke.assert_awaited_once()


@pytest.mark.asyncio
async def test_procesar_aprobacion_falla_si_no_puede_guardar_evento_humano():

    job_id = "test-job-error-evento"

    task_data = {
        "job_id": job_id,
        "query": "Evaluar una respuesta sobre la media.",
        "status": "waiting_approval",
        "result": None,
        "error": None,
    }

    approval_data = {
        "decision": "approve",
        "feedback": "La respuesta es correcta.",
    }

    fake_redis = AsyncMock()
    fake_redis.get.side_effect = [
        json.dumps(task_data),
        json.dumps(approval_data),
    ]

    fake_app = AsyncMock()

    with (
        patch("app.worker.redis_client", fake_redis),
        patch(
            "app.worker.guardar_evento_humano",
            new_callable=AsyncMock,
            side_effect=ConnectionError("Redis no disponible"),
        ) as guardar_evento,
    ):
        await procesar_aprobacion(job_id, fake_app)

    guardar_evento.assert_awaited_once_with(
        job_id=job_id,
        decision="approve",
        feedback="La respuesta es correcta.",
    )

    ultimo_set = fake_redis.set.await_args_list[-1]
    estado_final = json.loads(ultimo_set.args[1])

    assert ultimo_set.args[0] == f"task_status:{job_id}"
    assert estado_final["status"] == "failed"
    assert estado_final["result"] is None
    assert estado_final["error"] == "Redis no disponible"

    fake_app.ainvoke.assert_not_awaited()

    fake_redis.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_main_worker_marca_failed_si_falla_el_grafo():

    job_id = "test-job-worker-error"

    task_data = {
        "job_id": job_id,
        "query": "Explicá qué es la media.",
        "status": "pending",
        "result": None,
        "error": None,
    }

    fake_redis = AsyncMock()
    fake_redis.lpop.side_effect = [
        job_id,
        None,
        None,
    ]
    fake_redis.get.return_value = json.dumps(task_data)

    fake_app = AsyncMock()
    fake_app.ainvoke.side_effect = Exception(
        "Error simulado del grafo"
    )

    fake_grafo = type(
        "FakeGraph",
        (),
        {"compile": lambda self, checkpointer: fake_app},
    )()

    class FakeSaver:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    class StopWorker(Exception):
        pass

    with (
        patch("app.worker.redis_client", fake_redis),
        patch("app.worker.grafo", fake_grafo),
        patch(
            "app.worker.AsyncRedisSaver.from_conn_string",
            return_value=FakeSaver(),
        ),
        patch(
            "app.worker.asyncio.sleep",
            side_effect=StopWorker,
        ),
    ):
        with pytest.raises(StopWorker):
            await main_worker()

    fake_app.ainvoke.assert_awaited_once()

    assert fake_redis.set.await_count == 2

    ultimo_set = fake_redis.set.await_args_list[-1]
    estado_final = json.loads(ultimo_set.args[1])

    assert ultimo_set.args[0] == f"task_status:{job_id}"
    assert estado_final["status"] == "failed"
    assert estado_final["result"] is None
    assert estado_final["error"] == "Error simulado del grafo"


@pytest.mark.asyncio
async def test_main_worker_ignora_tarea_que_no_existe_en_redis():

    job_id = "test-job-inexistente"

    fake_redis = AsyncMock()
    fake_redis.lpop.side_effect = [
        job_id,
        None, 
        None,
    ]
    fake_redis.get.return_value = None

    fake_app = AsyncMock()

    fake_grafo = type(
        "FakeGraph",
        (),
        {"compile": lambda self, checkpointer: fake_app},
    )()

    class FakeSaver:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    class StopWorker(Exception):
        pass

    with (
        patch("app.worker.redis_client", fake_redis),
        patch("app.worker.grafo", fake_grafo),
        patch(
            "app.worker.AsyncRedisSaver.from_conn_string",
            return_value=FakeSaver(),
        ),
        patch(
            "app.worker.asyncio.sleep",
            side_effect=StopWorker,
        ),
    ):
        with pytest.raises(StopWorker):
            await main_worker()

    fake_redis.get.assert_awaited_once_with(f"task_status:{job_id}")

    fake_app.ainvoke.assert_not_awaited()
    fake_redis.set.assert_not_awaited()


@pytest.mark.asyncio
async def test_main_worker_ignora_aprobacion_de_job_inexistente():

    job_id = "test-approval-job-inexistente"

    fake_redis = AsyncMock()

    fake_redis.lpop.side_effect = [
        None,
        job_id,
        None,
        None,
    ]

    fake_redis.get.return_value = None

    fake_app = AsyncMock()

    fake_grafo = type(
        "FakeGraph",
        (),
        {"compile": lambda self, checkpointer: fake_app},
    )()

    class FakeSaver:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    class StopWorker(Exception):
        pass

    with (
        patch("app.worker.redis_client", fake_redis),
        patch("app.worker.grafo", fake_grafo),
        patch(
            "app.worker.AsyncRedisSaver.from_conn_string",
            return_value=FakeSaver(),
        ),
        patch(
            "app.worker.asyncio.sleep",
            side_effect=StopWorker,
        ),
    ):
        with pytest.raises(StopWorker):
            await main_worker()

    fake_redis.get.assert_awaited_once_with(f"task_status:{job_id}")

    fake_app.ainvoke.assert_not_awaited()
    fake_redis.set.assert_not_awaited()
