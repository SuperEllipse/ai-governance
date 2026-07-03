#!/usr/bin/env python3
"""Verify unified CAI / CAII application port resolution without binding sockets."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.runtime.startup import (  # noqa: E402
    detect_deploy_platform,
    is_platform_application_env,
    resolve_app_port,
)


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _with_env(env: dict[str, str | None], fn) -> None:
    with patch.dict(os.environ, env, clear=True):
        fn()


def test_detect_cai_from_cdsw_app_port() -> None:
    def run() -> None:
        _assert(detect_deploy_platform() == "cai", "CDSW_APP_PORT should imply CAI")
        _assert(is_platform_application_env(), "CAI ports should enable application mode")

    _with_env({"CDSW_APP_PORT": "8090"}, run)


def test_detect_caii_from_app_port() -> None:
    def run() -> None:
        _assert(detect_deploy_platform() == "caii", "APP_PORT should imply CAII")
        _assert(is_platform_application_env(), "CAII signals should enable application mode")

    _with_env({"APP_PORT": "8080"}, run)


def test_detect_caii_from_service_domain() -> None:
    def run() -> None:
        _assert(detect_deploy_platform() == "caii", "SERVICE_DOMAIN should imply CAII")

    _with_env({"SERVICE_DOMAIN": "banking-demo.example.com"}, run)


def test_explicit_deploy_platform_override() -> None:
    def run() -> None:
        _assert(detect_deploy_platform() == "caii", "DEPLOY_PLATFORM=caii should win")

    _with_env(
        {"DEPLOY_PLATFORM": "caii", "CDSW_APP_PORT": "8090"},
        run,
    )


def test_cai_port_precedence_over_caii_signals() -> None:
    def run() -> None:
        _assert(
            detect_deploy_platform() == "cai",
            "CAI port keys should take precedence when both CAI and CAII vars are set",
        )

    _with_env(
        {
            "CDSW_APP_PORT": "8090",
            "APP_PORT": "8080",
            "SERVICE_DOMAIN": "demo.example.com",
        },
        run,
    )


def test_resolve_cai_streamlit_port() -> None:
    def run() -> None:
        port, key = resolve_app_port("streamlit")
        _assert(port == 8100, "streamlit should bind CDSW_APP_PORT on CAI")
        _assert(key == "CDSW_APP_PORT", "env key should be CDSW_APP_PORT")

    _with_env({"CDSW_APP_PORT": "8100"}, run)


def test_resolve_cai_guardrails_default_port_key() -> None:
    def run() -> None:
        port, key = resolve_app_port("guardrails")
        _assert(port == 8091, "guardrails should use first CAI port key set")
        _assert(key == "CDSW_APP_PORT", "env key should be CDSW_APP_PORT")

    _with_env({"CDSW_APP_PORT": "8091", "CDSW_READONLY_PORT": "8092"}, run)


def test_resolve_cai_guardrails_bind_port_key() -> None:
    def run() -> None:
        port, key = resolve_app_port("guardrails")
        _assert(port == 8092, "CAI_BIND_PORT_KEY should select readonly port")
        _assert(key == "CDSW_READONLY_PORT", "env key should match CAI_BIND_PORT_KEY")

    _with_env(
        {
            "CDSW_APP_PORT": "8091",
            "CDSW_READONLY_PORT": "8092",
            "CAI_BIND_PORT_KEY": "CDSW_READONLY_PORT",
        },
        run,
    )


def test_resolve_caii_default_port() -> None:
    def run() -> None:
        port, key = resolve_app_port("streamlit")
        _assert(port == 8080, "CAII default bind port should be 8080")
        _assert(key == "APP_PORT", "env key should be APP_PORT")

    _with_env({"SERVICE_DOMAIN": "banking-demo.example.com"}, run)


def test_resolve_caii_explicit_app_port() -> None:
    def run() -> None:
        port, key = resolve_app_port("guardrails")
        _assert(port == 8080, "CAII should use injected APP_PORT")
        _assert(key == "APP_PORT", "env key should be APP_PORT")

    _with_env({"APP_PORT": "8080", "APP_URL": "https://nemo-guardrails.example.com"}, run)


def main() -> int:
    tests = [
        test_detect_cai_from_cdsw_app_port,
        test_detect_caii_from_app_port,
        test_detect_caii_from_service_domain,
        test_explicit_deploy_platform_override,
        test_cai_port_precedence_over_caii_signals,
        test_resolve_cai_streamlit_port,
        test_resolve_cai_guardrails_default_port_key,
        test_resolve_cai_guardrails_bind_port_key,
        test_resolve_caii_default_port,
        test_resolve_caii_explicit_app_port,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"\nAll {len(tests)} port resolution checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
