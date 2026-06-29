#!/usr/bin/env python3
"""Unit tests for server-mode block vs internal-error handling."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.guardrails.client import (  # noqa: E402
    DEFAULT_BLOCK_REFUSAL,
    _blocked_refusal_result,
    _friendly_block_refusal,
    _is_successful_policy_block,
    _looks_like_internal_error,
    _server_internal_error_result,
)
from src.guardrails.violation_parser import (  # noqa: E402
    infer_policy_block_from_query,
    log_indicates_block_intent,
)


def test_internal_error_text_detected() -> None:
    assert _looks_like_internal_error("I'm sorry, an internal error has occurred.")


def test_successful_block_with_internal_content() -> None:
    output_vars = {
        "allowed": False,
        "triggered_input_rail": "self check input",
    }
    log_data = {"activated_rails": [{"name": "self check input", "stop": True}]}
    assert _is_successful_policy_block(output_vars, log_data)
    refusal = _friendly_block_refusal(
        "Should I buy Bitcoin?",
        output_vars["triggered_input_rail"],
        log_data,
        output_vars,
    )
    assert refusal == DEFAULT_BLOCK_REFUSAL


def test_log_block_intent_from_self_check_yes() -> None:
    log_data = {
        "llm_calls": [
            {
                "task": "self_check_input",
                "completion": "Block: Yes\nViolated rule: investment advice",
            }
        ]
    }
    assert log_indicates_block_intent(log_data)


def test_blocked_refusal_enriches_policy_reason() -> None:
    query = "Should I buy Bitcoin?"
    log_data = {"activated_rails": [{"name": "self check input", "stop": True}]}
    content, _, output_vars, blocked = _blocked_refusal_result(query, log_data, {})
    assert blocked is True
    assert content == DEFAULT_BLOCK_REFUSAL
    assert output_vars.get("allowed") is False
    assert "Investment" in output_vars.get("policy_reason", "")


def test_query_inference_for_investment_advice() -> None:
    reason = infer_policy_block_from_query("What ETF should I buy?")
    assert "Investment" in reason


def test_internal_error_without_block_metadata() -> None:
    output_vars = {"allowed": True}
    log_data = {}
    assert not _is_successful_policy_block(output_vars, log_data)
    msg, _, out, blocked = _server_internal_error_result(
        log_data, "I'm sorry, an internal error has occurred."
    )
    assert blocked is False
    assert out.get("allowed") is True
    assert out.get("guardrails_error")
    assert "CAIIS_MAX_TOKENS" in msg


def test_llama_guard_parser() -> None:
    from src.guardrails.llama_guard import parse_llama_guard_response

    safe, cat = parse_llama_guard_response("safe")
    assert safe is True
    assert cat == ""

    unsafe, cat = parse_llama_guard_response("unsafe\nS10")
    assert unsafe is False
    assert cat == "S10"


def main() -> int:
    tests = [
        test_internal_error_text_detected,
        test_successful_block_with_internal_content,
        test_log_block_intent_from_self_check_yes,
        test_blocked_refusal_enriches_policy_reason,
        test_query_inference_for_investment_advice,
        test_internal_error_without_block_metadata,
        test_llama_guard_parser,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"\nAll {len(tests)} server block handling checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
