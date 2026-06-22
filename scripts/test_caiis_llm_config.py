#!/usr/bin/env python3
"""Verify CAIIS LLM config flows to CrewAI without live network calls."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.llm.provider import (
    create_crewai_llm,
    default_caiis_config,
    default_llm_config,
    detect_default_provider,
    get_llm_config,
    is_caiis_configured,
)


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_detect_default_provider() -> None:
    env = {
        "CAIIS_BASE_URL": "https://caiis.example.com/namespaces/serving-default/endpoints/demo/v1",
        "CAIIS_MODEL": "nvidia/llama-3.3-nemotron-super-49b-v1",
        "CDP_TOKEN": "test-cdp-token",
    }
    with patch.dict(os.environ, env, clear=True):
        _assert(is_caiis_configured(), "CAIIS should be configured with real base URL")
        _assert(
            detect_default_provider() == "openai",
            "default provider should be openai unless DEFAULT_LLM_PROVIDER is set",
        )
    with patch.dict(os.environ, {**env, "DEFAULT_LLM_PROVIDER": "caiis"}, clear=True):
        _assert(
            detect_default_provider() == "caiis",
            "DEFAULT_LLM_PROVIDER=caiis should select caiis",
        )


def test_get_llm_config_caiis() -> None:
    env = {
        "CAIIS_BASE_URL": "https://caiis.example.com/v1",
        "CAIIS_MODEL": "nvidia/llama-3.3-nemotron-super-49b-v1",
        "CDP_TOKEN": "test-cdp-token",
    }
    with patch.dict(os.environ, env, clear=True):
        cfg = get_llm_config(provider="caiis")
        _assert(cfg.provider == "caiis", "provider should be caiis")
        _assert(cfg.base_url == env["CAIIS_BASE_URL"], "base_url should match CAIIS_BASE_URL")
        _assert(cfg.api_key == env["CDP_TOKEN"], "api_key should use CDP_TOKEN")
        _assert(
            cfg.model == env["CAIIS_MODEL"],
            "model should match CAIIS_MODEL",
        )


def test_create_crewai_llm_routes_openai_client() -> None:
    cfg = default_caiis_config()
    cfg = type(cfg)(
        provider="caiis",
        model="nvidia/llama-3.3-nemotron-super-49b-v1",
        base_url="https://caiis.example.com/v1",
        api_key="test-cdp-token",
        temperature=cfg.temperature,
    )
    llm = create_crewai_llm(cfg)
    _assert(
        llm.__class__.__name__ == "OpenAICompletion",
        f"expected OpenAICompletion, got {llm.__class__.__name__}",
    )
    _assert(getattr(llm, "provider", None) == "openai", "CrewAI provider should be openai")
    _assert(
        getattr(llm, "base_url", None) == "https://caiis.example.com/v1",
        "base_url should point at CAIIS",
    )
    _assert(getattr(llm, "api_key", None) == "test-cdp-token", "api_key should be CDP token")
    _assert(
        getattr(llm, "model", None) == "nvidia/llama-3.3-nemotron-super-49b-v1",
        "model name should be preserved for CAIIS",
    )


def test_default_llm_config_prefers_openai() -> None:
    env = {
        "CAIIS_BASE_URL": "https://caiis.example.com/v1",
        "OPENAI_API_KEY": "sk-openai-key",
        "CDP_TOKEN": "test-cdp-token",
    }
    with patch.dict(os.environ, env, clear=True):
        cfg = default_llm_config()
        _assert(cfg.provider == "openai", "default_llm_config should default to openai")
        _assert(cfg.model == "gpt-4o-mini", "default should use gpt-4o-mini")

    with patch.dict(os.environ, {**env, "DEFAULT_LLM_PROVIDER": "caiis"}, clear=True):
        cfg = default_llm_config()
        _assert(
            cfg.provider == "caiis",
            "default_llm_config should pick caiis when DEFAULT_LLM_PROVIDER=caiis",
        )
        _assert(cfg.base_url == env["CAIIS_BASE_URL"], "default should use CAIIS base URL")


def test_guardrails_server_config_patch() -> None:
    from src.guardrails.config_composer import prepare_server_config_from_env

    env = {
        "MAIN_MODEL_BASE_URL": "https://caiis.example.com/v1",
        "MAIN_MODEL_NAME": "nvidia/llama-3.3-nemotron-super-49b-v1",
        "OPENAI_API_KEY": "test-cdp-token",
    }
    with patch.dict(os.environ, env, clear=True):
        runtime = prepare_server_config_from_env(ROOT / "guardrails" / "base")
        import yaml

        with (runtime / "config.yml").open() as f:
            config = yaml.safe_load(f)
        for model in config["models"]:
            if model.get("engine") != "openai":
                continue
            params = model.get("parameters", {})
            _assert(
                params.get("base_url") == env["MAIN_MODEL_BASE_URL"],
                f"{model['type']} model should use MAIN_MODEL_BASE_URL",
            )
            _assert(
                model.get("model") == env["MAIN_MODEL_NAME"],
                f"{model['type']} model name should be patched",
            )


def main() -> int:
    tests = [
        test_detect_default_provider,
        test_get_llm_config_caiis,
        test_create_crewai_llm_routes_openai_client,
        test_default_llm_config_prefers_openai,
        test_guardrails_server_config_patch,
    ]
    for test in tests:
        name = test.__name__
        print(f"PASS {name}")
        test()
    print(f"\nAll {len(tests)} CAIIS config checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
