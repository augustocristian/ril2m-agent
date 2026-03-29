"""LangGraph workflow definition for the RIL2M agent."""

from __future__ import annotations

import logging

from langgraph.graph import END, StateGraph

from agent.nodes.annotator import suggest_annotations
from agent.nodes.parser import parse_tests
from agent.nodes.pr_creator import create_pr
from agent.nodes.rag import build_rag_index
from agent.nodes.scanner import scan_project
from agent.state import AgentState

logger = logging.getLogger(__name__)


def _should_continue_after_scan(state: AgentState) -> str:
    """Route after scanning: abort on error, otherwise parse."""
    if state.current_step == "scan_failed":
        return "end"
    return "parse"


def _should_continue_after_parse(state: AgentState) -> str:
    """Route after parsing: skip RAG if no annotated tests exist."""
    if not state.non_annotated_tests:
        return "end"
    if state.annotated_tests:
        return "build_rag"
    # No annotated tests to learn from – go straight to annotator
    return "annotate"


def _should_create_pr(state: AgentState) -> str:
    """Route after annotation: create PR or finish."""
    if state.create_pr and state.suggestions:
        return "create_pr"
    return "end"


def build_graph() -> StateGraph:
    """Build and compile the LangGraph workflow."""
    workflow = StateGraph(AgentState)

    # Nodes
    workflow.add_node("scan", scan_project)
    workflow.add_node("parse", parse_tests)
    workflow.add_node("build_rag", build_rag_index)
    workflow.add_node("annotate", suggest_annotations)
    workflow.add_node("create_pr", create_pr)

    # Edges
    workflow.set_entry_point("scan")

    workflow.add_conditional_edges(
        "scan",
        _should_continue_after_scan,
        {"parse": "parse", "end": END},
    )

    workflow.add_conditional_edges(
        "parse",
        _should_continue_after_parse,
        {"build_rag": "build_rag", "annotate": "annotate", "end": END},
    )

    workflow.add_edge("build_rag", "annotate")

    workflow.add_conditional_edges(
        "annotate",
        _should_create_pr,
        {"create_pr": "create_pr", "end": END},
    )

    workflow.add_edge("create_pr", END)

    return workflow.compile()


# Pre-compiled graph instance for convenience
graph = build_graph()
