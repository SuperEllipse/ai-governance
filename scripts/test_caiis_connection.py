#!/usr/bin/env python3
"""Test CAIIS Nemotron endpoint connectivity (CDSW job friendly).

Reads CAIIS_BASE_URL, CAIIS_MODEL, and CDP_TOKEN from the environment or .env,
then makes a minimal chat.completions call via the OpenAI SDK.

Usage:
    python scripts/test_caiis_connection.py

Exit codes: 0 = PASS, 1 = FAIL
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.llm.provider import CAIIS_DEFAULT_MODEL, CAIIS_PLACEHOLDER_MARKERS, _read_cdp_token


def _load_env() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    for env_path in (ROOT / ".env", Path("/home/cdsw/.env")):
        if env_path.is_file():
            load_dotenv(env_path, override=False)


def _fail(message: str, detail: str = "") -> int:
    print("FAIL: CAIIS connectivity test")
    print(f"  {message}")
    if detail:
        print(f"  Detail: {detail}")
    return 1


def main() -> int:
    _load_env()

    base_url = os.getenv("CAIIS_BASE_URL", "").strip()
    model = os.getenv("CAIIS_MODEL", CAIIS_DEFAULT_MODEL).strip()
    token = os.getenv("CDP_TOKEN", "").strip() or _read_cdp_token()

    print("CAIIS connectivity test")
    print(f"  Base URL: {base_url or '(not set)'}")
    print(f"  Model:    {model}")
    print(f"  Auth:     {'CDP token present' if token else 'missing (set CDP_TOKEN or /tmp/jwt)'}")

    if not base_url:
        return _fail("CAIIS_BASE_URL is not set.")
    if any(marker in base_url for marker in CAIIS_PLACEHOLDER_MARKERS):
        return _fail(
            "CAIIS_BASE_URL still contains placeholder values.",
            "Replace YOUR-DOMAIN and YOUR-MODEL with your endpoint details.",
        )
    if not token:
        return _fail("No CDP token found.", "Set CDP_TOKEN in .env or ensure /tmp/jwt exists.")

    try:
        from openai import OpenAI
    except ImportError as exc:
        return _fail("openai package not installed.", str(exc))

    client = OpenAI(api_key=token, base_url=base_url)

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Reply with exactly: CAIIS OK"}],
            max_tokens=int(os.getenv("CAIIS_MAX_TOKENS", "1024")),
            temperature=0,
        )
    except Exception as exc:
        return _fail(
            f"Request to {base_url} failed.",
            f"{type(exc).__name__}: {exc}",
        )

    content = ""
    if response.choices:
        content = (response.choices[0].message.content or "").strip()

    print("PASS: CAIIS connectivity test")
    print(f"  Model response: {content[:200] or '(empty)'}")
    print(f"  Request ID: {getattr(response, 'id', 'n/a')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
