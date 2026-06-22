#!/usr/bin/env python3
"""Long-running Cloudera AI Application entry point for the NeMo Guardrails server."""

from __future__ import annotations

try:
    import pysqlite3
    import sys

    sys.modules["sqlite3"] = pysqlite3
except ImportError:
    pass

import argparse
import os
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
    configure_guardrails_llm_env,
    get_guardrails_config_path,
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
    parser = argparse.ArgumentParser(description="NeMo Guardrails server (CAI Application)")
    parser.add_argument(
        "--mode",
        choices=("session", "application"),
        default=None,
        help="Bind strategy: application uses CDSW_APP_PORT on loopback (127.0.0.1) with CDSW proxy.",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Rails config root (default: guardrails/ under project root).",
    )
    parser.add_argument("--default-config-id", default="base")
    args, _unknown = parser.parse_known_args()
    return args


def main() -> int:
    args = _parse_args()

    project_root = setup_pythonpath(resolve_project_root(_script_anchor()))
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
    if _running_under_ipykernel():
        if exit_code != 0:
            print(
                f"ERROR: Guardrails server failed to start (exit code {exit_code}). "
                "Check bind host/port and logs above.",
                file=sys.stderr,
            )
            raise RuntimeError(f"Guardrails server failed to start (exit code {exit_code})")
        return
    raise SystemExit(exit_code)


if _should_autostart():
    _run()
