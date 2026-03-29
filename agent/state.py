"""LangGraph state definitions for the RIL2M agent."""

from __future__ import annotations

import operator
from dataclasses import dataclass, field
from typing import Annotated


@dataclass
class AccessMode:
    """A single RETORCH @AccessMode annotation.

    Example:
        @AccessMode(resID = "loginservice", concurrency = 10,
                    sharing = true, accessMode = "READONLY")
    """

    res_id: str
    concurrency: int
    sharing: bool
    access_mode: str  # READONLY | READWRITE | WRITEONLY | NOACCESS

    def to_java(self) -> str:
        """Render back to Java annotation syntax."""
        sharing_str = "true" if self.sharing else "false"
        return (
            f'@AccessMode(resID = "{self.res_id}", '
            f"concurrency = {self.concurrency}, "
            f"sharing = {sharing_str}, "
            f'accessMode = "{self.access_mode}")'
        )


@dataclass
class ElasticityModel:
    """Elasticity configuration for a RETORCH resource."""

    elasticity_id: str = ""
    elasticity: int = 1
    elasticity_cost: float = 0.0


@dataclass
class Capacity:
    """A minimal capacity requirement (memory, processor, storage, etc.)."""

    name: str = ""
    quantity: float = 0.0


@dataclass
class Resource:
    """A resource declared in the .retorch SystemResources.json file.

    Matches the real RETORCH JSON format:
    {
      "resourceID": "loginservice",
      "resourceType": "LOGICAL",
      "hierarchyParent": ["mysql"],
      "replaceable": [],
      "elasticityModel": { ... },
      "minimalCapacities": [ ... ],
      "dockerImage": "database;mysql:5.7.21"
    }
    """

    resource_id: str = ""
    resource_type: str = "LOGICAL"
    hierarchy_parent: list[str] = field(default_factory=list)
    replaceable: list[str] = field(default_factory=list)
    elasticity_model: ElasticityModel = field(default_factory=ElasticityModel)
    minimal_capacities: list[Capacity] = field(default_factory=list)
    docker_image: str = ""

    def to_dict(self) -> dict:
        """Serialize to the RETORCH JSON format."""
        return {
            "hierarchyParent": self.hierarchy_parent,
            "replaceable": self.replaceable,
            "elasticityModel": {
                "elasticityID": self.elasticity_model.elasticity_id,
                "elasticity": self.elasticity_model.elasticity,
                "elasticityCost": self.elasticity_model.elasticity_cost,
            },
            "resourceType": self.resource_type,
            "resourceID": self.resource_id,
            "minimalCapacities": [
                {"name": c.name, "quantity": c.quantity}
                for c in self.minimal_capacities
            ],
            "dockerImage": self.docker_image,
        }

    @staticmethod
    def from_dict(key: str, data: dict) -> Resource:
        """Deserialize from the RETORCH JSON format."""
        em_raw = data.get("elasticityModel", {})
        return Resource(
            resource_id=data.get("resourceID", key),
            resource_type=data.get("resourceType", "LOGICAL"),
            hierarchy_parent=data.get("hierarchyParent", []),
            replaceable=data.get("replaceable", []),
            elasticity_model=ElasticityModel(
                elasticity_id=em_raw.get("elasticityID", ""),
                elasticity=em_raw.get("elasticity", 1),
                elasticity_cost=em_raw.get("elasticityCost", 0.0),
            ),
            minimal_capacities=[
                Capacity(name=c.get("name", ""), quantity=c.get("quantity", 0.0))
                for c in data.get("minimalCapacities", [])
            ],
            docker_image=data.get("dockerImage", ""),
        )


@dataclass
class NewResourceSuggestion:
    """A suggestion to add a new resource to SystemResources.json."""

    resource: Resource
    reasoning: str = ""


@dataclass
class TestCase:
    """Represents a single Java test method."""

    file_path: str
    class_name: str
    method_name: str
    method_body: str
    annotations: list[str] = field(default_factory=list)
    access_modes: list[AccessMode] = field(default_factory=list)
    has_access_mode: bool = False

    @property
    def access_modes_java(self) -> str:
        """Return all @AccessMode annotations as Java source lines."""
        return "\n".join(am.to_java() for am in self.access_modes)


@dataclass
class AnnotationSuggestion:
    """Suggested @AccessMode annotations for a test case."""

    test_case: TestCase
    suggested_access_modes: list[AccessMode] = field(default_factory=list)
    new_resources: list[NewResourceSuggestion] = field(default_factory=list)
    confidence: float = 0.0
    reasoning: str = ""
    similar_cases: list[TestCase] = field(default_factory=list)

    @property
    def suggested_annotations_java(self) -> str:
        """Return all suggested annotations as Java source lines."""
        return "\n".join(am.to_java() for am in self.suggested_access_modes)


@dataclass
class AgentState:
    """The state that flows through the LangGraph workflow."""

    # Input
    project_path: str = ""

    # Scanner output
    test_files: Annotated[list[str], operator.add] = field(default_factory=list)
    resources: list[Resource] = field(default_factory=list)
    resources_file_path: str = ""

    # Parser output
    annotated_tests: Annotated[list[TestCase], operator.add] = field(
        default_factory=list
    )
    non_annotated_tests: Annotated[list[TestCase], operator.add] = field(
        default_factory=list
    )

    # RAG output
    rag_ready: bool = False

    # Annotator output
    suggestions: Annotated[list[AnnotationSuggestion], operator.add] = field(
        default_factory=list
    )

    # PR creator output
    pr_url: str = ""
    pr_created: bool = False

    # Control
    create_pr: bool = False
    errors: Annotated[list[str], operator.add] = field(default_factory=list)
    current_step: str = ""
