"""CLI entry point for the RIL2M agent."""

from __future__ import annotations

import json
import logging
import sys

import typer
from rich.console import Console
from rich.table import Table

from agent.config import get_settings
from agent.graph import build_graph
from agent.state import AgentState

app = typer.Typer(
    name="ril2m",
    help="Suggest @AccessMode annotations for Java Maven test cases.",
)
console = Console()


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)8s] %(message)s (%(filename)s:%(lineno)s)",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stderr,
    )


def _extract_result(result: object, attr: str, default=None):
    """Extract a value from a LangGraph result (dict or dataclass)."""
    if isinstance(result, dict):
        return result.get(attr, default)
    return getattr(result, attr, default)


@app.command()
def analyze(
    project_path: str = typer.Argument(
        ..., help="Path to the Maven project root (must contain pom.xml)"
    ),
    create_pr: bool = typer.Option(
        False, "--pr", help="Create a GitHub PR with the suggested annotations"
    ),
    output_json: bool = typer.Option(
        False, "--json", help="Output results as JSON"
    ),
    log_level: str = typer.Option("INFO", "--log-level", help="Log level"),
) -> None:
    """Analyze a Java Maven project and suggest @AccessMode annotations."""
    _configure_logging(log_level)
    settings = get_settings()

    if create_pr and not settings.github_token:
        console.print(
            "[red]Error:[/red] --pr requires GITHUB_TOKEN to be set in .env"
        )
        raise typer.Exit(1)

    graph = build_graph()
    initial_state = AgentState(
        project_path=project_path,
        create_pr=create_pr,
    )

    console.print(f"\n[bold]Analyzing project:[/bold] {project_path}\n")

    with console.status("[bold green]Running agent pipeline…"):
        result = graph.invoke(initial_state)

    suggestions = _extract_result(result, "suggestions", [])
    errors = _extract_result(result, "errors", [])
    pr_url = _extract_result(result, "pr_url", "")

    if errors:
        for err in errors:
            console.print(f"[yellow]Warning:[/yellow] {err}")

    if output_json:
        data = {
            "suggestions": [
                {
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
                    "new_resources": [
                        {
                            "resource_id": nr.resource.resource_id,
                            "hierarchy_parent": nr.resource.hierarchy_parent,
                            "reasoning": nr.reasoning,
                        }
                        for nr in s.new_resources
                    ],
                    "confidence": s.confidence,
                    "reasoning": s.reasoning,
                }
                for s in suggestions
            ],
            "pr_url": pr_url,
            "errors": errors,
        }
        console.print_json(json.dumps(data, indent=2))
        return

    if not suggestions:
        console.print("[green]All test methods already have @AccessMode annotations.[/green]")
        return

    # Rich table output — annotations
    table = Table(title="RETORCH @AccessMode Annotation Suggestions")
    table.add_column("Class", style="cyan")
    table.add_column("Method", style="magenta")
    table.add_column("Annotations", style="green")
    table.add_column("Confidence", justify="right")
    table.add_column("Reasoning")

    for s in suggestions:
        annotations_str = "\n".join(am.to_java() for am in s.suggested_access_modes)
        table.add_row(
            s.test_case.class_name,
            s.test_case.method_name,
            annotations_str or "(none)",
            f"{s.confidence:.0%}",
            s.reasoning,
        )

    console.print(table)

    # New resources table (if any)
    all_new = [nr for s in suggestions for nr in s.new_resources]
    if all_new:
        nr_table = Table(title="New Resource Suggestions")
        nr_table.add_column("Resource ID", style="cyan")
        nr_table.add_column("Parent", style="magenta")
        nr_table.add_column("Reasoning")

        for nr in all_new:
            nr_table.add_row(
                nr.resource.resource_id,
                ", ".join(nr.resource.hierarchy_parent) or "(root)",
                nr.reasoning,
            )

        console.print(nr_table)

    if pr_url:
        console.print(f"\n[bold green]PR created:[/bold green] {pr_url}")


@app.command()
def serve() -> None:
    """Start the MCP server (stdio transport)."""
    from agent.mcp.server import main as mcp_main

    mcp_main()


@app.command()
def lsp() -> None:
    """Start the LSP server for VS Code integration (stdio transport)."""
    from agent.lsp.server import main as lsp_main

    lsp_main()


if __name__ == "__main__":
    app()
