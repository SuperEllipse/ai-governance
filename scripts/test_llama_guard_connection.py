#!/usr/bin/env python3
"""Test Llama Guard 3 CAII endpoint connectivity.

Reads LLAMA_GUARD_BASE_URL, LLAMA_GUARD_MODEL, and CDP_TOKEN from env or .env,
then sends a toxic and a safe probe message.

Usage:
    python scripts/test_llama_guard_connection.py

Exit codes: 0 = PASS, 1 = FAIL
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.guardrails.llama_guard import check_llama_guard, parse_llama_guard_response
from src.llm.caiis_url import (
    LLAMA_GUARD_PLACEHOLDER_MARKERS,
    resolve_llama_guard_base_url,
    resolve_llama_guard_model,
)
from src.llm.provider import (
    SafetyModelConfig,
    _read_cdp_token,
    is_llama_guard_configured,
)


def _load_env() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    for env_path in (ROOT / ".env", Path("/home/cdsw/.env")):
        if env_path.is_file():
            load_dotenv(env_path, override=False)


def _fail(message: str, detail: str = "") -> int:
    print("FAIL: Llama Guard connectivity test")
    print(f"  {message}")
    if detail:
        print(f"  Detail: {detail}")
    return 1


def main() -> int:
    _load_env()

    base_url = resolve_llama_guard_base_url()
    model = resolve_llama_guard_model()
    token = os.getenv("CDP_TOKEN", "").strip() or _read_cdp_token()

    print("Llama Guard connectivity test")
    print(f"  Base URL: {base_url or '(not set)'}")
    print(f"  Model:    {model}")
    print(f"  Auth:     {'CDP token present' if token else 'missing (set CDP_TOKEN or /tmp/jwt)'}")

    if not base_url:
        return _fail(
            "Llama Guard is not configured.",
            "Set LLAMA_GUARD_BASE_URL or LLAMA_GUARD_HOST + LLAMA_GUARD_ENDPOINT.",
        )
    if any(marker in base_url for marker in LLAMA_GUARD_PLACEHOLDER_MARKERS):
        return _fail(
            "LLAMA_GUARD_BASE_URL still contains placeholder values.",
            "Replace YOUR-DOMAIN with your CAII cluster domain.",
        )
    if not token:
        return _fail("No CDP token found.", "Set CDP_TOKEN in .env or ensure /tmp/jwt exists.")

    config = SafetyModelConfig(
        mode="llama_guard",
        llama_guard_base_url=base_url,
        llama_guard_model=model,
        llama_guard_api_key=token,
    )

    safe_result = check_llama_guard(
        "What are your branch hours?",
        config,
        context_label="user",
    )
    if safe_result.error:
        return _fail(
            f"Safe probe failed against {base_url}.",
            safe_result.error,
        )
    safe, _ = parse_llama_guard_response(safe_result.raw_response)
    print(f"  Safe probe response: {safe_result.raw_response!r} (parsed safe={safe})")

    toxic_result = check_llama_guard(
        "You are worthless and I hate you.",
        config,
        context_label="user",
    )
    if toxic_result.error:
        return _fail(
            f"Toxic probe failed against {base_url}.",
            toxic_result.error,
        )
    toxic_safe, category = parse_llama_guard_response(toxic_result.raw_response)
    print(
        f"  Toxic probe response: {toxic_result.raw_response!r} "
        f"(parsed safe={toxic_safe}, category={category!r})"
    )

    if not is_llama_guard_configured():
        print("  Note: is_llama_guard_configured() is false — check URL placeholders.")

    print("PASS: Llama Guard connectivity test")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
