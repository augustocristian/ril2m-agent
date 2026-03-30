"""Tests for the parser node."""

from agent.nodes.parser import parse_tests
from agent.nodes.scanner import scan_project
from agent.state import AgentState


class TestParser:
    def test_parse_classifies_tests(self, maven_project):
        state = AgentState(project_path=str(maven_project))
        scan_result = scan_project(state)
        state.test_files = scan_result["test_files"]

        result = parse_tests(state)

        assert result["current_step"] == "parsed"
        annotated = result["annotated_tests"]
        non_annotated = result["non_annotated_tests"]

        # AnnotatedTest.java has 3 annotated methods
        assert len(annotated) == 3
        # UnannotatedTest.java has 3 unannotated methods
        assert len(non_annotated) == 3

    def test_annotated_tests_have_access_modes(self, maven_project):
        state = AgentState(project_path=str(maven_project))
        scan_result = scan_project(state)
        state.test_files = scan_result["test_files"]
        result = parse_tests(state)

        for tc in result["annotated_tests"]:
            assert tc.has_access_mode is True
            assert len(tc.access_modes) >= 1

    def test_multi_annotation_parsing(self, maven_project):
        """Test that multiple @AccessMode per method are parsed correctly."""
        state = AgentState(project_path=str(maven_project))
        scan_result = scan_project(state)
        state.test_files = scan_result["test_files"]
        result = parse_tests(state)

        # Find forumNewEntryTest which has 3 @AccessMode annotations
        forum_test = None
        for tc in result["annotated_tests"]:
            if tc.method_name == "forumNewEntryTest":
                forum_test = tc
                break

        assert forum_test is not None
        assert len(forum_test.access_modes) == 3

        res_ids = [am.res_id for am in forum_test.access_modes]
        assert "loginservice" in res_ids
        assert "openvidu" in res_ids
        assert "course" in res_ids

        # Check specific attributes
        course_am = next(am for am in forum_test.access_modes if am.res_id == "course")
        assert course_am.concurrency == 1
        assert course_am.sharing is False
        assert course_am.access_mode == "READWRITE"

    def test_access_mode_attributes(self, maven_project):
        """Test that all @AccessMode attributes are parsed correctly."""
        state = AgentState(project_path=str(maven_project))
        scan_result = scan_project(state)
        state.test_files = scan_result["test_files"]
        result = parse_tests(state)

        # Find testViewCourse
        view_test = None
        for tc in result["annotated_tests"]:
            if tc.method_name == "testViewCourse":
                view_test = tc
                break

        assert view_test is not None
        assert len(view_test.access_modes) == 2

        login_am = next(am for am in view_test.access_modes if am.res_id == "loginservice")
        assert login_am.concurrency == 10
        assert login_am.sharing is True
        assert login_am.access_mode == "READONLY"

    def test_non_annotated_tests_lack_access_mode(self, maven_project):
        state = AgentState(project_path=str(maven_project))
        scan_result = scan_project(state)
        state.test_files = scan_result["test_files"]
        result = parse_tests(state)

        for tc in result["non_annotated_tests"]:
            assert tc.has_access_mode is False
            assert len(tc.access_modes) == 0

    def test_to_java_roundtrip(self, maven_project):
        """Test that to_java() produces valid annotation syntax."""
        state = AgentState(project_path=str(maven_project))
        scan_result = scan_project(state)
        state.test_files = scan_result["test_files"]
        result = parse_tests(state)

        for tc in result["annotated_tests"]:
            for am in tc.access_modes:
                java = am.to_java()
                assert java.startswith("@AccessMode(")
                assert f'resID = "{am.res_id}"' in java
                assert f'accessMode = "{am.access_mode}"' in java

    def test_parse_no_files(self):
        state = AgentState(project_path="/tmp", test_files=[])
        result = parse_tests(state)

        assert result["current_step"] == "parsed"
        assert len(result["annotated_tests"]) == 0
        assert len(result["non_annotated_tests"]) == 0
