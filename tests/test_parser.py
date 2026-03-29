"""Tests for the parser node."""

from agent.nodes.parser import parse_tests
from agent.nodes.scanner import scan_project
from agent.state import AgentState


class TestParser:
    def test_parse_classifies_tests(self, maven_project):
        # First scan
        state = AgentState(project_path=str(maven_project))
        scan_result = scan_project(state)
        state.test_files = scan_result["test_files"]

        # Then parse
        result = parse_tests(state)

        assert result["current_step"] == "parsed"
        annotated = result["annotated_tests"]
        non_annotated = result["non_annotated_tests"]

        # AnnotatedTest.java has 4 annotated methods
        assert len(annotated) == 4
        # UnannotatedTest.java has 3 unannotated methods
        assert len(non_annotated) == 3

    def test_annotated_tests_have_access_mode(self, maven_project):
        state = AgentState(project_path=str(maven_project))
        scan_result = scan_project(state)
        state.test_files = scan_result["test_files"]
        result = parse_tests(state)

        for tc in result["annotated_tests"]:
            assert tc.has_access_mode is True
            assert tc.access_mode_value in ("READONLY", "READWRITE", "WRITEONLY", "NOACCESS")

    def test_non_annotated_tests_lack_access_mode(self, maven_project):
        state = AgentState(project_path=str(maven_project))
        scan_result = scan_project(state)
        state.test_files = scan_result["test_files"]
        result = parse_tests(state)

        for tc in result["non_annotated_tests"]:
            assert tc.has_access_mode is False
            assert tc.access_mode_value is None

    def test_parse_no_files(self):
        state = AgentState(project_path="/tmp", test_files=[])
        result = parse_tests(state)

        assert result["current_step"] == "parsed"
        assert len(result["annotated_tests"]) == 0
        assert len(result["non_annotated_tests"]) == 0
