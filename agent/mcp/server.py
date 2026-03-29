"""MCP server that exposes the RIL2M agent capabilities as tools.

Run with:  python -m agent.mcp.server
"""

from __future__ import annotations

import json
import logging

from mcp.server.fastmcp import FastMCP

from agent.graph import build_graph
from agent.state import AgentState

logger = logging.getLogger(__name__)

mcp = FastMCP(
    "ril2m-agent",
    description=(
        "Agent that suggests @AccessMode annotations for Java Maven test "
        "cases using RAG (Ollama embeddings + ChromaDB) and an LLM."
    ),
)


def _extract_result(result: object, attr: str, default=None):
    """Extract a value from a LangGraph result (dict or dataclass)."""
    if isinstance(result, dict):
        return result.get(attr, default)
    return getattr(result, attr, default)


def _format_suggestion(s) -> dict:
    """Format a single AnnotationSuggestion for JSON output."""
    suggestion: dict = {
        "class": s.test_case.class_name,
        "method": s.test_case.method_name,
        "file": s.test_case.file_path,
        "suggested_access_modes": [
            {
                "resID": am.res_id,
                "concurrency": am.concurrency,
                "sharing": am.sharing,
                "accessMode": am.access_mode,
            }
            for am in s.suggested_access_modes
        ],
        "confidence": s.confidence,
        "reasoning": s.reasoning,
    }
    if s.new_resources:
        suggestion["new_resources"] = [
            {
                "resource_id": nr.resource.resource_id,
                "hierarchy_parent": nr.resource.hierarchy_parent,
                "reasoning": nr.reasoning,
            }
            for nr in s.new_resources
        ]
    return suggestion


@mcp.tool()
def analyze_project(project_path: str) -> str:
    """Scan a Java Maven project, find test cases without @AccessMode
    annotations, and suggest the correct annotation for each one.

    Args:
        project_path: Absolute path to the Maven project root (must contain pom.xml).

    Returns:
        JSON with the list of annotation suggestions.
    """
    graph = build_graph()
    initial_state = AgentState(project_path=project_path, create_pr=False)
    result = graph.invoke(initial_state)

    raw = _extract_result(result, "suggestions", [])
    suggestions = [_format_suggestion(s) for s in raw]

    return json.dumps({"suggestions": suggestions, "count": len(suggestions)}, indent=2)


@mcp.tool()
def analyze_and_create_pr(project_path: str) -> str:
    """Scan a Java Maven project, suggest @AccessMode annotations, apply them,
    and create a GitHub Pull Request.

    Requires GITHUB_TOKEN, GITHUB_OWNER, and GITHUB_REPO environment variables.

    Args:
        project_path: Absolute path to the Maven project root.

    Returns:
        JSON with the PR URL and suggestion details.
    """
    graph = build_graph()
    initial_state = AgentState(project_path=project_path, create_pr=True)
    result = graph.invoke(initial_state)

    pr_url = _extract_result(result, "pr_url", "")
    errors = _extract_result(result, "errors", [])
    raw = _extract_result(result, "suggestions", [])
    suggestions = [_format_suggestion(s) for s in raw]

    return json.dumps(
        {
            "pr_url": pr_url,
            "suggestions": suggestions,
            "errors": errors,
        },
        indent=2,
    )


@mcp.tool()
def list_unannotated_tests(project_path: str) -> str:
    """Scan a Java Maven project and list all test methods that lack
    @AccessMode annotations, without running the LLM suggestion step.

    Args:
        project_path: Absolute path to the Maven project root.

    Returns:
        JSON with unannotated test methods.
    """
    from agent.nodes.parser import parse_tests
    from agent.nodes.scanner import scan_project

    scan_result = scan_project(AgentState(project_path=project_path))
    if scan_result.get("current_step") == "scan_failed":
        return json.dumps({"errors": scan_result.get("errors", [])})

    state = AgentState(
        project_path=project_path,
        test_files=scan_result.get("test_files", []),
    )
    parse_result = parse_tests(state)

    tests = []
    non_annotated = parse_result.get("non_annotated_tests", [])
    for tc in non_annotated:
        tests.append(
            {
                "class": tc.class_name,
                "method": tc.method_name,
                "file": tc.file_path,
            }
        )

    return json.dumps(
        {"unannotated_tests": tests, "count": len(tests)}, indent=2
    )


def main():
    """Start the MCP server."""
    logging.basicConfig(level=logging.INFO)
    mcp.run()


if __name__ == "__main__":
    main()
