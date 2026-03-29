"""Tests for the RAG node (unit-level, no Ollama required)."""

from agent.nodes.rag import _test_to_document
from agent.state import TestCase


class TestRagHelpers:
    def test_document_creation(self):
        tc = TestCase(
            file_path="/tmp/Test.java",
            class_name="MyTest",
            method_name="testSomething",
            method_body='{ repo.findAll(); }',
            annotations=["@Test", '@AccessMode("READONLY")'],
            has_access_mode=True,
            access_mode_value="READONLY",
        )
        doc = _test_to_document(tc)

        assert doc.page_content == '{ repo.findAll(); }'
        assert doc.metadata["class_name"] == "MyTest"
        assert doc.metadata["method_name"] == "testSomething"
        assert doc.metadata["access_mode"] == "READONLY"

    def test_document_without_access_mode(self):
        tc = TestCase(
            file_path="/tmp/Test.java",
            class_name="MyTest",
            method_name="testOther",
            method_body='{ repo.save(x); }',
            annotations=["@Test"],
            has_access_mode=False,
            access_mode_value=None,
        )
        doc = _test_to_document(tc)

        assert doc.metadata["access_mode"] == ""
