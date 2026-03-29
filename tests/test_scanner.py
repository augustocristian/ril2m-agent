"""Tests for the scanner node."""

from agent.nodes.scanner import scan_project
from agent.state import AgentState


class TestScanner:
    def test_scan_finds_java_files(self, maven_project):
        state = AgentState(project_path=str(maven_project))
        result = scan_project(state)

        assert result["current_step"] == "scanned"
        assert len(result["test_files"]) == 2
        filenames = [f.split("/")[-1].split("\\")[-1] for f in result["test_files"]]
        assert "AnnotatedTest.java" in filenames
        assert "UnannotatedTest.java" in filenames

    def test_scan_finds_system_resources(self, maven_project):
        state = AgentState(project_path=str(maven_project))
        result = scan_project(state)

        resources = result.get("resources", [])
        assert len(resources) == 4
        res_ids = [r.resource_id for r in resources]
        assert "loginservice" in res_ids
        assert "openvidu" in res_ids
        assert "course" in res_ids
        assert "mysql" in res_ids

    def test_scan_resources_have_correct_structure(self, maven_project):
        state = AgentState(project_path=str(maven_project))
        result = scan_project(state)

        resources = {r.resource_id: r for r in result.get("resources", [])}

        login = resources["loginservice"]
        assert login.resource_type == "LOGICAL"
        assert login.hierarchy_parent == ["mysql"]
        assert login.elasticity_model.elasticity == 5
        assert login.docker_image == "codeurjc/full-teaching_no-services-openvidu:latest"

        openvidu = resources["openvidu"]
        assert openvidu.resource_type == "PHYSICAL"
        assert openvidu.hierarchy_parent == []

    def test_scan_returns_resources_file_path(self, maven_project):
        state = AgentState(project_path=str(maven_project))
        result = scan_project(state)

        assert result.get("resources_file_path", "")
        assert "ExampleSystemResources.json" in result["resources_file_path"]

    def test_scan_empty_project(self, empty_project):
        state = AgentState(project_path=str(empty_project))
        result = scan_project(state)

        assert result["current_step"] == "scan_failed"
        assert len(result["errors"]) > 0

    def test_scan_nonexistent_path(self):
        state = AgentState(project_path="/nonexistent/path")
        result = scan_project(state)

        assert result["current_step"] == "scan_failed"
