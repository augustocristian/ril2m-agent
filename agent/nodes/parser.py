"""Parser node – extracts test methods and classifies them by RETORCH @AccessMode."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from agent.state import AccessMode, AgentState, TestCase

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Regex patterns for RETORCH @AccessMode annotations
# ---------------------------------------------------------------------------

# Matches a single @AccessMode(...) with named attributes.
# Captures the full parenthesised content so we can parse attributes from it.
_ACCESS_MODE_RE = re.compile(
    r"@AccessMode\s*\(([^)]+)\)",
)

# Attribute extractors inside an @AccessMode(...)
_ATTR_RESID = re.compile(r'resID\s*=\s*"([^"]+)"')
_ATTR_CONCURRENCY = re.compile(r"concurrency\s*=\s*(\d+)")
_ATTR_SHARING = re.compile(r"sharing\s*=\s*(true|false)", re.IGNORECASE)
_ATTR_ACCESSMODE = re.compile(r'accessMode\s*=\s*"([^"]+)"')

# Matches a test method: annotations block + method signature + opening brace.
# The annotation block is everything from the first @ line preceding the method.
_TEST_METHOD_RE = re.compile(
    r"((?:^\s*@\w+(?:\([^)]*\))?\s*\n)+)"  # annotation block (one or more)
    r"\s*(?:public\s+|protected\s+|private\s+)?"  # optional visibility
    r"(?:static\s+)?void\s+"  # return type
    r"(\w+)"  # method name
    r"\s*\([^)]*\)"  # parameters
    r"\s*(?:throws\s+[\w,\s]+)?"  # optional throws
    r"\s*\{",  # opening brace
    re.MULTILINE,
)

# Matches a class declaration
_CLASS_RE = re.compile(r"(?:public\s+)?class\s+(\w+)")


def _parse_access_mode(attr_text: str) -> AccessMode | None:
    """Parse the attributes inside a single @AccessMode(...) annotation."""
    res_id_m = _ATTR_RESID.search(attr_text)
    concurrency_m = _ATTR_CONCURRENCY.search(attr_text)
    sharing_m = _ATTR_SHARING.search(attr_text)
    access_mode_m = _ATTR_ACCESSMODE.search(attr_text)

    if not res_id_m or not access_mode_m:
        return None

    return AccessMode(
        res_id=res_id_m.group(1),
        concurrency=int(concurrency_m.group(1)) if concurrency_m else 1,
        sharing=sharing_m.group(1).lower() == "true" if sharing_m else True,
        access_mode=access_mode_m.group(1),
    )


def _extract_method_body(source: str, method_start: int) -> str:
    """Extract the full method body starting from the opening '{' at *method_start*."""
    brace_count = 0
    start = source.index("{", method_start)
    i = start
    while i < len(source):
        if source[i] == "{":
            brace_count += 1
        elif source[i] == "}":
            brace_count -= 1
            if brace_count == 0:
                return source[start : i + 1]
        i += 1
    return source[start:]


def _parse_java_file(file_path: str) -> tuple[list[TestCase], list[TestCase]]:
    """Parse a single Java file, returning (annotated, non_annotated) test cases."""
    source = Path(file_path).read_text(encoding="utf-8", errors="replace")

    class_match = _CLASS_RE.search(source)
    class_name = class_match.group(1) if class_match else "UnknownClass"

    annotated: list[TestCase] = []
    non_annotated: list[TestCase] = []

    for match in _TEST_METHOD_RE.finditer(source):
        annotations_block = match.group(1)
        method_name = match.group(2)

        # Collect all annotation lines
        ann_lines = [
            line.strip()
            for line in annotations_block.strip().splitlines()
            if line.strip().startswith("@")
        ]

        # Check this is actually a test method
        is_test = any(
            a.startswith("@Test")
            or a.startswith("@ParameterizedTest")
            or a.startswith("@RepeatedTest")
            for a in ann_lines
        )
        if not is_test:
            continue

        body = _extract_method_body(source, match.start())

        # Parse all @AccessMode annotations
        access_modes: list[AccessMode] = []
        for am_match in _ACCESS_MODE_RE.finditer(annotations_block):
            am = _parse_access_mode(am_match.group(1))
            if am:
                access_modes.append(am)

        has_access_mode = len(access_modes) > 0

        tc = TestCase(
            file_path=file_path,
            class_name=class_name,
            method_name=method_name,
            method_body=body,
            annotations=ann_lines,
            access_modes=access_modes,
            has_access_mode=has_access_mode,
        )

        if has_access_mode:
            annotated.append(tc)
        else:
            non_annotated.append(tc)

    return annotated, non_annotated


def parse_tests(state: AgentState) -> dict:
    """Parse all discovered test files and classify test methods."""
    annotated_all: list[TestCase] = []
    non_annotated_all: list[TestCase] = []

    for file_path in state.test_files:
        try:
            annotated, non_annotated = _parse_java_file(file_path)
            annotated_all.extend(annotated)
            non_annotated_all.extend(non_annotated)
            logger.info(
                "%s: %d annotated, %d non-annotated",
                Path(file_path).name,
                len(annotated),
                len(non_annotated),
            )
        except Exception as exc:
            logger.warning("Failed to parse %s: %s", file_path, exc)

    if not non_annotated_all:
        logger.info("All test methods already have @AccessMode annotations.")

    logger.info(
        "Total: %d annotated, %d non-annotated test methods",
        len(annotated_all),
        len(non_annotated_all),
    )

    return {
        "annotated_tests": annotated_all,
        "non_annotated_tests": non_annotated_all,
        "current_step": "parsed",
    }
