from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage

from app.errors import classify_error
from app.logging_config import logger
from app.models import get_model
from app.schemas import AgentState
from app.tools import buscar_concepto, buscar_fuente

PROFESOR_PROMPT = """
Sos un profesor universitario especializado en metodología
de la investigación y estadística.

Tu función es responder consultas utilizando la base de
conocimientos disponible mediante las herramientas proporcionadas.

1. Si el usuario solicita una definición o explicación de un
   concepto, utilizá 'buscar_concepto'.

2. Si el usuario pregunta dónde encontrar información, qué
   fuente consultar o en qué página aparece un tema, utilizá
   'buscar_fuente'.

3. No inventes información cuando la respuesta dependa de los
   documentos disponibles.

4. Si las herramientas no proporcionan información suficiente,
   indicálo claramente.

5. Cuando la consulta involucre más de un concepto, obtené
   información sobre cada concepto antes de responder.

6. Respondé de manera clara, natural y didáctica.

REGLAS DE USO DE HERRAMIENTAS:

- Utilizá una sola herramienta por vez.
- Esperá el resultado de una herramienta antes de solicitar otra.
- No solicites llamadas simultáneas a distintas herramientas.
- No llames a 'buscar_concepto' más de una vez durante la misma ejecución.
- Utilizá la información obtenida de las herramientas antes de realizar
  otra consulta.
"""


async def nodo_profesor(state: AgentState) -> dict:
    tarea = state["messages"][-1].content

    last_error = None

    for provider in ["openai", "anthropic", "gemini"]:
        try:
            logger.info(
                "Intentando utilizar proveedor LLM para profesor: %s",
                provider,
            )

            agente_profesor = create_agent(
                model=get_model(provider),
                tools=[buscar_concepto, buscar_fuente],
                system_prompt=PROFESOR_PROMPT,
            )

            resultado = await agente_profesor.ainvoke(
                {"messages": [HumanMessage(content=tarea)]}
            )

            respuesta = resultado["messages"][-1].content

            logger.info(
                "Proveedor LLM utilizado correctamente para profesor: %s",
                provider,
            )

            return {
                "messages": [
                    AIMessage(
                        content=respuesta,
                        name="profesor",
                    )
                ],
                "contribuciones": [
                    {
                        "agente": "profesor",
                        "aporte": respuesta,
                    }
                ],
                "pasos": state.get("pasos", 0) + 1,
            }

        except Exception as e:
            last_error = e

            error = classify_error(e)

            logger.warning(
                "El proveedor %s falló para profesor: %s",
                provider,
                error.message,
            )

            continue

    logger.error(
        "Todos los proveedores LLM fallaron para profesor"
    )

    raise classify_error(last_error)