"""Annotator node – uses Ollama LLM + RAG context to suggest @AccessMode annotations."""

from __future__ import annotations

import logging

from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama

from agent.config import get_settings
from agent.nodes.rag import retrieve_similar
from agent.state import AgentState, AnnotationSuggestion, TestCase

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are an expert Java testing assistant. Your task is to suggest the correct
@AccessMode annotation for a Java test method.

@AccessMode is used to declare the database access mode required by a test:
- @AccessMode("READONLY")  – the test only reads data, no inserts/updates/deletes.
- @AccessMode("READWRITE") – the test reads AND writes (inserts, updates, or deletes).
- @AccessMode("WRITEONLY") – the test only writes data.
- @AccessMode("NOACCESS")  – the test does not access the database at all.

Analyze the test method body and its similar annotated examples to determine the
correct annotation.

Respond with EXACTLY this format (no extra text):
ANNOTATION: @AccessMode("<VALUE>")
CONFIDENCE: <0.0 to 1.0>
REASONING: <one-line explanation>
"""

_USER_PROMPT = """\
## Similar annotated test cases (for reference)

{similar_cases}

## Test method to annotate

Class: {class_name}
Method: {method_name}
File: {file_path}

```java
{method_body}
```

What @AccessMode annotation should this test have?
"""


def _format_similar_cases(docs: list) -> str:
    """Format retrieved documents into a readable block."""
    if not docs:
        return "(no similar annotated tests found)"
    parts = []
    for i, doc in enumerate(docs, 1):
        meta = doc.metadata
        parts.append(
            f"### Example {i}: {meta.get('class_name', '?')}.{meta.get('method_name', '?')}\n"
            f"Annotation: @AccessMode(\"{meta.get('access_mode', '?')}\")\n"
            f"```java\n{doc.page_content}\n```"
        )
    return "\n\n".join(parts)


def _parse_llm_response(text: str) -> tuple[str, float, str]:
    """Parse the structured LLM response."""
    annotation = "@AccessMode(\"READWRITE\")"  # safe default
    confidence = 0.5
    reasoning = "Could not parse LLM response."

    for line in text.strip().splitlines():
        line = line.strip()
        if line.upper().startswith("ANNOTATION:"):
            annotation = line.split(":", 1)[1].strip()
        elif line.upper().startswith("CONFIDENCE:"):
            try:
                confidence = float(line.split(":", 1)[1].strip())
            except ValueError:
                pass
        elif line.upper().startswith("REASONING:"):
            reasoning = line.split(":", 1)[1].strip()

    return annotation, confidence, reasoning


def suggest_annotations(state: AgentState) -> dict:
    """Generate @AccessMode suggestions for every non-annotated test case."""
    if not state.non_annotated_tests:
        logger.info("No non-annotated tests – nothing to suggest.")
        return {"current_step": "annotated"}

    settings = get_settings()
    llm = ChatOllama(
        model=settings.ollama_llm_model,
        base_url=settings.ollama_base_url,
        temperature=0.1,
    )

    prompt = ChatPromptTemplate.from_messages(
        [("system", _SYSTEM_PROMPT), ("human", _USER_PROMPT)]
    )
    chain = prompt | llm

    suggestions: list[AnnotationSuggestion] = []

    for tc in state.non_annotated_tests:
        logger.info(
            "Suggesting annotation for %s.%s …", tc.class_name, tc.method_name
        )
        similar_docs = (
            retrieve_similar(tc) if state.rag_ready else []
        )
        similar_text = _format_similar_cases(similar_docs)

        # Build similar TestCase references for the suggestion
        similar_tcs: list[TestCase] = []
        for doc in similar_docs:
            similar_tcs.append(
                TestCase(
                    file_path=doc.metadata.get("file_path", ""),
                    class_name=doc.metadata.get("class_name", ""),
                    method_name=doc.metadata.get("method_name", ""),
                    method_body=doc.page_content,
                    has_access_mode=True,
                    access_mode_value=doc.metadata.get("access_mode", ""),
                )
            )

        try:
            response = chain.invoke(
                {
                    "similar_cases": similar_text,
                    "class_name": tc.class_name,
                    "method_name": tc.method_name,
                    "file_path": tc.file_path,
                    "method_body": tc.method_body,
                }
            )
            annotation, confidence, reasoning = _parse_llm_response(
                response.content
            )
        except Exception as exc:
            logger.error("LLM call failed for %s.%s: %s", tc.class_name, tc.method_name, exc)
            annotation = "@AccessMode(\"READWRITE\")"
            confidence = 0.0
            reasoning = f"LLM error: {exc}"

        suggestions.append(
            AnnotationSuggestion(
                test_case=tc,
                suggested_annotation=annotation,
                confidence=confidence,
                reasoning=reasoning,
                similar_cases=similar_tcs,
            )
        )
        logger.info(
            "  -> %s (confidence: %.2f)", annotation, confidence
        )

    return {"suggestions": suggestions, "current_step": "annotated"}
