"""NeMo Guardrails hooks for the demo ``base`` config."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nemoguardrails.rails.llm.llmrails import LLMRails


def init(rails: LLMRails) -> None:
    """Register custom output parsers used by ``prompts.yml``."""
    from src.guardrails.output_parsers import self_check_yes_no

    rails.register_output_parser(self_check_yes_no, "self_check_yes_no")
