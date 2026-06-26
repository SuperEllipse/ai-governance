#!/usr/bin/env python3
"""Unit tests for reasoning-model self_check output parsing."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.guardrails.output_parsers import self_check_yes_no


def test_block_yes_with_thinking_prefix() -> None:
    response = (
        "<think>User asks about bitcoin investing.</think>\n\n"
        "Block: Yes\nViolated rule: investment advice"
    )
    assert self_check_yes_no(response)[0] is False


def test_explanatory_no_at_start_is_not_allow() -> None:
    """Nemotron-style prose must not be misread as allow via leading 'No'."""
    response = (
        "<think>off topic investment</think>\n\n"
        "This is investment advice and should be blocked.\nBlock: Yes"
    )
    assert self_check_yes_no(response)[0] is False


def test_block_no_allows() -> None:
    response = "Block: No"
    assert self_check_yes_no(response)[0] is True


def test_legacy_yes_answer() -> None:
    response = "Yes\nViolated rule: investment advice"
    assert self_check_yes_no(response)[0] is False


def main() -> int:
    tests = [
        test_block_yes_with_thinking_prefix,
        test_explanatory_no_at_start_is_not_allow,
        test_block_no_allows,
        test_legacy_yes_answer,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"\nAll {len(tests)} parser checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
