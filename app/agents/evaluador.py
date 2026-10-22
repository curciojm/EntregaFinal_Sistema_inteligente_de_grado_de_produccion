from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage

from app.errors import classify_error
from app.logging_config import logger
from app.models import get_model
from app.schemas import AgentState
from app.tools import buscar_concepto, buscar_fuente, evaluar_concepto

EVALUADOR_PROMPT = """
Sos un agente especializado en evaluar respuestas de estudiantes
sobre conceptos de metodología de la investigación y estadística.

TU TAREA PRINCIPAL:

Evaluá la explicación del estudiante utilizando las herramientas
disponibles y construí una respuesta final dirigida al estudiante.

FLUJO OBLIGATORIO:

1. Primero utilizá 'evaluar_concepto' para evaluar la respuesta
   del usuario.

2. Conservá el resultado obtenido de 'evaluar_concepto'.
   Las categorías posibles son exactamente:
   "Mal", "Incompleta", "Bien" y "Muy bien".

3. Si la evaluación es "Mal", "Incompleta" o "Bien",
   utilizá 'buscar_fuente' para localizar dónde puede estudiar
   el concepto o la información que necesita.

4. Si necesitás explicar cuál sería la formulación correcta o
   qué información conceptual falta, utilizá 'buscar_concepto'.

5. No utilices una herramienta si la información disponible
   ya es suficiente para construir la respuesta.

RESPUESTA FINAL:

La respuesta final debe integrar la información obtenida de las
herramientas y estar dirigida al estudiante.

La primera línea de la respuesta debe indicar siempre,
explícitamente, la evaluación obtenida mediante 'evaluar_concepto',
utilizando exactamente una de estas categorías:

Evaluación: Mal
Evaluación: Incompleta
Evaluación: Bien
Evaluación: Muy bien

Después de indicar la evaluación:

- Explicá qué está correcto o incorrecto en la respuesta del estudiante.
- Indicá qué debería mejorar o cuál sería una formulación correcta.
- Cuando corresponda, incluí la fuente y las páginas obtenidas mediante
  'buscar_fuente'.
- Si utilizaste 'buscar_concepto', integrá esa información en la
  explicación.

REGLAS IMPORTANTES:

- Nunca reemplaces la evaluación obtenida mediante 'evaluar_concepto'
  por el resultado de otra herramienta.
- Nunca respondas únicamente con el resultado de 'buscar_fuente'
  o 'buscar_concepto'.
- No modifiques ni inventes la categoría devuelta por
  'evaluar_concepto'.
- No inventes fuentes, páginas ni información bibliográfica.
- Si la evaluación es "Mal", indicá claramente que la respuesta
  no responde correctamente al concepto evaluado.
- Si la evaluación es "Incompleta", indicá qué elementos conceptuales
  faltan para completar la explicación.
- Si la evaluación es "Bien", indicá qué aspectos son correctos y
  qué podría agregarse o precisarse.
- Si la evaluación es "Muy bien", indicá que la explicación es
  adecuada y señalá únicamente mejoras menores si corresponden.
- Si no hay información suficiente para evaluar la respuesta,
  indicálo claramente.

REGLAS DE USO DE HERRAMIENTAS:

- Utilizá una sola herramienta por vez.
- Esperá el resultado de una herramienta antes de solicitar otra.
- No solicites llamadas simultáneas a distintas herramientas.
- No llames a 'buscar_concepto' más de una vez durante la misma ejecución.
- Utilizá la información obtenida de una herramienta antes de
  realizar otra consulta.

REVISIÓN HUMANA:

Si la tarea contiene una revisión o feedback proporcionado por un supervisor humano:

- Considerá el feedback como información adicional para reconsiderar la evaluación.
- Volvé a evaluar la respuesta del estudiante utilizando 'evaluar_concepto'.
- No asumas que la categoría sugerida implícitamente por el feedback es necesariamente correcta.
- La evaluación final debe ser siempre la categoría devuelta por 'evaluar_concepto'.
- Utilizá el feedback humano para identificar aspectos de la respuesta que deban revisarse.
"""

async def nodo_evaluador(state: AgentState) -> dict:

    tarea = state["messages"][-1].content

    feedback = state.get("feedback_humano")

    if feedback:
        tarea = f"""
{tarea}

REVISIÓN HUMANA DE LA EVALUACIÓN ANTERIOR:

Un supervisor humano revisó la evaluación anterior y proporcionó el siguiente feedback:

{feedback}

Debés reconsiderar la respuesta del estudiante teniendo en cuenta este feedback.
Volvé a utilizar las herramientas disponibles para realizar una nueva evaluación.
"""

    last_error = None

    for provider in ["openai", "anthropic", "gemini"]:
        try:
            logger.info(
                "Intentando utilizar proveedor LLM para evaluador: %s",
                provider,
            )

            agente_evaluador = create_agent(
                model=get_model(provider),
                tools=[
                    evaluar_concepto,
                    buscar_fuente,
                    buscar_concepto,
                ],
                system_prompt=EVALUADOR_PROMPT,
            )

            resultado = await agente_evaluador.ainvoke(
                {
                    "messages": [
                        HumanMessage(content=tarea)
                    ]
                }
            )

            respuesta = resultado["messages"][-1].content

            logger.info(
                "Proveedor LLM utilizado correctamente para evaluador: %s",
                provider,
            )

            return {
                "messages": [
                    AIMessage(
                        content=respuesta,
                        name="evaluador",
                    )
                ],
                "contribuciones": [
                    {
                        "agente": "evaluador",
                        "aporte": respuesta,
                    }
                ],
                "pasos": state.get("pasos", 0) + 1,
            }

        except Exception as e:
            last_error = e

            error = classify_error(e)

            logger.warning(
                "El proveedor %s falló para evaluador: %s",
                provider,
                error.message,
            )

            continue

    logger.error(
        "Todos los proveedores LLM fallaron para evaluador"
    )

    raise classify_error(last_error)