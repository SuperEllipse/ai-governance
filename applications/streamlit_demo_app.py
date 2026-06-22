#!/usr/bin/env python3
"""Long-running Cloudera AI Application entry point for the Streamlit banking demo."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.runtime.startup import (  # noqa: E402
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
    parser = argparse.ArgumentParser(description="Streamlit banking demo (CAI Application)")
    parser.add_argument(
        "--mode",
        choices=("session", "application"),
        default=None,
        help="Bind strategy: application uses CDSW_APP_PORT on 0.0.0.0; session auto-picks loopback.",
    )
    args = parser.parse_args()

    project_root = setup_pythonpath(ROOT)
    load_dotenv_files(project_root)

    mode = _detect_mode(args.mode)
    bind_host, port = pick_bind(mode, "streamlit")

    app_path = project_root / "app" / "streamlit_app.py"
    if not app_path.is_file():
        print(f"Streamlit app not found: {app_path}", file=sys.stderr)
        return 1

    print(f"PYTHONPATH={os.environ.get('PYTHONPATH', '')}")
    print("Starting Streamlit demo...")
    if mode == "session":
        print("")
        print("Recommended: run guardrails server in a separate terminal first:")
        print("  bash scripts/start_guardrails_server.sh")
        print("Then select 'Centralized Server' mode in the Streamlit sidebar (default).")
    print_startup_banner("streamlit", bind_host=bind_host, port=port, mode=mode)

    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(app_path),
        "--server.port",
        str(port),
        "--server.address",
        bind_host,
        "--browser.gatherUsageStats",
        "false",
    ]
    return subprocess.call(cmd)


if __name__ == "__main__":
    raise SystemExit(main())
