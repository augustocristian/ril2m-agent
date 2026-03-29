"""Tests for the RAG node (unit-level, no Ollama required)."""

import json

from agent.nodes.rag import _test_to_document
from agent.state import AccessMode, TestCase


class TestRagHelpers:
    def test_document_creation_single_access_mode(self):
        tc = TestCase(
            file_path="/tmp/Test.java",
            class_name="MyTest",
            method_name="testSomething",
            method_body="{ repo.findAll(); }",
            annotations=["@Test"],
            access_modes=[
                AccessMode(
                    res_id="Database",
                    concurrency=10,
                    sharing=True,
                    access_mode="READONLY",
                )
            ],
            has_access_mode=True,
        )
        doc = _test_to_document(tc)

        assert doc.page_content == "{ repo.findAll(); }"
        assert doc.metadata["class_name"] == "MyTest"
        assert doc.metadata["method_name"] == "testSomething"
        assert doc.metadata["num_access_modes"] == 1

        # Check JSON metadata
        am_json = json.loads(doc.metadata["access_modes_json"])
        assert len(am_json) == 1
        assert am_json[0]["resID"] == "Database"
        assert am_json[0]["accessMode"] == "READONLY"

    def test_document_creation_multiple_access_modes(self):
        tc = TestCase(
            file_path="/tmp/Test.java",
            class_name="MyTest",
            method_name="testMulti",
            method_body="{ login(); viewCourse(); }",
            annotations=["@Test"],
            access_modes=[
                AccessMode("LoginService", 10, True, "READONLY"),
                AccessMode("Course", 1, False, "READWRITE"),
            ],
            has_access_mode=True,
        )
        doc = _test_to_document(tc)

        assert doc.metadata["num_access_modes"] == 2

        am_json = json.loads(doc.metadata["access_modes_json"])
        assert len(am_json) == 2
        assert am_json[0]["resID"] == "LoginService"
        assert am_json[1]["resID"] == "Course"

        # Check Java rendering in metadata
        java_str = doc.metadata["access_modes_java"]
        assert "@AccessMode(" in java_str
        assert "LoginService" in java_str
        assert "Course" in java_str

    def test_document_without_access_mode(self):
        tc = TestCase(
            file_path="/tmp/Test.java",
            class_name="MyTest",
            method_name="testOther",
            method_body="{ repo.save(x); }",
            annotations=["@Test"],
            access_modes=[],
            has_access_mode=False,
        )
        doc = _test_to_document(tc)

        assert doc.metadata["num_access_modes"] == 0
        am_json = json.loads(doc.metadata["access_modes_json"])
        assert am_json == []
