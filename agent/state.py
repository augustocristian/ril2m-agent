"""LangGraph state definitions for the RIL2M agent."""

from __future__ import annotations

import operator
from dataclasses import dataclass, field
from typing import Annotated


@dataclass
class TestCase:
    """Represents a single Java test method."""

    file_path: str
    class_name: str
    method_name: str
    method_body: str
    annotations: list[str] = field(default_factory=list)
    has_access_mode: bool = False
    access_mode_value: str | None = None


@dataclass
class AnnotationSuggestion:
    """A suggested @AccessMode annotation for a test case."""

    test_case: TestCase
    suggested_annotation: str
    confidence: float
    reasoning: str
    similar_cases: list[TestCase] = field(default_factory=list)


@dataclass
class AgentState:
    """The state that flows through the LangGraph workflow."""

    # Input
    project_path: str = ""

    # Scanner output
    test_files: Annotated[list[str], operator.add] = field(default_factory=list)

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
