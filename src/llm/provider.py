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
CAIIS_DEFAULT_MODEL = "nvidia/nemotron-3-nano"
CAIIS_DEFAULT_MAX_TOKENS = 1024
OPENAI_DEFAULT_MAX_TOKENS = 512
CAIIS_PLACEHOLDER_MARKERS = ("YOUR-DOMAIN", "YOUR-MODEL")


def _default_max_tokens(provider: ProviderName) -> int:
    if provider == "caiis":
        return int(os.getenv("CAIIS_MAX_TOKENS", str(CAIIS_DEFAULT_MAX_TOKENS)))
    return int(os.getenv("OPENAI_MAX_TOKENS", str(OPENAI_DEFAULT_MAX_TOKENS)))


def _load_project_env() -> None:
    """Load .env when Streamlit is started without scripts/start_demo.sh."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    project_root = Path(__file__).resolve().parents[2]
    for env_path in (project_root / ".env", Path("/home/cdsw/.env")):
        if env_path.is_file():
            load_dotenv(env_path, override=False)


_load_project_env()


@dataclass
class LLMConfig:
    provider: ProviderName = "openai"
    model: str = "gpt-4o-mini"
    base_url: str = "https://api.openai.com/v1"
    api_key: str = ""
    temperature: float = 0.2
    max_tokens: int = OPENAI_DEFAULT_MAX_TOKENS

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "base_url": self.base_url,
            "api_key": self.api_key,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }


def _read_cdp_token() -> str:
    token = os.getenv("CDP_TOKEN", "").strip()
    if token:
        return token
    jwt_path = Path("/tmp/jwt")
    if jwt_path.exists():
        return jwt_path.read_text().strip()
    return ""


def is_caiis_configured() -> bool:
    """True when CAIIS_BASE_URL is set to a non-placeholder endpoint."""
    url = os.getenv("CAIIS_BASE_URL", "").strip()
    if not url:
        return False
    return not any(marker in url for marker in CAIIS_PLACEHOLDER_MARKERS)


def detect_default_provider() -> ProviderName:
    """Pick the default sidebar provider.

    Uses DEFAULT_LLM_PROVIDER when set; otherwise CAIIS when configured, else OpenAI.
    """
    override = os.getenv("DEFAULT_LLM_PROVIDER", "").strip().lower()
    if override in ("openai", "caiis"):
        return override  # type: ignore[return-value]
    if is_caiis_configured():
        return "caiis"
    return "openai"


def default_llm_config() -> LLMConfig:
    """Default LLM config — CAIIS when configured or DEFAULT_LLM_PROVIDER=caiis."""
    if detect_default_provider() == "caiis":
        return default_caiis_config()
    return default_openai_config()


def default_openai_config() -> LLMConfig:
    return LLMConfig(
        provider="openai",
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        api_key=os.getenv("OPENAI_API_KEY", ""),
        max_tokens=_default_max_tokens("openai"),
    )


def default_caiis_config() -> LLMConfig:
    return LLMConfig(
        provider="caiis",
        model=os.getenv("CAIIS_MODEL", CAIIS_DEFAULT_MODEL),
        base_url=os.getenv("CAIIS_BASE_URL", CAIIS_DEFAULT_BASE_URL),
        api_key=_read_cdp_token(),
        max_tokens=_default_max_tokens("caiis"),
    )


def get_llm_config(
    provider: ProviderName | str | None = None, **overrides: Any
) -> LLMConfig:
    resolved = provider or detect_default_provider()
    base = default_caiis_config() if resolved == "caiis" else default_openai_config()
    for key, value in overrides.items():
        if value is not None and value != "" and hasattr(base, key):
            setattr(base, key, value)
    if base.provider == "caiis" and not base.api_key:
        base.api_key = _read_cdp_token()
    return base


def format_llm_connection_error(exc: Exception, config: LLMConfig) -> str:
    """Clarify CrewAI's generic 'OpenAI API' errors for CAIIS endpoints."""
    msg = str(exc)
    endpoint = config.base_url or "https://api.openai.com/v1"
    provider_label = (
        "Cloudera AI Inference (CAIIS)"
        if config.provider == "caiis"
        else "OpenAI-compatible endpoint"
    )
    if "Failed to connect to OpenAI API" in msg or "Connection error" in msg:
        return (
            f"LLM connection failed to {endpoint} ({provider_label}). "
            "Verify VPN access, base URL, and auth token. "
            f"Underlying error: {msg}"
        )
    return msg


def create_crewai_llm(config: LLMConfig | None = None) -> LLM:
    cfg = config or default_llm_config()
    if cfg.provider == "caiis" and not cfg.api_key:
        cfg.api_key = _read_cdp_token()
    kwargs: dict[str, Any] = {
        "model": cfg.model,
        "temperature": cfg.temperature,
        "max_tokens": cfg.max_tokens,
    }
    api_key = cfg.api_key or (
        _read_cdp_token() if cfg.provider == "caiis" else os.getenv("OPENAI_API_KEY", "")
    )
    if api_key:
        kwargs["api_key"] = api_key
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
