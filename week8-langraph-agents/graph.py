"""
warrantyAI — Week 8
graph.py — LangGraph StateGraph wiring

Wires Reader → Classifier → Reminder into a compiled graph.
This is the entire orchestration layer — 15 lines of actual logic.

Usage:
    from graph import app
    result = app.invoke(initial_state)
"""

from langgraph.graph import StateGraph, END
from state import WarrantyState
from agents.reader import reader_agent
from agents.classifier import classifier_agent
from agents.reminder import reminder_agent


def build_graph() -> StateGraph:
    """
    Build and return the compiled warrantyAI StateGraph.

    Flow:
        START → reader_agent → classifier_agent → reminder_agent → END

    Each node:
        - Receives full WarrantyState
        - Returns partial dict (only the keys it updates)
        - LangGraph merges the partial dict back into state
    """
    graph = StateGraph(WarrantyState)

    #    Register nodes                                                     
    graph.add_node("reader",     reader_agent)
    graph.add_node("classifier", classifier_agent)
    graph.add_node("reminder",   reminder_agent)

    #    Wire edges                                                         
    graph.set_entry_point("reader")
    graph.add_edge("reader",     "classifier")
    graph.add_edge("classifier", "reminder")
    graph.add_edge("reminder",   END)

    return graph.compile()


# Compiled graph — import this in run.py and Lambda handlers
app = build_graph()
