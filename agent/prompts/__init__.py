"""Jinja2 prompt template loader."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, Template

_PROMPTS_DIR = Path(__file__).parent
_env = Environment(
    loader=FileSystemLoader(str(_PROMPTS_DIR)),
    keep_trailing_newline=True,
    trim_blocks=True,
    lstrip_blocks=True,
)


def load_prompt(name: str) -> Template:
    """Load a Jinja2 template from the prompts directory.

    Args:
        name: Template filename (e.g. ``"annotator_system.jinja"``).
    """
    return _env.get_template(name)
