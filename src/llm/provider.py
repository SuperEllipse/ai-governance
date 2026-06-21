"""LLM provider abstraction for OpenAI and Cloudera AI Inference Service."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from crewai import LLM


ProviderName = Literal["openai", "caiis"]

CAIIS_DEFAULT_BASE_URL = (
    "https://ai-inference.YOUR-DOMAIN/namespaces/serving-default/endpoints/YOUR-MODEL/v1"
)
CAIIS_DEFAULT_MODEL = "nvidia/llama-3.3-nemotron-super-49b-v1"


@dataclass
class LLMConfig:
    provider: ProviderName = "openai"
    model: str = "gpt-4o-mini"
    base_url: str = "https://api.openai.com/v1"
    api_key: str = ""
    temperature: float = 0.2

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "base_url": self.base_url,
            "api_key": self.api_key,
            "temperature": self.temperature,
        }


def _read_cdp_token() -> str:
    token = os.getenv("CDP_TOKEN", "").strip()
    if token:
        return token
    jwt_path = Path("/tmp/jwt")
    if jwt_path.exists():
        return jwt_path.read_text().strip()
    return ""


def default_openai_config() -> LLMConfig:
    return LLMConfig(
        provider="openai",
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        api_key=os.getenv("OPENAI_API_KEY", ""),
    )


def default_caiis_config() -> LLMConfig:
    return LLMConfig(
        provider="caiis",
        model=os.getenv("CAIIS_MODEL", CAIIS_DEFAULT_MODEL),
        base_url=os.getenv("CAIIS_BASE_URL", CAIIS_DEFAULT_BASE_URL),
        api_key=_read_cdp_token(),
    )


def get_llm_config(provider: ProviderName | str = "openai", **overrides: Any) -> LLMConfig:
    base = default_caiis_config() if provider == "caiis" else default_openai_config()
    for key, value in overrides.items():
        if value is not None and value != "" and hasattr(base, key):
            setattr(base, key, value)
    if base.provider == "caiis" and not base.api_key:
        base.api_key = _read_cdp_token()
    return base


def create_crewai_llm(config: LLMConfig | None = None) -> LLM:
    cfg = config or default_openai_config()
    kwargs: dict[str, Any] = {
        "model": cfg.model,
        "temperature": cfg.temperature,
    }
    if cfg.api_key:
        kwargs["api_key"] = cfg.api_key
    if cfg.base_url:
        kwargs["base_url"] = cfg.base_url
    # CrewAI routes "nvidia/..." to LiteLLM; force OpenAI-compatible client for CAIIS.
    if cfg.provider == "caiis" or (
        cfg.base_url and cfg.base_url.rstrip("/") != "https://api.openai.com/v1"
    ):
        kwargs["provider"] = "openai"
    return LLM(**kwargs)


def create_openai_client_kwargs(config: LLMConfig) -> dict[str, Any]:
    """Kwargs for OpenAI-compatible clients (openai SDK, httpx calls)."""
    return {
        "api_key": config.api_key or "not-needed",
        "base_url": config.base_url,
    }


@dataclass
class SafetyModelConfig:
    mode: Literal["self_check", "nim"] = "self_check"
    nim_model: str = "nvidia/llama-3.1-nemoguard-8b-content-safety"
    nim_api_key: str = field(default_factory=lambda: os.getenv("NVIDIA_API_KEY", ""))
    nim_base_url: str = field(
        default_factory=lambda: os.getenv(
            "NIM_BASE_URL", "https://integrate.api.nvidia.com/v1"
        )
    )

    def safety_engine(self) -> str:
        return "nim" if self.mode == "nim" else "openai"

    def safety_model_name(self, main_config: LLMConfig) -> str:
        if self.mode == "nim":
            return self.nim_model
        return main_config.model
