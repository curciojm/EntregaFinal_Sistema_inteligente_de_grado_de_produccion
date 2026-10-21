from langgraph.types import interrupt


def human_approval(state):
    # Interrupt avisa que el procesamiento tiene que ser interrumpido. En el worker se ve que luego de que el grafo hace una respeusta.
    decision = interrupt(
        {
            "message": "Se requiere aprobación humana para ejecutar la evaluación.",
            "job_id": state["job_id"],
        }
    )

    aprobado = decision["decision"] == "approve"

    return {
        "approval": aprobado,
        "feedback_humano": decision.get("feedback", ""),
        "revision_humana": not aprobado,
    }