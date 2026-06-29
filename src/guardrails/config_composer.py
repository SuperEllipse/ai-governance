"""Compose runtime NeMo Guardrails config from selected policy modules."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

if TYPE_CHECKING:
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
        "parameters": {
            "temperature": llm_config.temperature,
            "max_tokens": llm_config.max_tokens,
        },
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
    elif safety.mode == "llama_guard":
        safety_model["parameters"]["base_url"] = safety.llama_guard_base_url
        if safety.llama_guard_api_key:
            safety_model["parameters"]["api_key"] = safety.llama_guard_api_key
        safety_model["parameters"]["max_tokens"] = 16
    else:
        safety_model["parameters"]["max_tokens"] = llm_config.max_tokens
        if llm_config.base_url:
            safety_model["parameters"]["base_url"] = llm_config.base_url
        if llm_config.api_key:
            safety_model["parameters"]["api_key"] = llm_config.api_key

    return [main_model, safety_model]


def _strip_self_check_flows(rails: dict[str, Any]) -> dict[str, Any]:
    """Remove self_check flows when using Llama Guard instead."""
    for rail_type in ("input", "output", "retrieval"):
        section = rails.get(rail_type, {})
        flows = section.get("flows")
        if isinstance(flows, list):
            section["flows"] = [
                f for f in flows if "self check" not in str(f).lower()
            ]
            rails[rail_type] = section
    return rails


def compose_config(
    policies: list[str],
    llm_config: LLMConfig,
    safety_config: SafetyModelConfig | None = None,
) -> Path:
    """Build a temporary guardrails config directory and return its path."""
    from src.llm.provider import SafetyModelConfig

    safety = safety_config or SafetyModelConfig()
    merged: dict[str, Any] = _load_yaml(BASE_DIR / "config.yml")

    for policy_key in policies:
        folder = POLICY_MAP.get(policy_key, policy_key)
        policy_cfg = _load_yaml(GUARDRAILS_ROOT / "policies" / folder / "config.yml")
        merged = _deep_merge(merged, policy_cfg)

    merged["models"] = _build_models_config(llm_config, safety)

    rails = merged.get("rails", {})
    if safety.mode == "llama_guard":
        rails = _strip_self_check_flows(rails)
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


def resolve_rails_layout(source_dir: Path | str) -> tuple[Path, Path, str]:
    """Return (rails_root, config_subdir, config_id) for the NeMo server API.

    NeMo expects ``rails_config_path`` to be a parent directory whose immediate
    child folders (each containing ``config.yml``) are config ids — e.g.
    ``guardrails/base/`` → root ``guardrails/``, id ``base``.
    """
    src = Path(source_dir).resolve()
    default_id = os.environ.get("GUARDRAILS_CONFIG_ID", "base")

    if (src / "config.yml").exists() or (src / "config.yaml").exists():
        if src.name == default_id and src.parent != src:
            return src.parent, src, default_id
        return src, src, src.name

    base_dir = src / default_id
    if (base_dir / "config.yml").exists() or (base_dir / "config.yaml").exists():
        return src, base_dir, default_id

    return src, src, default_id


def set_server_env(llm_config: LLMConfig) -> dict[str, str]:
    """Environment variables for nemoguardrails server subprocess."""
    env = os.environ.copy()
    env["MAIN_MODEL_ENGINE"] = "openai"
    env["MAIN_MODEL_NAME"] = llm_config.model
    env["OPENAI_API_KEY"] = llm_config.api_key or env.get("OPENAI_API_KEY", "")
    if llm_config.base_url:
        env["MAIN_MODEL_BASE_URL"] = llm_config.base_url
    return env


def _patch_openai_models(
    config_path: Path,
    base_url: str,
    model_name: str,
    api_key: str,
    max_tokens: int | None = None,
    *,
    llama_guard_base_url: str = "",
    llama_guard_model: str = "",
    llama_guard_api_key: str = "",
    strip_self_check: bool = False,
) -> None:
    if max_tokens is None:
        max_tokens = int(os.getenv("CAIIS_MAX_TOKENS", "1024"))
    merged = _load_yaml(config_path)
    models = merged.get("models") or []
    for model in models:
        if model.get("engine") != "openai":
            continue
        params = model.setdefault("parameters", {})
        model_type = model.get("type", "")
        if model_type == "safety_check" and llama_guard_base_url:
            params["base_url"] = llama_guard_base_url
            if llama_guard_api_key:
                params["api_key"] = llama_guard_api_key
            if llama_guard_model:
                model["model"] = llama_guard_model
            params["max_tokens"] = 16
            continue
        if base_url:
            params["base_url"] = base_url
        if api_key:
            params["api_key"] = api_key
        if model_name:
            model["model"] = model_name
        params["max_tokens"] = max_tokens

    if strip_self_check:
        merged["rails"] = _strip_self_check_flows(merged.get("rails", {}))

    with config_path.open("w") as f:
        yaml.dump(merged, f, default_flow_style=False)


def get_rails_config_parent(source_dir: Path | str) -> Path:
    """Return the NeMo ``rails_config_path`` parent (e.g. ``guardrails/`` for ``base/``)."""
    rails_root, _, _ = resolve_rails_layout(source_dir)
    return rails_root


def prepare_server_config_from_env(source_dir: Path | str) -> Path:
    """Return NeMo ``rails_config_path`` with optional MAIN_MODEL_* env overrides.

    NeMo server only patches the main model from env; safety_check rails still
    read config.yml. This ensures both main and safety_check models use CAIIS.

    Always returns a directory layout where ``<root>/<config_id>/config.yml``
    exists (never a bare single-config temp dir with an unstable id).
    """
    rails_root, config_subdir, config_id = resolve_rails_layout(source_dir)
    base_url = os.environ.get("MAIN_MODEL_BASE_URL", "").strip()
    model_name = os.environ.get("MAIN_MODEL_NAME", "").strip()
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    safety_mode = os.environ.get("DEFAULT_SAFETY_MODE", os.environ.get("SAFETY_MODE", "")).strip().lower()
    from src.llm.caiis_url import resolve_llama_guard_base_url

    llama_guard_base_url = resolve_llama_guard_base_url()
    llama_guard_model = os.environ.get("LLAMA_GUARD_MODEL", "").strip()
    llama_guard_api_key = os.environ.get("CDP_TOKEN", api_key).strip()
    strip_self_check = safety_mode == "llama_guard"

    if (
        not base_url
        and not model_name
        and not api_key
        and not strip_self_check
        and not llama_guard_base_url
    ):
        return rails_root

    tmp_root = Path(tempfile.mkdtemp(prefix="nemo_guardrails_server_"))
    dest_subdir = tmp_root / config_id
    shutil.copytree(config_subdir, dest_subdir, dirs_exist_ok=True)
    config_path = dest_subdir / "config.yml"

    _patch_openai_models(
        config_path,
        base_url,
        model_name,
        api_key,
        llama_guard_base_url=llama_guard_base_url if strip_self_check else "",
        llama_guard_model=llama_guard_model,
        llama_guard_api_key=llama_guard_api_key,
        strip_self_check=strip_self_check,
    )
    return tmp_root
