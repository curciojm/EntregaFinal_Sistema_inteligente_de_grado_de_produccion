from typing import Literal

from langgraph.graph import StateGraph, START, END

from app.hitl import human_approval
from app.agents.profesor import nodo_profesor
from app.agents.supervisor import nodo_supervisor
from app.agents.evaluador import nodo_evaluador
from app.agents.sintesis import nodo_sintesis
from app.schemas import AgentState


def enrutar(state: AgentState) -> Literal["profesor", "evaluador", "sintesis"]:

    if state["next_agent"] == "FINISH":
        return "sintesis"

    return state["next_agent"]


def enrutar_aprobacion(state: AgentState) -> Literal["evaluador"]:
    return "evaluador"

def enrutar_despues_evaluador(state: AgentState) -> Literal["supervisor", "human_approval"]:

    if state.get("revision_humana", False):
        return "human_approval"

    return "supervisor"


grafo = StateGraph(AgentState)

grafo.add_node("supervisor", nodo_supervisor)
grafo.add_node("profesor", nodo_profesor)
grafo.add_node("evaluador", nodo_evaluador)
grafo.add_node("sintesis", nodo_sintesis)
grafo.add_node("human_approval", human_approval)


grafo.add_edge(START, "supervisor")


grafo.add_conditional_edges(
    "supervisor",
    enrutar,
    {
        "profesor": "profesor",
        "evaluador": "human_approval",
        "sintesis": "sintesis",
    },
)


grafo.add_edge("profesor", "supervisor")


grafo.add_conditional_edges(
    "human_approval",
    enrutar_aprobacion,
    {
        "evaluador": "evaluador",
    },
)

grafo.add_conditional_edges(
    "evaluador",
    enrutar_despues_evaluador,
    {
        "supervisor": "supervisor",
        "human_approval": "human_approval",
    },
)

grafo.add_edge("sintesis", END)