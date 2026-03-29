"""Bridge between the LSP server and the agent pipeline.

Runs the LangGraph workflow and returns lightweight result objects
that the LSP server can cache and convert to diagnostics / code actions.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from agent.graph import build_graph
from agent.state import AgentState

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SuggestionResult:
    """Lightweight result for LSP consumption."""

    file_path: str
    class_name: str
    method_name: str
    suggested_annotation: str
    confidence: float
    reasoning: str


def analyze_workspace(project_path: str) -> list[SuggestionResult]:
    """Run the agent pipeline and return a flat list of suggestions.

    This does NOT create a PR — it only analyzes.
    """
    graph = build_graph()
    initial_state = AgentState(project_path=project_path, create_pr=False)

    result = graph.invoke(initial_state)

    # Extract suggestions from the result
    suggestions_raw = (
        result.suggestions
        if hasattr(result, "suggestions")
        else result.get("suggestions", [])
    )

    results: list[SuggestionResult] = []
    for s in suggestions_raw:
        results.append(
            SuggestionResult(
                file_path=s.test_case.file_path,
                class_name=s.test_case.class_name,
                method_name=s.test_case.method_name,
                suggested_annotation=s.suggested_annotation,
                confidence=s.confidence,
                reasoning=s.reasoning,
            )
        )

    return results
