"""Bridge between the LSP server and the agent pipeline.

Runs the LangGraph workflow and returns lightweight result objects
that the LSP server can cache and convert to diagnostics / code actions.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from agent.graph import build_graph
from agent.state import AgentState

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AccessModeSuggestion:
    """A single @AccessMode annotation suggestion."""

    res_id: str
    concurrency: int
    sharing: bool
    access_mode: str

    def to_java(self) -> str:
        sharing_str = "true" if self.sharing else "false"
        return (
            f'@AccessMode(resID = "{self.res_id}", '
            f"concurrency = {self.concurrency}, "
            f"sharing = {sharing_str}, "
            f'accessMode = "{self.access_mode}")'
        )


@dataclass(frozen=True)
class NewResourceResult:
    """A suggestion to add a new resource to SystemResources.json."""

    resource_id: str
    hierarchy_parent: str
    reasoning: str


@dataclass(frozen=True)
class SuggestionResult:
    """Lightweight result for LSP consumption."""

    file_path: str
    class_name: str
    method_name: str
    suggested_access_modes: tuple[AccessModeSuggestion, ...] = ()
    new_resources: tuple[NewResourceResult, ...] = ()
    confidence: float = 0.0
    reasoning: str = ""

    @property
    def suggested_annotations_java(self) -> str:
        return "\n".join(am.to_java() for am in self.suggested_access_modes)


def analyze_workspace(project_path: str) -> list[SuggestionResult]:
    """Run the agent pipeline and return a flat list of suggestions.

    This does NOT create a PR — it only analyzes.
    """
    graph = build_graph()
    initial_state = AgentState(project_path=project_path, create_pr=False)

    result = graph.invoke(initial_state)

    suggestions_raw = (
        result.suggestions
        if hasattr(result, "suggestions")
        else result.get("suggestions", [])
    )

    results: list[SuggestionResult] = []
    for s in suggestions_raw:
        new_res = tuple(
            NewResourceResult(
                resource_id=nr.resource.resource_id,
                hierarchy_parent=", ".join(nr.resource.hierarchy_parent),
                reasoning=nr.reasoning,
            )
            for nr in s.new_resources
        )
        results.append(
            SuggestionResult(
                file_path=s.test_case.file_path,
                class_name=s.test_case.class_name,
                method_name=s.test_case.method_name,
                suggested_access_modes=tuple(
                    AccessModeSuggestion(
                        res_id=am.res_id,
                        concurrency=am.concurrency,
                        sharing=am.sharing,
                        access_mode=am.access_mode,
                    )
                    for am in s.suggested_access_modes
                ),
                new_resources=new_res,
                confidence=s.confidence,
                reasoning=s.reasoning,
            )
        )

    return results
