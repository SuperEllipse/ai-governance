#!/usr/bin/env python3
"""Test rails.check() API for guardrails-only pattern."""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.guardrails.config_composer import compose_config
from src.llm.provider import LLMConfig, SafetyModelConfig

QUERY = "What are your current 30-year mortgage rates?"
AGENT_RESP = (
    "As of June 18, 2026, the current 30-year fixed mortgage rate is 6.375% "
    "with an APR of 6.498% and 0.75 points."
)
POLICIES = ["pii", "jailbreak", "topic", "toxicity"]


def main() -> None:
    llm_config = LLMConfig(api_key=os.getenv("OPENAI_API_KEY", ""))
    safety = SafetyModelConfig()
    config_path = compose_config(POLICIES, llm_config, safety)

    from nemoguardrails import LLMRails, RailsConfig
    from nemoguardrails.rails.llm.options import RailType

    rails = LLMRails(RailsConfig.from_path(str(config_path)))

    print("=== INPUT CHECK ===")
    input_result = rails.check(
        [{"role": "user", "content": QUERY}],
        rail_types=[RailType.INPUT],
    )
    print(input_result)

    if input_result.status.value != "blocked":
        print("\n=== OUTPUT CHECK ===")
        output_result = rails.check(
            [
                {"role": "user", "content": QUERY},
                {"role": "assistant", "content": AGENT_RESP},
            ],
            rail_types=[RailType.OUTPUT],
        )
        print(output_result)


if __name__ == "__main__":
    main()
