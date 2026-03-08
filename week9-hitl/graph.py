"""
warrantyAI — Week 9
graph.py — Updated StateGraph with HITL node

Week 8 flow:  Reader → Classifier → Reminder
Week 9 flow:  Reader → Classifier → HITL → [pause if high] → Reminder

The HITL node either:
  - Raises NodeInterrupt (high risk)  → graph pauses, human reviews via email
  - Returns hitl_status="skipped"     → graph continues to Reminder immediately

When resume_lambda approves a paused document, it re-invokes the pipeline
Lambda with resume_from_hitl=True, which calls run_from_reminder() directly,
bypassing Reader / Classifier / HITL entirely.
"""

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from state import WarrantyState
from agents.reader     import reader_agent
from agents.classifier import classifier_agent
from agents.hitl       import hitl_agent
from agents.reminder   import reminder_agent


def build_graph() -> StateGraph:
    """
    Build and compile the Week 9 warrantyAI StateGraph.

    MemorySaver enables graph state persistence across interrupts.
    In production (Week 10+) swap MemorySaver for a DynamoDB checkpointer.
    """
    checkpointer = MemorySaver()
    graph        = StateGraph(WarrantyState)

    # ── Register nodes ────────────────────────────────────────────────────
    graph.add_node("reader",     reader_agent)
    graph.add_node("classifier", classifier_agent)
    graph.add_node("hitl",       hitl_agent)       # NEW Week 9
    graph.add_node("reminder",   reminder_agent)

    # ── Wire edges ────────────────────────────────────────────────────────
    graph.set_entry_point("reader")
    graph.add_edge("reader",     "classifier")
    graph.add_edge("classifier", "hitl")           # always goes to HITL check
    graph.add_edge("hitl",       "reminder")       # HITL either passes through or interrupts
    graph.add_edge("reminder",   END)

    return graph.compile(
        checkpointer=checkpointer,
        interrupt_before=["hitl"]  # LangGraph pauses BEFORE hitl node if NodeInterrupt raised
    )


# Compiled graph — import this in run.py
app = build_graph()
