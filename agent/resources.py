"""Shared resource management for both the agent pipeline and VS Code LSP.

Handles loading, saving, and suggesting new resources in the RETORCH
.retorch/<SUT>SystemResources.json file.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from agent.state import (
    Capacity,
    ElasticityModel,
    NewResourceSuggestion,
    Resource,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Finding the resources file
# ---------------------------------------------------------------------------

def find_resources_file(project_root: str | Path) -> Path | None:
    """Find the *SystemResources.json file inside the .retorch/ directory.

    Searches:
      1. <project_root>/.retorch/*SystemResources.json
      2. Any child module's .retorch/ (multi-module Maven projects)

    Returns the first match or None.
    """
    root = Path(project_root).resolve()

    # Direct .retorch/ directory
    retorch_dir = root / ".retorch"
    if retorch_dir.is_dir():
        for f in retorch_dir.glob("*SystemResources.json"):
            return f

    # Multi-module: child/.retorch/
    for child in root.iterdir():
        if child.is_dir():
            child_retorch = child / ".retorch"
            if child_retorch.is_dir():
                for f in child_retorch.glob("*SystemResources.json"):
                    return f

    return None


# ---------------------------------------------------------------------------
# Loading resources
# ---------------------------------------------------------------------------

def load_resources(file_path: str | Path) -> dict[str, Resource]:
    """Load resources from a SystemResources.json file.

    The file uses a dict keyed by resource ID:
        { "loginservice": { "resourceID": "loginservice", ... }, ... }

    Returns a dict[resource_id, Resource].
    """
    path = Path(file_path)
    if not path.is_file():
        logger.warning("Resources file not found: %s", path)
        return {}

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to parse %s: %s", path, exc)
        return {}

    resources: dict[str, Resource] = {}
    for key, entry in data.items():
        if isinstance(entry, dict):
            resources[key] = Resource.from_dict(key, entry)

    logger.info("Loaded %d resource(s) from %s", len(resources), path)
    return resources


def load_resources_list(file_path: str | Path) -> list[Resource]:
    """Load resources as a flat list (convenience wrapper)."""
    return list(load_resources(file_path).values())


# ---------------------------------------------------------------------------
# Saving / adding resources
# ---------------------------------------------------------------------------

def save_resources(file_path: str | Path, resources: dict[str, Resource]) -> None:
    """Write the full resources dict back to the JSON file."""
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    data = {rid: r.to_dict() for rid, r in resources.items()}
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    logger.info("Saved %d resource(s) to %s", len(resources), path)


def add_resources(
    file_path: str | Path,
    new_resources: list[NewResourceSuggestion],
) -> list[str]:
    """Add new resources to the SystemResources.json file.

    Returns the list of resource IDs that were actually added (skips duplicates).
    """
    existing = load_resources(file_path)
    added: list[str] = []

    for nr in new_resources:
        rid = nr.resource.resource_id
        if rid in existing:
            logger.info("Resource %s already exists – skipping.", rid)
            continue
        existing[rid] = nr.resource
        added.append(rid)
        logger.info("Adding new resource: %s", rid)

    if added:
        save_resources(file_path, existing)

    return added


# ---------------------------------------------------------------------------
# Building a default Resource scaffold for new suggestions
# ---------------------------------------------------------------------------

def build_default_resource(
    resource_id: str,
    hierarchy_parent: list[str] | None = None,
    resource_type: str = "LOGICAL",
) -> Resource:
    """Create a Resource with sensible defaults for a new suggestion.

    The LLM can suggest a resource_id and parent; the rest gets reasonable
    defaults that the user can refine.
    """
    return Resource(
        resource_id=resource_id,
        resource_type=resource_type,
        hierarchy_parent=hierarchy_parent or [],
        replaceable=[],
        elasticity_model=ElasticityModel(
            elasticity_id=f"elasmodel{resource_id}",
            elasticity=5,
            elasticity_cost=15.0,
        ),
        minimal_capacities=[
            Capacity(name="memory", quantity=0.3),
            Capacity(name="processor", quantity=0.2),
            Capacity(name="storage", quantity=0.5),
        ],
        docker_image="",
    )


# ---------------------------------------------------------------------------
# Formatting for prompts (shared between annotator and LSP)
# ---------------------------------------------------------------------------

def format_resources_for_prompt(resources: list[Resource]) -> list[dict]:
    """Convert resources into dicts for use in Jinja prompts."""
    result = []
    for r in resources:
        parents = ", ".join(r.hierarchy_parent) if r.hierarchy_parent else "(root)"
        result.append(
            {
                "resource_id": r.resource_id,
                "resource_type": r.resource_type,
                "hierarchy_parent": parents,
                "elasticity": r.elasticity_model.elasticity,
                "docker_image": r.docker_image,
            }
        )
    return result
