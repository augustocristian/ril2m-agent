"""Scanner node – finds Java test files and SystemResources.json in Maven projects."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from agent.state import AgentState, Resource

logger = logging.getLogger(__name__)

# Standard Maven test directories
_MAVEN_TEST_DIRS = ("src/test/java",)
_JAVA_EXT = ".java"


def _is_maven_project(path: Path) -> bool:
    """Check whether *path* looks like a Maven project (has a pom.xml)."""
    return (path / "pom.xml").is_file()


def _find_test_files(project_root: Path) -> list[str]:
    """Recursively find all .java files under Maven test source directories."""
    test_files: list[str] = []
    for test_dir_name in _MAVEN_TEST_DIRS:
        test_dir = project_root / test_dir_name
        if test_dir.is_dir():
            for java_file in test_dir.rglob(f"*{_JAVA_EXT}"):
                if java_file.is_file():
                    test_files.append(str(java_file))
    return test_files


def _find_system_resources(project_root: Path) -> list[Resource]:
    """Find and parse *SystemResources.json files in the project.

    The file is typically named <SUT_NAME>SystemResources.json and lives
    somewhere under the project root (often src/test/resources).
    """
    resources: list[Resource] = []

    for json_file in project_root.rglob("*SystemResources.json"):
        logger.info("Found SystemResources file: %s", json_file)
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
            # The file can be a list of resources or a dict with a resources key
            resource_list = data if isinstance(data, list) else data.get("resources", [])
            for entry in resource_list:
                if isinstance(entry, dict):
                    resources.append(
                        Resource(
                            res_id=entry.get("resID", entry.get("id", "")),
                            name=entry.get("name", ""),
                            resource_type=entry.get("type", entry.get("resourceType", "")),
                            extra={
                                k: v
                                for k, v in entry.items()
                                if k not in ("resID", "id", "name", "type", "resourceType")
                            },
                        )
                    )
        except Exception as exc:
            logger.warning("Failed to parse %s: %s", json_file, exc)

    return resources


def scan_project(state: AgentState) -> dict:
    """Scan *state.project_path* for Java test files and SystemResources.

    If the path points directly to a Maven project its test directory is
    scanned.  If the path contains multiple Maven modules (multi-module
    project) each module is scanned independently.
    """
    root = Path(state.project_path).resolve()
    logger.info("Scanning for Maven test files in: %s", root)

    if not root.is_dir():
        return {
            "errors": [f"Project path does not exist: {root}"],
            "current_step": "scan_failed",
        }

    test_files: list[str] = []
    resources: list[Resource] = []

    if _is_maven_project(root):
        test_files.extend(_find_test_files(root))
        resources.extend(_find_system_resources(root))

    # Also look one level deep for multi-module projects
    for child in root.iterdir():
        if child.is_dir() and _is_maven_project(child):
            test_files.extend(_find_test_files(child))
            resources.extend(_find_system_resources(child))

    if not test_files:
        return {
            "errors": [f"No Java test files found under: {root}"],
            "current_step": "scan_failed",
        }

    logger.info("Found %d test file(s), %d resource(s)", len(test_files), len(resources))
    return {
        "test_files": test_files,
        "resources": resources,
        "current_step": "scanned",
    }
