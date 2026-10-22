from langgraph.types import interrupt


def human_approval(state):
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