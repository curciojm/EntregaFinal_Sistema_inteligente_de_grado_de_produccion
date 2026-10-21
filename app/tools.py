from langchain_core.tools import tool
from sklearn.metrics.pairwise import cosine_similarity

from app.db_config import EMBEDDINGS
from app.errors import classify_error
from app.schemas import ResultadoConcepto, ResultadoEvaluacion, ResultadoFuente
from app.logging_config import logger
from app.retriever import retriever_hibrido


@tool # el decorador ya establece una estructura. Eso es útil, pero no establece por sí solo restricciones como longitud mínima, longitud máxima o cadenas no vacías.
async def buscar_concepto(consulta: str) -> list[ResultadoConcepto]:
    """
    Busca información teórica sobre un concepto de estadística
    y metodología.

    Usar esta herramienta cuando el usuario solicite una definición
    o explicación de un concepto.

    Devuelve únicamente el contenido relevante.
    """
    try:
        logger.info("Ejecutando buscar_concepto: %s", consulta)

        docs = await retriever_hibrido.ainvoke(consulta)

        return [
            ResultadoConcepto(
                contenido=doc.page_content,
            )
            for doc in docs[:5]
        ]

    except Exception as e:
        logger.exception(
            "ERROR REAL en buscar_concepto"
        )

        error = classify_error(e)

        logger.error(
            "Error durante la ejecución de buscar_concepto: %s",
            error.message,
        )

        raise error

@tool
async def buscar_fuente(tema: str) -> list[ResultadoFuente]:
    """
    Busca en la base de conocimientos dónde se encuentra información
    relevante sobre un tema de estadística y metodología.

    Usar esta herramienta cuando el usuario pregunte dónde encontrar
    información, qué fuente consultar o en qué página aparece un tema.

    Devuelve la fuente y el número de página correspondiente.
    """
    try:
        logger.info("Ejecutando buscar_fuente: %s", tema)

        docs = await retriever_hibrido.ainvoke(tema)

        return [
            ResultadoFuente(
                fuente=doc.metadata.get("fuente", "desconocida"),
                pagina=int(doc.metadata.get("pagina", 0)),
            )
            for doc in docs[:5]
        ]

    except Exception as e:
        error = classify_error(e)
        logger.error(
            "Error durante la ejecución de buscar_fuente: %s",
            error.message,
        )
        raise error

UMBRAL_INCOMPLETA = 0.55
UMBRAL_BIEN = 0.70
UMBRAL_MUY_BIEN = 0.90

@tool
async def evaluar_concepto(
    tema: str,
    respuesta_usuario: str,
) -> ResultadoEvaluacion:
    """
    Evalúa la respuesta del usuario sobre un concepto de estadística
    o metodología mediante similitud semántica con información
    recuperada de la base de conocimientos.

    La evaluación utiliza umbrales heurísticos establecidos con
    fines educativos:
        
        0.00 - 0.54 → Mal
        0.55 - 0.69 → Incompleta
        0.70 - 0.89 → Bien
        0.90 - 1.00 → Muy bien

    Estos umbrales no fueron calibrados empíricamente y la
    similitud semántica no constituye por sí sola una medida
    definitiva de la calidad conceptual de una respuesta.
    """
    try:
        logger.info(
            "Ejecutando evaluar_concepto: %s",
            tema,
        )

        docs = await retriever_hibrido.ainvoke(tema)

        embedding_respuesta = await EMBEDDINGS.aembed_query(
            respuesta_usuario
        )

        embedding_docs = await EMBEDDINGS.aembed_documents(
            [doc.page_content for doc in docs]
        )

        similitudes = cosine_similarity(
            [embedding_respuesta],
            embedding_docs
        )[0]

        similitud = float(max(similitudes))
        logger.info(
            "Similitud semántica obtenida: %.3f",
            similitud,
        )

        if similitud < UMBRAL_INCOMPLETA:
            evaluacion = "Mal"
        elif similitud < UMBRAL_BIEN:
            evaluacion = "Incompleta"
        elif similitud < UMBRAL_MUY_BIEN:
            evaluacion = "Bien"
        else:
            evaluacion = "Muy bien"

        return ResultadoEvaluacion(
            evaluacion=evaluacion,
            mejora=(
                f"La similitud semántica obtenida fue "
                f"{similitud:.2f}."
            ),
        )
    
    except Exception as e:
        logger.exception(
            "ERROR REAL en evaluar_concepto"
    )

        error = classify_error(e)

        logger.error(
            "Error durante la ejecución de evaluar_concepto: %s",
            error.message,
        )

        raise error