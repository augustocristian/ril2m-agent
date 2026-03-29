"""PR Creator node – applies suggested annotations and opens a GitHub PR."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from git import Repo
from github import Auth, Github

from agent.config import get_settings
from agent.state import AgentState, AnnotationSuggestion

logger = logging.getLogger(__name__)

_BRANCH_NAME = "ril2m/add-access-mode-annotations"


def _apply_annotation(suggestion: AnnotationSuggestion) -> bool:
    """Insert the suggested @AccessMode annotation into the source file.

    Returns True if the file was modified, False otherwise.
    """
    file_path = Path(suggestion.test_case.file_path)
    if not file_path.is_file():
        logger.warning("File not found: %s", file_path)
        return False

    source = file_path.read_text(encoding="utf-8")

    # Ensure the @AccessMode import exists
    access_mode_import = "import giis.visualassert.portable.AccessMode;"
    if "import" in source and "AccessMode" not in source:
        # Insert after the last import statement
        last_import = max(
            (m.end() for m in re.finditer(r"^import\s+[^;]+;", source, re.MULTILINE)),
            default=0,
        )
        if last_import > 0:
            source = (
                source[:last_import]
                + f"\n{access_mode_import}"
                + source[last_import:]
            )

    # Find the test method and insert the annotation before it
    tc = suggestion.test_case
    # Build a pattern to find the method declaration
    # Look for the @Test annotation line preceding the method
    pattern = re.compile(
        rf"([ \t]*@Test[^\n]*\n)"  # @Test annotation line
        rf"([ \t]*(?:public\s+|protected\s+|private\s+)?(?:static\s+)?void\s+{re.escape(tc.method_name)}\s*\()",
        re.MULTILINE,
    )

    match = pattern.search(source)
    if not match:
        # Fallback: try without @Test preceding directly
        pattern2 = re.compile(
            rf"([ \t]*)((?:public\s+|protected\s+|private\s+)?(?:static\s+)?void\s+{re.escape(tc.method_name)}\s*\()",
            re.MULTILINE,
        )
        match2 = pattern2.search(source)
        if not match2:
            logger.warning(
                "Could not locate method %s in %s", tc.method_name, file_path
            )
            return False
        indent = match2.group(1)
        insert_pos = match2.start()
        annotation_line = f"{indent}{suggestion.suggested_annotation}\n"
        source = source[:insert_pos] + annotation_line + source[insert_pos:]
    else:
        # Insert the annotation before @Test
        indent = re.match(r"([ \t]*)", match.group(1)).group(1)
        insert_pos = match.start()
        annotation_line = f"{indent}{suggestion.suggested_annotation}\n"
        source = source[:insert_pos] + annotation_line + source[insert_pos:]

    file_path.write_text(source, encoding="utf-8")
    logger.info(
        "Applied %s to %s.%s",
        suggestion.suggested_annotation,
        tc.class_name,
        tc.method_name,
    )
    return True


def create_pr(state: AgentState) -> dict:
    """Apply all annotation suggestions and create a GitHub Pull Request."""
    if not state.create_pr:
        logger.info("PR creation not requested – skipping.")
        return {"current_step": "done"}

    if not state.suggestions:
        logger.info("No suggestions to apply – skipping PR creation.")
        return {"current_step": "done"}

    settings = get_settings()

    if not settings.github_token:
        return {
            "errors": ["GITHUB_TOKEN is not set – cannot create PR."],
            "current_step": "pr_failed",
        }

    # 1. Apply annotations to files
    modified_files: list[str] = []
    for suggestion in state.suggestions:
        if _apply_annotation(suggestion):
            modified_files.append(suggestion.test_case.file_path)

    if not modified_files:
        return {
            "errors": ["No files were modified – nothing to commit."],
            "current_step": "pr_failed",
        }

    # 2. Commit changes with gitpython
    repo = Repo(state.project_path)

    # Create and checkout a new branch
    if _BRANCH_NAME in [b.name for b in repo.branches]:
        repo.git.checkout(_BRANCH_NAME)
    else:
        repo.git.checkout("-b", _BRANCH_NAME)

    # Stage modified files
    unique_files = list(set(modified_files))
    repo.index.add(unique_files)

    # Build commit message
    summary_lines = []
    for s in state.suggestions:
        summary_lines.append(
            f"  - {s.test_case.class_name}.{s.test_case.method_name}: "
            f"{s.suggested_annotation} (confidence: {s.confidence:.0%})"
        )
    commit_msg = (
        "Add @AccessMode annotations to test methods\n\n"
        "Annotations suggested by RIL2M Agent (RAG + Ollama):\n"
        + "\n".join(summary_lines)
    )
    repo.index.commit(commit_msg)

    # Push the branch
    origin = repo.remote("origin")
    origin.push(_BRANCH_NAME)
    logger.info("Pushed branch %s to origin.", _BRANCH_NAME)

    # 3. Create PR via PyGithub
    auth = Auth.Token(settings.github_token)
    gh = Github(auth=auth)
    gh_repo = gh.get_repo(f"{settings.github_owner}/{settings.github_repo}")

    pr_body = (
        "## @AccessMode Annotation Suggestions\n\n"
        "This PR was automatically generated by the **RIL2M Agent**.\n\n"
        "The agent used a RAG pipeline (Ollama embeddings + ChromaDB) to find "
        "similar annotated test cases and an LLM to suggest the appropriate "
        "`@AccessMode` annotation for each unannotated test method.\n\n"
        "### Suggestions\n\n"
        "| Class | Method | Annotation | Confidence |\n"
        "| ----- | ------ | ---------- | ---------- |\n"
    )
    for s in state.suggestions:
        pr_body += (
            f"| {s.test_case.class_name} | {s.test_case.method_name} "
            f"| `{s.suggested_annotation}` | {s.confidence:.0%} |\n"
        )
    pr_body += (
        "\n### Reasoning\n\n"
    )
    for s in state.suggestions:
        pr_body += (
            f"- **{s.test_case.class_name}.{s.test_case.method_name}**: "
            f"{s.reasoning}\n"
        )

    pr = gh_repo.create_pull(
        title="Add @AccessMode annotations to test methods",
        body=pr_body,
        head=_BRANCH_NAME,
        base=settings.github_base_branch,
    )

    logger.info("PR created: %s", pr.html_url)
    return {
        "pr_url": pr.html_url,
        "pr_created": True,
        "current_step": "done",
    }
