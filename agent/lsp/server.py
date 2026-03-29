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

    # Calculate line/col from offset
    start = match.start()
    lines_before = source[:start].split("\n")
    start_line = len(lines_before) - 1
    start_col = len(lines_before[-1])
    end_col = start_col + len(match.group())
    return (start_line, start_col, start_line, end_col)


def _uri_to_path(uri: str) -> str:
    """Convert a file URI to a filesystem path."""
    if uri.startswith("file:///"):
        # Windows: file:///C:/...  →  C:/...
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
        annotations_str = s.suggested_annotations_java
        diagnostics.append(
            lsp.Diagnostic(
                range=lsp.Range(
                    start=lsp.Position(line=sl, character=sc),
                    end=lsp.Position(line=el, character=ec),
                ),
                message=(
                    f"Missing @AccessMode annotation(s).\n"
                    f"Suggested:\n{annotations_str}\n"
                    f"({s.confidence:.0%} confidence)\n"
                    f"{s.reasoning}"
                ),
                severity=lsp.DiagnosticSeverity.Warning,
                source="ril2m",
                code="missing-access-mode",
                data=json.dumps(
                    {
                        "method": s.method_name,
                        "class": s.class_name,
                        "annotations_java": annotations_str,
                        "file": s.file_path,
                    }
                ),
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

    # Cache and publish
    _suggestions.clear()
    for s in results:
        uri = _path_to_uri(s.file_path)
        _suggestions.setdefault(uri, []).append(s)

    for uri in _suggestions:
        _publish_diagnostics_for_file(uri)

    count = len(results)
    ls.show_message(
        f"RIL2M: Found {count} test(s) missing @AccessMode.",
        lsp.MessageType.Info,
    )

    return json.dumps(
        {
            "count": count,
            "suggestions": [
                {
                    "class": s.class_name,
                    "method": s.method_name,
                    "file": s.file_path,
                    "annotations_java": s.suggested_annotations_java,
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

    # Remove from cache and refresh diagnostics
    uri = _path_to_uri(file_path)
    if uri in _suggestions:
        _suggestions[uri] = [
            s for s in _suggestions[uri] if s.method_name != method_name
        ]
        _publish_diagnostics_for_file(uri)

    return json.dumps({"applied": True, "method": method_name})


@server.command("ril2m.applyAllSuggestions")
def cmd_apply_all(ls: LanguageServer, args: list) -> str:
    """Apply all cached annotation suggestions."""
    applied = 0
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

        path.write_text(source, encoding="utf-8")

    _suggestions.clear()
    # Clear all diagnostics
    for uri in list(_suggestions.keys()):
        server.publish_diagnostics(uri, [])

    ls.show_message(
        f"RIL2M: Applied {applied} annotation(s).", lsp.MessageType.Info
    )
    return json.dumps({"applied": applied})


def _insert_annotations(source: str, method_name: str, annotations_java: str) -> str:
    """Insert annotation lines before the method's @Test annotation."""
    if not annotations_java.strip():
        return source

    # Ensure @AccessMode import exists
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

    # Find the method
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

    # Fallback: insert directly above void methodName(
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

    return source  # unchanged


# ─── Code Actions (Quick Fix) ───────────────────────────────────────

@server.feature(lsp.TEXT_DOCUMENT_CODE_ACTION)
def code_action(params: lsp.CodeActionParams) -> list[lsp.CodeAction]:
    """Provide 'Apply @AccessMode(…)' quick fixes for ril2m diagnostics."""
    actions: list[lsp.CodeAction] = []
    uri = params.text_document.uri

    for diag in params.context.diagnostics:
        if diag.source != "ril2m" or diag.data is None:
            continue

        data = json.loads(diag.data) if isinstance(diag.data, str) else diag.data

        num_annotations = data.get("annotations_java", "").count("@AccessMode")
        actions.append(
            lsp.CodeAction(
                title=f"Apply {num_annotations} @AccessMode annotation(s) to {data['method']}",
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

        # "Apply" lens
        annotations_java = s.suggested_annotations_java
        num_am = len(s.suggested_access_modes)
        data = json.dumps(
            {
                "method": s.method_name,
                "class": s.class_name,
                "annotations_java": annotations_java,
                "file": s.file_path,
            }
        )
        lenses.append(
            lsp.CodeLens(
                range=range_,
                command=lsp.Command(
                    title=f"Apply {num_am} @AccessMode annotation(s)",
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
