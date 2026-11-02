"""Request models for the web UI API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from src.guardrails.client import GuardrailsMode
from src.llm.provider import ProviderName, SafetyMode


class RunSettings(BaseModel):
    """Settings panel values sent with every query or batch run.

    Secret fields (``api_key``, ``nim_api_key``) are optional: when blank the server
    falls back to its own environment (``OPENAI_API_KEY``, ``CDP_TOKEN``, ``NVIDIA_API_KEY``).
    """

    provider: ProviderName = "openai"
    api_key: str = ""
    base_url: str = ""
    model: str = ""
    safety_mode: SafetyMode = "self_check"
    nim_api_key: str = ""
    llama_guard_base_url: str = ""
    llama_guard_model: str = ""
    mode: GuardrailsMode = "server"
    server_url: str = ""
    policies: list[str] = Field(default_factory=list)


class QueryRequest(BaseModel):
    query: str = Field(min_length=1)
    settings: RunSettings


class BatchRequest(BaseModel):
    sample_size: Literal[10, 25, 50, 100] = 100
    settings: RunSettings
