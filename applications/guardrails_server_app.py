#!/usr/bin/env python3
"""Long-running Cloudera AI Application entry point for the NeMo Guardrails server."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.runtime.startup import (  # noqa: E402
    configure_guardrails_llm_env,
    get_guardrails_config_path,
    load_dotenv_files,
    pick_bind,
    print_startup_banner,
    setup_pythonpath,
)


def _detect_mode(cli_mode: str | None) -> str:
    if cli_mode:
        return cli_mode
    if os.environ.get("CDSW_APP_PORT") or os.environ.get("CDSW_READONLY_PORT"):
        return "application"
    return "session"


def main() -> int:
    parser = argparse.ArgumentParser(description="NeMo Guardrails server (CAI Application)")
    parser.add_argument(
        "--mode",
        choices=("session", "application"),
        default=None,
        help="Bind strategy: application uses CDSW_APP_PORT on 0.0.0.0; session auto-picks loopback.",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Rails config root (default: guardrails/ under project root).",
    )
    parser.add_argument("--default-config-id", default="base")
    args = parser.parse_args()

    project_root = setup_pythonpath(ROOT)
    load_dotenv_files(project_root)
    configure_guardrails_llm_env()

    mode = _detect_mode(args.mode)
    bind_host, port = pick_bind(mode, "guardrails")
    os.environ["GUARDRAILS_HOST"] = bind_host
    os.environ["GUARDRAILS_PORT"] = str(port)

    config_path = get_guardrails_config_path(project_root)
    if args.config:
        config_path = Path(args.config).expanduser().resolve()

    from src.guardrails.config_composer import get_rails_config_parent

    rails_config_path = get_rails_config_parent(str(config_path))

    print("Starting NeMo Guardrails server...")
    print(f"  Config source: {config_path}")
    print(f"  rails_config_path: {rails_config_path}")
    print(f"  default config_id: {args.default_config_id}")
    print(f"  Bind:   {bind_host}:{port}")
    print(f"  Model:  {os.environ.get('MAIN_MODEL_NAME', '')}")
    print(f"  Base:   {os.environ.get('MAIN_MODEL_BASE_URL', '')}")
    print(f"  Mode:   {mode}")
    print_startup_banner("guardrails", bind_host=bind_host, port=port, mode=mode)

    from scripts.run_guardrails_uvicorn import run_uvicorn_server

    return run_uvicorn_server(
        config=str(config_path),
        host=bind_host,
        port=port,
        default_config_id=args.default_config_id,
    )


if __name__ == "__main__":
    raise SystemExit(main())
