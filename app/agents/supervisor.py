from app.errors import classify_error
from app.logging_config import logger
from app.models import get_model
from app.schemas import AgentState, DecisionSupervisor

MAX_PASOS = 6

SUPERVISOR_PROMPT = """Sos el Supervisor de un equipo con dos especialistas:

- agente_profesor: responde consultas conceptuales del usuario y, si el usuario lo solicita,
  puede indicar las fuentes utilizadas.
- agente_evaluador: evalúa si el concepto explicado por el usuario es correcto y,
  cuando corresponda, indica qué información debería estudiar y dónde encontrarla
  en las fuentes recuperadas.

Reglas:

1. Si el usuario realiza una consulta conceptual, utilizá "profesor".

2. Si el usuario proporciona una respuesta propia y solicita o requiere
   una evaluación de su conocimiento, utilizá "evaluador".

3. Si "profesor" ya respondió una consulta conceptual de manera suficiente,
   seleccioná "FINISH". No envíes esa respuesta al "evaluador".

4. Si "evaluador" ya evaluó una respuesta del usuario, seleccioná "FINISH".

5. No utilices "evaluador" para evaluar la respuesta generada por "profesor".

6. Si la tarea ya fue resuelta por el especialista correspondiente,
   seleccioná "FINISH".

7. Antes de seleccionar "FINISH", verificá que el aporte del especialista
   sea suficiente para responder la solicitud original. Si falta información
   relevante, seleccioná el especialista correspondiente.

8. No repitas innecesariamente el mismo agente si ya cumplió su función.

Contribuciones hasta ahora:
{contribuciones}
"""


async def nodo_supervisor(state: AgentState) -> dict:

    if state.get("pasos", 0) >= MAX_PASOS:
        return {
            "next_agent": "FINISH",
            "task_completed": True,
        }

    contribuciones_texto = "\n".join(
        f"- {c['agente']}: {c['aporte'][:500]}"
        for c in state.get("contribuciones", [])
    ) or "(ninguna todavía)"

    pregunta_actual = state["messages"][-1].content

    prompt_sistema = SUPERVISOR_PROMPT.format(
        contribuciones=contribuciones_texto
    )

    messages = [
        {
            "role": "system",
            "content": prompt_sistema,
        },
        {
            "role": "user",
            "content": f"Tarea actual: {pregunta_actual}",
        },
    ]

    last_error = None

    for provider in ["openai", "anthropic", "gemini"]:
        try:
            logger.info(
                "Intentando utilizar proveedor LLM para supervisor: %s",
                provider,
            )

            llm = get_model(provider)

            llm_supervisor = llm.with_structured_output(
                DecisionSupervisor
            )

            decision = await llm_supervisor.ainvoke(messages)

            logger.info(
                "Proveedor LLM utilizado correctamente: %s",
                provider,
            )

            return {
                "next_agent": decision.next,
                "task_completed": decision.next == "FINISH",
            }

        except Exception as e:
            last_error = e

            error = classify_error(e)

            logger.warning(
                "El proveedor %s falló: %s",
                provider,
                error.message,
            )

            continue

    logger.error("Todos los proveedores LLM fallaron")

    raise classify_error(last_error)