"""Scanner node – finds Java test files and .retorch/SystemResources.json."""

from __future__ import annotations

import logging
from pathlib import Path

from agent.resources import find_resources_file, load_resources_list
from agent.state import AgentState

logger = logging.getLogger(__name__)

_MAVEN_TEST_DIRS = ("src/test/java",)
_JAVA_EXT = ".java"


def _is_maven_project(path: Path) -> bool:
    return (path / "pom.xml").is_file()


def _find_test_files(project_root: Path) -> list[str]:
    test_files: list[str] = []
    for test_dir_name in _MAVEN_TEST_DIRS:
        test_dir = project_root / test_dir_name
        if test_dir.is_dir():
            for java_file in test_dir.rglob(f"*{_JAVA_EXT}"):
                if java_file.is_file():
                    test_files.append(str(java_file))
    return test_files


def scan_project(state: AgentState) -> dict:
    """Scan for Java test files and .retorch/*SystemResources.json."""
    root = Path(state.project_path).resolve()
    logger.info("Scanning for Maven test files in: %s", root)

    if not root.is_dir():
        return {
            "errors": [f"Project path does not exist: {root}"],
            "current_step": "scan_failed",
        }

    test_files: list[str] = []

    if _is_maven_project(root):
        test_files.extend(_find_test_files(root))

    # Multi-module projects
    for child in root.iterdir():
        if child.is_dir() and _is_maven_project(child):
            test_files.extend(_find_test_files(child))

    if not test_files:
        return {
            "errors": [f"No Java test files found under: {root}"],
            "current_step": "scan_failed",
        }

    # Find and load .retorch resources
    resources_file = find_resources_file(root)
    resources = []
    resources_file_path = ""

    if resources_file:
        resources_file_path = str(resources_file)
        resources = load_resources_list(resources_file)
        logger.info(
            "Found %d resource(s) in %s", len(resources), resources_file
        )
    else:
        logger.warning("No .retorch/*SystemResources.json found in %s", root)

    logger.info("Found %d test file(s)", len(test_files))
    return {
        "test_files": test_files,
        "resources": resources,
        "resources_file_path": resources_file_path,
        "current_step": "scanned",
    }
