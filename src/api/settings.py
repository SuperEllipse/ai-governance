"""Map settings-panel values to LLM/safety configs and expose UI defaults."""

from __future__ import annotations

import os
from typing import Any

from src.api.schemas import RunSettings
from src.llm.caiis_url import (
    resolve_guardrails_server_url,
    resolve_llama_guard_base_url,
    resolve_llama_guard_model,
)
from src.llm.provider import (
    LLAMA_GUARD_DEFAULT_BASE_URL,
    LLMConfig,
    SafetyModelConfig,
    default_caiis_config,
    default_openai_config,
    detect_default_provider,
    detect_default_safety_mode,
    get_llm_config,
    is_caiis_configured,
    is_llama_guard_configured,
)

POLICY_OPTIONS: list[dict[str, str]] = [
    {"key": "pii", "label": "PII / Personal Data"},
    {"key": "jailbreak", "label": "Prompt Injection / Jailbreak"},
    {"key": "topic", "label": "Topic Control"},
    {"key": "toxicity", "label": "Toxicity / Bias"},
]

MODE_OPTIONS: list[dict[str, str]] = [
    {"key": "server", "label": "Centralized Server"},
    {"key": "embedded", "label": "Embedded"},
    {"key": "unguarded", "label": "Unguarded Only"},
]

SAFETY_OPTIONS: list[dict[str, str]] = [
    {"key": "self_check", "label": "Main LLM (self_check)"},
    {"key": "llama_guard", "label": "Llama Guard 3 (CAII)"},
    {"key": "nim", "label": "NVIDIA NIM"},
]


def default_guardrails_server_url() -> str:
    """Settings default: GUARDRAILS_PORT (CDSW often 8001), else resolved server URL."""
    port = os.getenv("GUARDRAILS_PORT", "").strip()
    if port:
        return f"http://127.0.0.1:{port}"
    resolved = resolve_guardrails_server_url()
    if resolved:
        return resolved
    return "http://127.0.0.1:8001"


def build_configs(settings: RunSettings) -> tuple[LLMConfig, SafetyModelConfig, str]:
    """Return ``(llm_config, safety_config, server_url)`` for a request.

    Blank fields fall back to server-side env defaults (``get_llm_config`` ignores
    empty overrides), so the browser never needs to hold the configured secrets.
    """
    llm_config = get_llm_config(
        provider=settings.provider,
        api_key=settings.api_key,
        base_url=settings.base_url,
        model=settings.model,
    )

    safety_kwargs: dict[str, Any] = {"mode": settings.safety_mode}
    if settings.nim_api_key:
        safety_kwargs["nim_api_key"] = settings.nim_api_key
    if settings.llama_guard_base_url:
        safety_kwargs["llama_guard_base_url"] = settings.llama_guard_base_url
    if settings.llama_guard_model:
        safety_kwargs["llama_guard_model"] = settings.llama_guard_model
    safety_config = SafetyModelConfig(**safety_kwargs)

    server_url = settings.server_url.strip() or default_guardrails_server_url()
    return llm_config, safety_config, server_url


def _provider_defaults(cfg: LLMConfig) -> dict[str, Any]:
    return {
        "base_url": cfg.base_url,
        "model": cfg.model,
        "max_tokens": cfg.max_tokens,
        "has_api_key": bool(cfg.api_key),
    }


def ui_defaults() -> dict[str, Any]:
    """Defaults for the settings panel. Never includes secret values."""
    llama_guard_base = resolve_llama_guard_base_url() or LLAMA_GUARD_DEFAULT_BASE_URL
    return {
        "default_provider": detect_default_provider(),
        "providers": {
            "openai": _provider_defaults(default_openai_config()),
            "caiis": _provider_defaults(default_caiis_config()),
        },
        "caiis_configured": is_caiis_configured(),
        "default_safety_mode": detect_default_safety_mode(),
        "safety_options": SAFETY_OPTIONS,
        "has_nim_api_key": bool(os.getenv("NVIDIA_API_KEY", "")),
        "llama_guard": {
            "base_url": llama_guard_base,
            "model": resolve_llama_guard_model(),
            "configured": is_llama_guard_configured(),
        },
        "default_mode": "server",
        "mode_options": MODE_OPTIONS,
        "default_server_url": default_guardrails_server_url(),
        "policy_options": POLICY_OPTIONS,
    }
