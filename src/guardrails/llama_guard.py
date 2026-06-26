"""Llama Guard 3 safety checks via OpenAI-compatible CAII endpoints."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from src.llm.provider import SafetyModelConfig, _read_cdp_token, is_llama_guard_configured


def parse_llama_guard_response(text: str) -> tuple[bool, str]:
    """Parse Llama Guard output: ``safe`` or ``unsafe`` plus optional category code."""
    cleaned = (text or "").strip()
    if not cleaned:
        return True, ""

    first_line = cleaned.splitlines()[0].strip().lower()
    category = ""
    if "\n" in cleaned:
        parts = cleaned.split("\n", 1)
        if len(parts) > 1:
            category = parts[1].strip()

    if first_line == "safe":
        return True, category
    if first_line.startswith("unsafe"):
        if not category and " " in first_line:
            category = first_line.split(" ", 1)[1].strip()
        return False, category
    if first_line.startswith("not safe") or first_line.startswith("blocked"):
        return False, category
    logger.warning("Unexpected Llama Guard response: %r", cleaned[:200])
    return True, category


@dataclass
class LlamaGuardResult:
    safe: bool
    category: str = ""
    raw_response: str = ""
    error: str = ""

    @property
    def blocked(self) -> bool:
        return not self.safe and not self.error


def _llama_guard_client_kwargs(config: SafetyModelConfig) -> dict[str, str]:
    api_key = config.llama_guard_api_key or _read_cdp_token()
    return {
        "api_key": api_key or "not-needed",
        "base_url": config.llama_guard_base_url,
    }


def _category_reason(category: str) -> str:
    """Map Llama Guard category codes to human-readable policy reasons."""
    code = (category or "").strip().upper()
    mapping = {
        "S1": "Violent crimes",
        "S2": "Non-violent crimes",
        "S3": "Sex-related crimes",
        "S4": "Child exploitation",
        "S5": "Defamation",
        "S6": "Specialized advice",
        "S7": "Privacy",
        "S8": "Intellectual property",
        "S9": "Indiscriminate weapons",
        "S10": "Hate speech / toxic content",
        "S11": "Self-harm",
        "S12": "Sexual content",
        "S13": "Elections",
        "S14": "Code interpreter abuse",
    }
    if code in mapping:
        return f"Content flagged as unsafe ({mapping[code]})"
    if code:
        return f"Content flagged as unsafe (category {code})"
    return "Content flagged as unsafe by Llama Guard"


def block_refusal_for_category(category: str) -> tuple[str, str]:
    """Return (user-facing refusal, policy_reason) for a Llama Guard block."""
    reason = _category_reason(category)
    if category.upper() == "S6":
        reason = "Investment or specialized financial advice not permitted"
    return (
        "I'm sorry, I can't help with that request. "
        "Please ask about retail banking services such as accounts, cards, or mortgages.",
        reason,
    )


def check_llama_guard(
    text: str,
    config: SafetyModelConfig,
    *,
    context_label: str = "user",
) -> LlamaGuardResult:
    """Call Llama Guard on ``text`` (user message or bot response)."""
    if not config.llama_guard_base_url:
        return LlamaGuardResult(
            safe=True,
            error="LLAMA_GUARD_BASE_URL is not configured",
        )

    try:
        from openai import OpenAI
    except ImportError as exc:
        return LlamaGuardResult(safe=True, error=f"openai package missing: {exc}")

    client = OpenAI(**_llama_guard_client_kwargs(config))
    prompt = text.strip()
    if context_label == "assistant":
        prompt = f"[Assistant response to evaluate]\n{text.strip()}"

    try:
        response = client.chat.completions.create(
            model=config.llama_guard_model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=16,
            temperature=0,
        )
    except Exception as exc:
        logger.exception("Llama Guard API call failed")
        return LlamaGuardResult(safe=True, error=str(exc))

    raw = ""
    if response.choices:
        raw = (response.choices[0].message.content or "").strip()
    safe, category = parse_llama_guard_response(raw)
    return LlamaGuardResult(safe=safe, category=category, raw_response=raw)
