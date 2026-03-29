"""Parser node – extracts test methods and classifies them by @AccessMode."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from agent.state import AgentState, TestCase

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Regex-based Java parser (avoids hard dependency on full Java AST parsing)
# ---------------------------------------------------------------------------

# Matches @AccessMode("VALUE") or @AccessMode(value = "VALUE") etc.
_ACCESS_MODE_RE = re.compile(
    r'@AccessMode\s*\(\s*(?:value\s*=\s*)?["\']?(\w+)["\']?\s*\)',
)

# Matches any annotation line
_ANNOTATION_RE = re.compile(r"^\s*@(\w+(?:\([^)]*\))?)", re.MULTILINE)

# Matches a test method: annotations block + method signature + body
# Captures: everything from the first annotation before the method to the
# closing brace. Handles @Test, @ParameterizedTest, etc.
_TEST_METHOD_RE = re.compile(
    r"((?:^\s*@\w+(?:\([^)]*\))?\s*\n)+)"  # annotation block
    r"\s*(?:public\s+|protected\s+|private\s+)?"  # optional visibility
    r"(?:static\s+)?void\s+"  # return type
    r"(\w+)"  # method name
    r"\s*\([^)]*\)"  # parameters
    r"\s*(?:throws\s+[\w,\s]+)?"  # optional throws
    r"\s*\{",  # opening brace
    re.MULTILINE,
)

# Matches a class declaration to extract the class name
_CLASS_RE = re.compile(
    r"(?:public\s+)?class\s+(\w+)",
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

    # Find the class name
    class_match = _CLASS_RE.search(source)
    class_name = class_match.group(1) if class_match else "UnknownClass"

    annotated: list[TestCase] = []
    non_annotated: list[TestCase] = []

    for match in _TEST_METHOD_RE.finditer(source):
        annotations_block = match.group(1)
        method_name = match.group(2)

        # Check this is actually a test method (has @Test or similar)
        ann_lines = [
            line.strip()
            for line in annotations_block.strip().splitlines()
            if line.strip().startswith("@")
        ]

        is_test = any(
            a.startswith("@Test")
            or a.startswith("@ParameterizedTest")
            or a.startswith("@RepeatedTest")
            for a in ann_lines
        )
        if not is_test:
            continue

        body = _extract_method_body(source, match.start())

        access_mode_match = _ACCESS_MODE_RE.search(annotations_block)
        has_access_mode = access_mode_match is not None
        access_mode_value = (
            access_mode_match.group(1) if access_mode_match else None
        )

        tc = TestCase(
            file_path=file_path,
            class_name=class_name,
            method_name=method_name,
            method_body=body,
            annotations=ann_lines,
            has_access_mode=has_access_mode,
            access_mode_value=access_mode_value,
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
