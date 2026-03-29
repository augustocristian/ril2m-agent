"""Annotator node – uses Ollama LLM + RAG context to suggest @AccessMode annotations."""

from __future__ import annotations

import logging

from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama

from agent.config import get_settings
from agent.nodes.rag import retrieve_similar
from agent.prompts import load_prompt
from agent.state import AgentState, AnnotationSuggestion, TestCase

logger = logging.getLogger(__name__)

# Load Jinja2 templates from agent/prompts/
_system_template = load_prompt("annotator_system.jinja")
_user_template = load_prompt("annotator_user.jinja")


def _build_similar_cases_ctx(docs: list) -> list[dict]:
    """Convert retrieved documents into template-friendly dicts."""
    cases = []
    for doc in docs:
        meta = doc.metadata
        cases.append(
            {
                "class_name": meta.get("class_name", "?"),
                "method_name": meta.get("method_name", "?"),
                "access_mode": meta.get("access_mode", "?"),
                "body": doc.page_content,
            }
        )
    return cases


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

    # Render system prompt once (it has no per-test variables)
    system_text = _system_template.render()

    suggestions: list[AnnotationSuggestion] = []

    for tc in state.non_annotated_tests:
        logger.info(
            "Suggesting annotation for %s.%s …", tc.class_name, tc.method_name
        )
        similar_docs = (
            retrieve_similar(tc) if state.rag_ready else []
        )
        similar_cases_ctx = _build_similar_cases_ctx(similar_docs)

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

        # Render user prompt with Jinja2
        user_text = _user_template.render(
            similar_cases=similar_cases_ctx,
            class_name=tc.class_name,
            method_name=tc.method_name,
            file_path=tc.file_path,
            method_body=tc.method_body,
        )

        prompt = ChatPromptTemplate.from_messages(
            [("system", system_text), ("human", user_text)]
        )
        chain = prompt | llm

        try:
            response = chain.invoke({})
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
