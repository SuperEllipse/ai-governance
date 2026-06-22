#!/usr/bin/env python3
"""Long-running Cloudera AI Application entry point for the Streamlit banking demo."""

from __future__ import annotations

try:
    import pysqlite3
    import sys

    sys.modules["sqlite3"] = pysqlite3
except ImportError:
    pass

import argparse
import os
import subprocess
import sys
from pathlib import Path


def _bootstrap_import_path() -> None:
    try:
        root = Path(__file__).resolve().parents[1]
    except NameError:
        root = None
        for candidate in (Path.cwd(), Path("/home/cdsw")):
            if (candidate / "guardrails").is_dir() and (candidate / "applications").is_dir():
                root = candidate.resolve()
                break
        if root is None:
            root = Path.cwd()
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)


_bootstrap_import_path()

from src.runtime.startup import (  # noqa: E402
    load_dotenv_files,
    pick_bind,
    print_startup_banner,
    resolve_project_root,
    setup_pythonpath,
)


def _script_anchor() -> str | None:
    try:
        return __file__
    except NameError:
        return None


def _detect_mode(cli_mode: str | None) -> str:
    if cli_mode:
        return cli_mode
    if os.environ.get("CDSW_APP_PORT") or os.environ.get("CDSW_READONLY_PORT"):
        return "application"
    return "session"


def _running_under_ipykernel() -> bool:
    argv0 = os.path.basename(sys.argv[0]) if sys.argv else ""
    return "ipykernel" in argv0 or "-f" in sys.argv


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Streamlit banking demo (CAI Application)")
    parser.add_argument(
        "--mode",
        choices=("session", "application"),
        default=None,
        help="Bind strategy: application uses CDSW_APP_PORT on 0.0.0.0; session auto-picks loopback.",
    )
    args, _unknown = parser.parse_known_args()
    return args


def main() -> int:
    args = _parse_args()

    project_root = setup_pythonpath(resolve_project_root(_script_anchor()))
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


_main_started = False


def _should_autostart() -> bool:
    if __name__ == "__main__":
        return True
    if os.environ.get("CDSW_APP_PORT") or os.environ.get("CDSW_READONLY_PORT"):
        return True
    return _running_under_ipykernel()


def _run() -> None:
    global _main_started
    if _main_started:
        return
    _main_started = True
    exit_code = main()
    if not _running_under_ipykernel():
        raise SystemExit(exit_code)


if _should_autostart():
    _run()
