#!/usr/bin/env python3
"""Minimal repro for embedded guardrails path using sync check in a worker thread."""

import asyncio
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO)

from src.guardrails.client import GuardrailsClient, _prepare_worker_event_loop
from src.llm.provider import LLMConfig, SafetyModelConfig

QUERY = "What are your current 30-year mortgage rates?"
AGENT_RESPONSE = (
    "As of June 18, 2026, the current 30-year fixed mortgage rate is 6.375% "
    "with an APR of 6.498% and 0.75 points."
)
POLICIES = ["pii", "jailbreak", "topic", "toxicity"]


def run_sync_check() -> None:
    """Mirror the production embedded path: fresh loop + sync rails.check()."""
    from nemoguardrails.rails.llm.options import RailStatus, RailType

    client = GuardrailsClient(
        LLMConfig(
            api_key=os.getenv("OPENAI_API_KEY", ""),
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        ),
        SafetyModelConfig(),
    )
    _prepare_worker_event_loop()
    rails = client._create_embedded_rails(POLICIES)

    input_result = rails.check(
        messages=[{"role": "user", "content": QUERY}],
        rail_types=[RailType.INPUT],
    )
    print(f"Input status: {input_result.status}")
    print(f"Input content: {input_result.content[:120]}")

    output_result = rails.check(
        messages=[
            {"role": "user", "content": QUERY},
            {"role": "assistant", "content": AGENT_RESPONSE},
        ],
        rail_types=[RailType.OUTPUT],
    )
    print(f"Output status: {output_result.status}")
    print(f"Output content: {output_result.content[:120]}")

    assert input_result.status in {
        RailStatus.PASSED,
        RailStatus.MODIFIED,
        RailStatus.BLOCKED,
    }
    assert "response=[" not in output_result.content
    print("PASS")


async def main() -> None:
    await asyncio.to_thread(run_sync_check)


if __name__ == "__main__":
    asyncio.run(main())
