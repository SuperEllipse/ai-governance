#!/usr/bin/env python3
"""Unit tests for guardrails response extraction helpers."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.guardrails.client import (  # noqa: E402
    _ensure_text_response,
    _extract_response_content,
    _looks_like_raw_generation_response,
)


def test_generation_response_repr_is_normalized() -> None:
    raw = (
        "response=[{'role': 'assistant', 'content': \"I'm sorry, an internal error has occurred.\"}] "
        "llm_output=None output_data=None log=None"
    )
    assert _looks_like_raw_generation_response(raw)
    assert (
        _ensure_text_response(raw)
        == "I'm sorry, an internal error has occurred."
    )


def test_rails_result_dict_extraction() -> None:
    payload = {
        "status": "blocked",
        "content": "This request is not allowed.",
        "rail": "self check input",
    }
    assert _extract_response_content(payload) == "This request is not allowed."


def test_message_list_extraction() -> None:
    payload = {
        "response": [
            {"role": "assistant", "content": "6.375% fixed rate"},
        ]
    }
    assert _extract_response_content(payload) == "6.375% fixed rate"


def main() -> None:
    test_generation_response_repr_is_normalized()
    test_rails_result_dict_extraction()
    test_message_list_extraction()
    print("PASS")


if __name__ == "__main__":
    main()
