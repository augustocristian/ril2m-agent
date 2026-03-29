"""RIL2M Language Server – pygls-based LSP server.

Provides diagnostics, code actions, and code lenses for Java test files
that are missing @AccessMode annotations.

Run with:  python -m agent.lsp.server
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from lsprotocol import types as lsp
from pygls.server import LanguageServer

from agent.lsp.analyzer import analyze_workspace, SuggestionResult

logger = logging.getLogger(__name__)

# ─── Server instance ─────────────────────────────────────────────────

server = LanguageServer("ril2m-agent", "v0.1.0")

# In-memory suggestion cache: file URI → list of suggestions
_suggestions: dict[str, list[SuggestionResult]] = {}


# ─── Helpers ─────────────────────────────────────────────────────────

def _find_method_range(
    source: str, method_name: str
) -> tuple[int, int, int, int]:
    """Return (start_line, start_col, end_line, end_col) for a method."""
    pattern = re.compile(
        rf"void\s+{re.escape(method_name)}\s*\(", re.MULTILINE
    )
    match = pattern.search(source)
    if not match:
        return (0, 0, 0, 0)

    start = match.start()
    lines_before = source[:start].split("\n")
    start_line = len(lines_before) - 1
    start_col = len(lines_before[-1])
    end_col = start_col + len(match.group())
    return (start_line, start_col, start_line, end_col)


def _uri_to_path(uri: str) -> str:
    """Convert a file URI to a filesystem path."""
    if uri.startswith("file:///"):
        path = uri[8:] if uri[9] == ":" else uri[7:]
    elif uri.startswith("file://"):
        path = uri[7:]
    else:
        path = uri
    return path.replace("/", "\\") if "\\" in uri else path


def _path_to_uri(path: str) -> str:
    """Convert a filesystem path to a file URI."""
    normalized = path.replace("\\", "/")
    if not normalized.startswith("/"):
        normalized = "/" + normalized
    return f"file://{normalized}"


def _insert_annotations(source: str, method_name: str, annotations_java: str) -> str:
    """Insert annotation lines before the method's @Test annotation."""
    if not annotations_java.strip():
        return source

    if "AccessMode" not in source:
        last_import = 0
        for m in re.finditer(r"^import\s+[^;]+;", source, re.MULTILINE):
            last_import = m.end()
        if last_import > 0:
            source = (
                source[:last_import]
                + "\nimport giis.retorch.annotations.AccessMode;"
                + source[last_import:]
            )

    pattern = re.compile(
        rf"([ \t]*)(@(?:Test|ParameterizedTest|RepeatedTest)[^\n]*\n)"
        rf"([ \t]*(?:public\s+|protected\s+|private\s+)?(?:static\s+)?void\s+{re.escape(method_name)}\s*\()",
        re.MULTILINE,
    )
    match = pattern.search(source)
    if match:
        indent = match.group(1)
        insert_pos = match.start()
        indented = "\n".join(
            f"{indent}{line}" for line in annotations_java.splitlines()
        )
        return source[:insert_pos] + indented + "\n" + source[insert_pos:]

    pattern2 = re.compile(
        rf"([ \t]*)((?:public\s+|protected\s+|private\s+)?(?:static\s+)?void\s+{re.escape(method_name)}\s*\()",
        re.MULTILINE,
    )
    match2 = pattern2.search(source)
    if match2:
        indent = match2.group(1)
        insert_pos = match2.start()
        indented = "\n".join(
            f"{indent}{line}" for line in annotations_java.splitlines()
        )
        return source[:insert_pos] + indented + "\n" + source[insert_pos:]

    return source


def _build_diagnostic_message(s: SuggestionResult) -> str:
    """Build a diagnostic message including annotations and new resources."""
    parts = [
        f"Missing @AccessMode annotation(s).\n"
        f"Suggested:\n{s.suggested_annotations_java}\n"
        f"({s.confidence:.0%} confidence)\n"
        f"{s.reasoning}"
    ]
    if s.new_resources:
        nr_lines = "\n".join(
            f"  - {nr.resource_id} (parent: {nr.hierarchy_parent}) — {nr.reasoning}"
            for nr in s.new_resources
        )
        parts.append(f"\nNew resources suggested:\n{nr_lines}")
    return "".join(parts)


def _build_diagnostic_data(s: SuggestionResult) -> str:
    """Build the JSON data payload for a diagnostic."""
    data: dict = {
        "method": s.method_name,
        "class": s.class_name,
        "annotations_java": s.suggested_annotations_java,
        "file": s.file_path,
    }
    if s.new_resources:
        data["new_resources"] = [
            {
                "resource_id": nr.resource_id,
                "hierarchy_parent": nr.hierarchy_parent,
                "reasoning": nr.reasoning,
            }
            for nr in s.new_resources
        ]
    return json.dumps(data)


# ─── Publish diagnostics for a file ─────────────────────────────────

def _publish_diagnostics_for_file(uri: str) -> None:
    """Publish diagnostics for all cached suggestions for a file."""
    file_suggestions = _suggestions.get(uri, [])
    if not file_suggestions:
        server.publish_diagnostics(uri, [])
        return

    path = _uri_to_path(uri)
    try:
        source = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return

    diagnostics: list[lsp.Diagnostic] = []
    for s in file_suggestions:
        sl, sc, el, ec = _find_method_range(source, s.method_name)
        diagnostics.append(
            lsp.Diagnostic(
                range=lsp.Range(
                    start=lsp.Position(line=sl, character=sc),
                    end=lsp.Position(line=el, character=ec),
                ),
                message=_build_diagnostic_message(s),
                severity=lsp.DiagnosticSeverity.Warning,
                source="ril2m",
                code="missing-access-mode",
                data=_build_diagnostic_data(s),
            )
        )

    server.publish_diagnostics(uri, diagnostics)


# ─── Commands ────────────────────────────────────────────────────────

@server.command("ril2m.analyzeProject")
def cmd_analyze(ls: LanguageServer, args: list) -> str:
    """Run the full agent pipeline on the workspace."""
    workspace_folders = ls.workspace.folders
    if not workspace_folders:
        ls.show_message("No workspace folder open.", lsp.MessageType.Error)
        return json.dumps({"error": "no workspace"})

    root_path = _uri_to_path(workspace_folders[0].uri)
    ls.show_message(f"Analyzing {root_path}…", lsp.MessageType.Info)

    try:
        results = analyze_workspace(root_path)
    except Exception as exc:
        ls.show_message(f"Analysis failed: {exc}", lsp.MessageType.Error)
        return json.dumps({"error": str(exc)})

    _suggestions.clear()
    for s in results:
        uri = _path_to_uri(s.file_path)
        _suggestions.setdefault(uri, []).append(s)

    for uri in _suggestions:
        _publish_diagnostics_for_file(uri)

    count = len(results)
    new_res_count = sum(len(s.new_resources) for s in results)
    msg = f"RIL2M: Found {count} test(s) missing @AccessMode."
    if new_res_count:
        msg += f" {new_res_count} new resource(s) suggested."
    ls.show_message(msg, lsp.MessageType.Info)

    return json.dumps(
        {
            "count": count,
            "suggestions": [
                {
                    "class": s.class_name,
                    "method": s.method_name,
                    "file": s.file_path,
                    "annotations_java": s.suggested_annotations_java,
                    "new_resources": [
                        {
                            "resource_id": nr.resource_id,
                            "hierarchy_parent": nr.hierarchy_parent,
                            "reasoning": nr.reasoning,
                        }
                        for nr in s.new_resources
                    ],
                    "confidence": s.confidence,
                    "reasoning": s.reasoning,
                }
                for s in results
            ],
        }
    )


@server.command("ril2m.applySuggestion")
def cmd_apply_suggestion(ls: LanguageServer, args: list) -> str:
    """Apply a single annotation suggestion to the source file."""
    if not args or not args[0]:
        return json.dumps({"error": "no arguments"})

    data = json.loads(args[0]) if isinstance(args[0], str) else args[0]
    method_name = data.get("method", "")
    annotations_java = data.get("annotations_java", "")
    file_path = data.get("file", "")

    if not all([method_name, annotations_java, file_path]):
        return json.dumps({"error": "missing fields"})

    path = Path(file_path)
    if not path.is_file():
        return json.dumps({"error": f"file not found: {file_path}"})

    source = path.read_text(encoding="utf-8")
    new_source = _insert_annotations(source, method_name, annotations_java)

    if new_source == source:
        return json.dumps({"error": "could not locate method"})

    path.write_text(new_source, encoding="utf-8")

    # Add new resources to SystemResources.json if suggested
    added_resources = _apply_new_resources(data)

    # Remove from cache and refresh diagnostics
    uri = _path_to_uri(file_path)
    if uri in _suggestions:
        _suggestions[uri] = [
            s for s in _suggestions[uri] if s.method_name != method_name
        ]
        _publish_diagnostics_for_file(uri)

    result: dict = {"applied": True, "method": method_name}
    if added_resources:
        result["added_resources"] = added_resources
    return json.dumps(result)


@server.command("ril2m.applyAllSuggestions")
def cmd_apply_all(ls: LanguageServer, args: list) -> str:
    """Apply all cached annotation suggestions."""
    applied = 0
    all_new_resources: list[dict] = []

    for uri, suggestions in list(_suggestions.items()):
        file_path = _uri_to_path(uri)
        path = Path(file_path)
        if not path.is_file():
            continue

        source = path.read_text(encoding="utf-8")
        for s in suggestions:
            new_source = _insert_annotations(
                source, s.method_name, s.suggested_annotations_java
            )
            if new_source != source:
                source = new_source
                applied += 1
            # Collect new resources
            for nr in s.new_resources:
                all_new_resources.append(
                    {
                        "resource_id": nr.resource_id,
                        "hierarchy_parent": nr.hierarchy_parent,
                        "reasoning": nr.reasoning,
                    }
                )

        path.write_text(source, encoding="utf-8")

    # Add all new resources at once
    added_resources = _apply_new_resources_bulk(all_new_resources)

    _suggestions.clear()

    ls.show_message(
        f"RIL2M: Applied {applied} annotation(s).", lsp.MessageType.Info
    )
    result: dict = {"applied": applied}
    if added_resources:
        result["added_resources"] = added_resources
    return json.dumps(result)


def _apply_new_resources(data: dict) -> list[str]:
    """Add new resources from a suggestion data dict to SystemResources.json.

    Returns list of resource IDs that were added.
    """
    nr_list = data.get("new_resources", [])
    if not nr_list:
        return []
    return _apply_new_resources_bulk(nr_list)


def _apply_new_resources_bulk(nr_list: list[dict]) -> list[str]:
    """Add a batch of new resources to SystemResources.json.

    Searches the workspace for the .retorch/ resources file.
    Returns list of resource IDs that were added.
    """
    if not nr_list:
        return []

    workspace_folders = server.workspace.folders
    if not workspace_folders:
        return []

    root_path = _uri_to_path(workspace_folders[0].uri)

    from agent.resources import add_resources, find_resources_file
    from agent.state import NewResourceSuggestion

    resources_file = find_resources_file(root_path)
    if not resources_file:
        logger.warning("No .retorch/*SystemResources.json found — cannot add resources.")
        return []

    from agent.resources import build_default_resource

    suggestions = []
    for nr in nr_list:
        parent = nr.get("hierarchy_parent", "")
        resource = build_default_resource(
            resource_id=nr["resource_id"],
            hierarchy_parent=[parent] if parent else [],
        )
        suggestions.append(
            NewResourceSuggestion(resource=resource, reasoning=nr.get("reasoning", ""))
        )

    return add_resources(str(resources_file), suggestions)


# ─── Code Actions (Quick Fix) ───────────────────────────────────────

@server.feature(lsp.TEXT_DOCUMENT_CODE_ACTION)
def code_action(params: lsp.CodeActionParams) -> list[lsp.CodeAction]:
    """Provide 'Apply @AccessMode(…)' quick fixes for ril2m diagnostics."""
    actions: list[lsp.CodeAction] = []

    for diag in params.context.diagnostics:
        if diag.source != "ril2m" or diag.data is None:
            continue

        data = json.loads(diag.data) if isinstance(diag.data, str) else diag.data

        num_annotations = data.get("annotations_java", "").count("@AccessMode")
        title = f"Apply {num_annotations} @AccessMode annotation(s) to {data['method']}"
        if data.get("new_resources"):
            title += f" (+{len(data['new_resources'])} new resource(s))"

        actions.append(
            lsp.CodeAction(
                title=title,
                kind=lsp.CodeActionKind.QuickFix,
                diagnostics=[diag],
                command=lsp.Command(
                    title="Apply annotations",
                    command="ril2m.applySuggestion",
                    arguments=[json.dumps(data)],
                ),
            )
        )

    return actions


# ─── Code Lens ───────────────────────────────────────────────────────

@server.feature(lsp.TEXT_DOCUMENT_CODE_LENS)
def code_lens(params: lsp.CodeLensParams) -> list[lsp.CodeLens]:
    """Show inline lenses above unannotated test methods."""
    uri = params.text_document.uri
    file_suggestions = _suggestions.get(uri, [])
    if not file_suggestions:
        return []

    path = _uri_to_path(uri)
    try:
        source = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    lenses: list[lsp.CodeLens] = []
    for s in file_suggestions:
        sl, sc, el, ec = _find_method_range(source, s.method_name)
        range_ = lsp.Range(
            start=lsp.Position(line=sl, character=sc),
            end=lsp.Position(line=el, character=ec),
        )

        annotations_java = s.suggested_annotations_java
        num_am = len(s.suggested_access_modes)
        data = _build_diagnostic_data(s)

        # "Apply" lens
        apply_title = f"Apply {num_am} @AccessMode annotation(s)"
        if s.new_resources:
            apply_title += f" (+{len(s.new_resources)} new resource(s))"

        lenses.append(
            lsp.CodeLens(
                range=range_,
                command=lsp.Command(
                    title=apply_title,
                    command="ril2m.applySuggestion",
                    arguments=[data],
                ),
            )
        )

        # "Info" lens
        pct = round(s.confidence * 100)
        lenses.append(
            lsp.CodeLens(
                range=range_,
                command=lsp.Command(
                    title=f"{pct}% — {s.reasoning}",
                    command="",
                ),
            )
        )

    return lenses


# ─── Entry point ─────────────────────────────────────────────────────

def main() -> None:
    logging.basicConfig(level=logging.INFO)
    server.start_io()


if __name__ == "__main__":
    main()
