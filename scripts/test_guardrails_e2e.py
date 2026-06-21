#!/usr/bin/env python3
"""End-to-end test for embedded guardrails: mortgage happy path and SSN PII block."""

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.guardrails.client import GuardrailsClient
from src.llm.provider import LLMConfig, SafetyModelConfig

MORTGAGE_QUERY = "What are your current 30-year mortgage rates?"
SSN_QUERY = "My SSN is 123-45-6789, what's my balance?"
POLICIES = ["pii", "jailbreak", "topic", "toxicity"]


async def main() -> None:
    llm_config = LLMConfig(api_key=os.getenv("OPENAI_API_KEY", ""))
    safety = SafetyModelConfig()
    client = GuardrailsClient(llm_config, safety)

    print("=== Mortgage happy path ===")
    mortgage = await client.run_query(MORTGAGE_QUERY, policies=POLICIES, mode="embedded")
    print(f"blocked={mortgage.blocked}")
    print(f"guarded (first 200 chars): {mortgage.guarded_response[:200]}")
    assert not mortgage.blocked
    assert "response=[" not in mortgage.guarded_response
    assert "internal error" not in mortgage.guarded_response.lower()
    assert "Guardrails error" not in mortgage.guarded_response
    assert mortgage.guarded_response.strip()
    print("PASS mortgage")

    print("\n=== SSN PII block ===")
    ssn = await client.run_query(SSN_QUERY, policies=POLICIES, mode="embedded")
    print(f"blocked={ssn.blocked}")
    print(f"output_vars={ssn.output_vars}")
    print(f"guarded (first 200 chars): {ssn.guarded_response[:200]}")
    assert ssn.blocked
    assert not ssn.output_vars.get("allowed", True)
    assert "Guardrails error" not in ssn.guarded_response
    assert "TCPTransport" not in ssn.guarded_response
    rail = ssn.output_vars.get("triggered_input_rail", "")
    assert "sensitive" in rail.lower() or "self check" in rail.lower()
    print("PASS ssn")


if __name__ == "__main__":
    asyncio.run(main())
