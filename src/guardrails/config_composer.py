"""Compose runtime NeMo Guardrails config from selected policy modules."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

import yaml

from src.llm.provider import LLMConfig, SafetyModelConfig

PROJECT_ROOT = Path(__file__).resolve().parents[2]
GUARDRAILS_ROOT = PROJECT_ROOT / "guardrails"
BASE_DIR = GUARDRAILS_ROOT / "base"

POLICY_MAP = {
    "pii": "pii",
    "jailbreak": "jailbreak",
    "topic": "topic_control",
    "toxicity": "toxicity_bias",
    "prompt_injection": "prompt_injection",
}


def _dedupe_flows(flows: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for flow in flows:
        if flow not in seen:
            seen.add(flow)
            result.append(flow)
    return result


def _deep_merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        elif key in result and isinstance(result[key], list) and isinstance(value, list):
            result[key] = result[key] + value
        else:
            result[key] = value
    return result


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open() as f:
        return yaml.safe_load(f) or {}


def _build_models_config(llm_config: LLMConfig, safety: SafetyModelConfig) -> list[dict]:
    main_model = {
        "type": "main",
        "engine": "openai",
        "model": llm_config.model,
        "parameters": {"temperature": llm_config.temperature},
    }
    if llm_config.base_url:
        main_model["parameters"]["base_url"] = llm_config.base_url
    if llm_config.api_key:
        main_model["parameters"]["api_key"] = llm_config.api_key

    safety_engine = safety.safety_engine()
    safety_model: dict[str, Any] = {
        "type": "safety_check",
        "engine": safety_engine,
        "model": safety.safety_model_name(llm_config),
        "parameters": {"temperature": 0.0},
    }
    if safety_engine == "nim":
        safety_model["parameters"]["base_url"] = safety.nim_base_url
        if safety.nim_api_key:
            safety_model["parameters"]["api_key"] = safety.nim_api_key
    else:
        if llm_config.base_url:
            safety_model["parameters"]["base_url"] = llm_config.base_url
        if llm_config.api_key:
            safety_model["parameters"]["api_key"] = llm_config.api_key

    return [main_model, safety_model]


def compose_config(
    policies: list[str],
    llm_config: LLMConfig,
    safety_config: SafetyModelConfig | None = None,
) -> Path:
    """Build a temporary guardrails config directory and return its path."""
    safety = safety_config or SafetyModelConfig()
    merged: dict[str, Any] = _load_yaml(BASE_DIR / "config.yml")

    for policy_key in policies:
        folder = POLICY_MAP.get(policy_key, policy_key)
        policy_cfg = _load_yaml(GUARDRAILS_ROOT / "policies" / folder / "config.yml")
        merged = _deep_merge(merged, policy_cfg)

    merged["models"] = _build_models_config(llm_config, safety)

    rails = merged.get("rails", {})
    base_rails = _load_yaml(BASE_DIR / "config.yml").get("rails", {})
    for rail_type in ("input", "output", "retrieval"):
        section = rails.get(rail_type, {})
        flows = section.get("flows")
        if isinstance(flows, list):
            base_flows = base_rails.get(rail_type, {}).get("flows", [])
            base_set = set(base_flows)
            policy_flows = [f for f in flows if f not in base_set]
            ordered = _dedupe_flows(policy_flows + base_flows)
            section["flows"] = ordered
            rails[rail_type] = section
    merged["rails"] = rails

    tmp_dir = Path(tempfile.mkdtemp(prefix="nemo_guardrails_"))
    shutil.copytree(BASE_DIR, tmp_dir, dirs_exist_ok=True)
    for policy_key in policies:
        folder = POLICY_MAP.get(policy_key, policy_key)
        src = GUARDRAILS_ROOT / "policies" / folder
        if src.exists():
            for item in src.iterdir():
                dest = tmp_dir / item.name
                if item.is_file():
                    shutil.copy2(item, dest)

    with (tmp_dir / "config.yml").open("w") as f:
        yaml.dump(merged, f, default_flow_style=False)

    prompts_src = BASE_DIR / "prompts.yml"
    if prompts_src.exists():
        shutil.copy2(prompts_src, tmp_dir / "prompts.yml")

    return tmp_dir


def get_server_config_path() -> Path:
    """Return root guardrails path for centralized server mode."""
    return GUARDRAILS_ROOT


def set_server_env(llm_config: LLMConfig) -> dict[str, str]:
    """Environment variables for nemoguardrails server subprocess."""
    env = os.environ.copy()
    env["MAIN_MODEL_ENGINE"] = "openai"
    env["MAIN_MODEL_NAME"] = llm_config.model
    env["OPENAI_API_KEY"] = llm_config.api_key or env.get("OPENAI_API_KEY", "")
    if llm_config.base_url:
        env["MAIN_MODEL_BASE_URL"] = llm_config.base_url
    return env
