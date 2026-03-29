"""LangGraph state definitions for the RIL2M agent."""

from __future__ import annotations

import operator
from dataclasses import dataclass, field
from typing import Annotated


@dataclass
class AccessMode:
    """A single RETORCH @AccessMode annotation.

    Example:
        @AccessMode(resID = "LoginService", concurrency = 10,
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
class Resource:
    """A resource declared in the SystemResources.json file."""

    res_id: str
    name: str = ""
    resource_type: str = ""
    extra: dict = field(default_factory=dict)


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
