"""Annotator node – uses Ollama LLM + RAG context to suggest RETORCH
@AccessMode annotations."""

from __future__ import annotations

import logging
import re

from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama

from agent.config import get_settings
from agent.nodes.rag import retrieve_similar
from agent.prompts import load_prompt
from agent.state import AccessMode, AgentState, AnnotationSuggestion, TestCase

logger = logging.getLogger(__name__)

# Load Jinja2 templates from agent/prompts/
_system_template = load_prompt("annotator_system.jinja")
_user_template = load_prompt("annotator_user.jinja")

# Parse RESOURCE lines from LLM output
_RESOURCE_RE = re.compile(
    r'RESOURCE:\s*resID\s*=\s*"([^"]+)"\s+'
    r"concurrency\s*=\s*(\d+)\s+"
    r"sharing\s*=\s*(true|false)\s+"
    r'accessMode\s*=\s*"([^"]+)"',
    re.IGNORECASE,
)


def _build_similar_cases_ctx(docs: list) -> list[dict]:
    """Convert retrieved documents into template-friendly dicts."""
    import json

    cases = []
    for doc in docs:
        meta = doc.metadata
        # Deserialize the access modes from JSON stored in metadata
        try:
            access_modes_raw = json.loads(meta.get("access_modes_json", "[]"))
        except (json.JSONDecodeError, TypeError):
            access_modes_raw = []

        am_strings = []
        for am in access_modes_raw:
            sharing_str = "true" if am.get("sharing", True) else "false"
            am_strings.append(
                f'@AccessMode(resID = "{am.get("resID", "?")}", '
                f'concurrency = {am.get("concurrency", 1)}, '
                f"sharing = {sharing_str}, "
                f'accessMode = "{am.get("accessMode", "?")}")'
            )

        cases.append(
            {
                "class_name": meta.get("class_name", "?"),
                "method_name": meta.get("method_name", "?"),
                "access_modes": am_strings,
                "body": doc.page_content,
            }
        )
    return cases


def _parse_llm_response(text: str) -> tuple[list[AccessMode], float, str]:
    """Parse the structured LLM response into AccessMode objects."""
    access_modes: list[AccessMode] = []
    confidence = 0.5
    reasoning = "Could not parse LLM response."

    for match in _RESOURCE_RE.finditer(text):
        access_modes.append(
            AccessMode(
                res_id=match.group(1),
                concurrency=int(match.group(2)),
                sharing=match.group(3).lower() == "true",
                access_mode=match.group(4),
            )
        )

    for line in text.strip().splitlines():
        line = line.strip()
        if line.upper().startswith("CONFIDENCE:"):
            try:
                confidence = float(line.split(":", 1)[1].strip())
            except ValueError:
                pass
        elif line.upper().startswith("REASONING:"):
            reasoning = line.split(":", 1)[1].strip()

    return access_modes, confidence, reasoning


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

    # Render system prompt once (includes resource list if available)
    resources_ctx = [
        {"res_id": r.res_id, "name": r.name, "resource_type": r.resource_type}
        for r in state.resources
    ]
    system_text = _system_template.render(resources=resources_ctx)

    suggestions: list[AnnotationSuggestion] = []

    for tc in state.non_annotated_tests:
        logger.info(
            "Suggesting annotations for %s.%s …", tc.class_name, tc.method_name
        )
        similar_docs = retrieve_similar(tc) if state.rag_ready else []
        similar_cases_ctx = _build_similar_cases_ctx(similar_docs)

        # Build similar TestCase references for the suggestion
        similar_tcs: list[TestCase] = []
        for doc in similar_docs:
            import json as _json

            try:
                am_raw = _json.loads(doc.metadata.get("access_modes_json", "[]"))
            except (TypeError, _json.JSONDecodeError):
                am_raw = []
            similar_tcs.append(
                TestCase(
                    file_path=doc.metadata.get("file_path", ""),
                    class_name=doc.metadata.get("class_name", ""),
                    method_name=doc.metadata.get("method_name", ""),
                    method_body=doc.page_content,
                    has_access_mode=True,
                    access_modes=[
                        AccessMode(
                            res_id=am.get("resID", ""),
                            concurrency=am.get("concurrency", 1),
                            sharing=am.get("sharing", True),
                            access_mode=am.get("accessMode", ""),
                        )
                        for am in am_raw
                    ],
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
            access_modes, confidence, reasoning = _parse_llm_response(
                response.content
            )
        except Exception as exc:
            logger.error(
                "LLM call failed for %s.%s: %s",
                tc.class_name,
                tc.method_name,
                exc,
            )
            access_modes = []
            confidence = 0.0
            reasoning = f"LLM error: {exc}"

        suggestions.append(
            AnnotationSuggestion(
                test_case=tc,
                suggested_access_modes=access_modes,
                confidence=confidence,
                reasoning=reasoning,
                similar_cases=similar_tcs,
            )
        )
        logger.info(
            "  -> %d annotation(s) suggested (confidence: %.2f)",
            len(access_modes),
            confidence,
        )
        for am in access_modes:
            logger.info("     %s", am.to_java())

    return {"suggestions": suggestions, "current_step": "annotated"}
