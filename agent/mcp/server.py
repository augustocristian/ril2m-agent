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

    suggestions = []
    for s in result.get("suggestions", []) if isinstance(result, dict) else result.suggestions:
        suggestions.append(
            {
                "class": s.test_case.class_name,
                "method": s.test_case.method_name,
                "file": s.test_case.file_path,
                "suggested_annotation": s.suggested_annotation,
                "confidence": s.confidence,
                "reasoning": s.reasoning,
            }
        )

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

    pr_url = result.get("pr_url", "") if isinstance(result, dict) else result.pr_url
    errors = result.get("errors", []) if isinstance(result, dict) else result.errors

    suggestions = []
    for s in result.get("suggestions", []) if isinstance(result, dict) else result.suggestions:
        suggestions.append(
            {
                "class": s.test_case.class_name,
                "method": s.test_case.method_name,
                "suggested_annotation": s.suggested_annotation,
                "confidence": s.confidence,
            }
        )

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
                "annotations": tc.annotations,
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
