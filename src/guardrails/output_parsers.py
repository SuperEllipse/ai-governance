"""Custom NeMo Guardrails output parsers for reasoning models (e.g. nemotron-3-nano)."""

from __future__ import annotations

import re
from typing import Sequence, Union

from nemoguardrails.llm.output_parsers import is_content_safe


def _strip_thinking_traces(text: str) -> str:
    cleaned = re.sub(
        r"<think>.*?</think>",
        "",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    return cleaned.strip()


def self_check_yes_no(response: str) -> Sequence[Union[bool, str]]:
    """Parse self_check_input/self_check_output for Yes=block, No=allow.

    Reasoning models often prepend ``<think>`` or explanatory text
    before Yes/No. The default ``is_content_safe`` parser only inspects the first
    two tokens, so a reply like ``No, this is investment advice`` is misread as
    allow and the server continues into dialog rails (which fail on nemotron).
    """
    cleaned = _strip_thinking_traces(response)

    block_match = re.search(
        r"(?:^|\n)\s*block\s*:\s*(yes|no)\b",
        cleaned,
        flags=re.IGNORECASE,
    )
    if block_match:
        return [False] if block_match.group(1).lower() == "yes" else [True]

    answer_match = re.search(
        r"(?:^|\n)\s*(?:answer|decision)\s*:\s*(yes|no)\b",
        cleaned,
        flags=re.IGNORECASE,
    )
    if answer_match:
        return [False] if answer_match.group(1).lower() == "yes" else [True]

    # Prefer the last standalone Yes/No — models often explain first, decide last.
    tail = cleaned[-240:]
    tail_match = re.findall(r"\b(yes|no)\b", tail, flags=re.IGNORECASE)
    if tail_match:
        decision = tail_match[-1].lower()
        return [False] if decision == "yes" else [True]

    return is_content_safe(cleaned)
