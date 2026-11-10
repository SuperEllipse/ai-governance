#!/usr/bin/env python3
"""Long-running Cloudera AI Application entry point for the banking demo web UI."""

from __future__ import annotations

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

from src.runtime.sqlite_compat import apply_sqlite3_compat, needs_pysqlite3_shim  # noqa: E402

import argparse
import os
import subprocess

from src.runtime.startup import (  # noqa: E402
    is_platform_application_env,
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
    if is_platform_application_env():
        return "application"
    return "session"


def _running_under_ipykernel() -> bool:
    argv0 = os.path.basename(sys.argv[0]) if sys.argv else ""
    return "ipykernel" in argv0 or "-f" in sys.argv


def _ensure_sqlite_compat() -> None:
    """Apply sqlite3 shim; auto-install pysqlite3-binary on CAI engines when missing."""
    if needs_pysqlite3_shim():
        try:
            import pysqlite3  # noqa: F401
        except ImportError:
            print(
                "System sqlite3 is too old for ChromaDB; installing pysqlite3-binary…",
                file=sys.stderr,
            )
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "pysqlite3-binary"],
            )
    apply_sqlite3_compat()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Banking demo web UI (CAI Application)")
    parser.add_argument(
        "--mode",
        choices=("session", "application"),
        default=None,
        help=(
            "Bind strategy: application binds localhost (127.0.0.1) on APP_PORT (CAII) "
            "or CDSW_APP_PORT (CAI Workbench) injected by the platform."
        ),
    )
    args, _unknown = parser.parse_known_args()
    return args


def main() -> int:
    args = _parse_args()
    _ensure_sqlite_compat()

    project_root = setup_pythonpath(resolve_project_root(_script_anchor()))
    load_dotenv_files(project_root)

    mode = _detect_mode(args.mode)
    bind_host, port = pick_bind(mode, "web")

    from src.api.app import WEB_DIST, create_app
    from src.runtime.uvicorn_runner import serve

    print(f"PYTHONPATH={os.environ.get('PYTHONPATH', '')}")
    print("Starting banking demo web UI...")
    if not (WEB_DIST / "index.html").is_file():
        print(
            f"WARNING: {WEB_DIST} not found; only the API will be served. "
            "Build the UI with: cd interface && npm ci && npm run build",
            file=sys.stderr,
        )
    if mode == "session":
        print("")
        print("Recommended: run guardrails server in a separate terminal first:")
        print("  bash scripts/start_guardrails_server.sh")
        print("Then select 'Centralized Server' mode in the web UI settings (default).")
    print_startup_banner("web", bind_host=bind_host, port=port, mode=mode)

    return serve(create_app(), bind_host, port, thread_name="web-uvicorn")


_main_started = False


def _should_autostart() -> bool:
    if __name__ == "__main__":
        return True
    if is_platform_application_env():
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
