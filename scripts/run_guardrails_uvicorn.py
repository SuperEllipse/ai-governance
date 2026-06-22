#!/usr/bin/env python3
"""Start NeMo Guardrails server with configurable host (CLI hardcodes 0.0.0.0)."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="NeMo Guardrails uvicorn launcher")
    parser.add_argument(
        "--config",
        required=True,
        help="Rails config root (e.g. ./guardrails) or legacy ./guardrails/base",
    )
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default=os.environ.get("GUARDRAILS_HOST", "127.0.0.1"))
    parser.add_argument("--default-config-id", default=None)
    args = parser.parse_args()

    try:
        import uvicorn
        from fastapi import FastAPI

        from nemoguardrails import utils
        from nemoguardrails.server import api
        from nemoguardrails.telemetry import DeploymentTypeEnum, set_deployment_type
    except ImportError:
        print(
            "Server dependencies are missing. Install with: pip install nemoguardrails[server]",
            file=sys.stderr,
        )
        return 1

    set_deployment_type(DeploymentTypeEnum.API.value)

    source_config_path = os.path.abspath(
        os.path.expanduser(args.config.rstrip(os.path.sep))
    )
    from src.guardrails.config_composer import (
        get_rails_config_parent,
        prepare_server_config_from_env,
        resolve_rails_layout,
    )

    rails_parent = get_rails_config_parent(source_config_path)
    _, _, layout_config_id = resolve_rails_layout(source_config_path)
    config_id = (
        args.default_config_id
        or os.environ.get("DEFAULT_CONFIG_ID")
        or os.environ.get("GUARDRAILS_CONFIG_ID")
        or layout_config_id
    )
    os.environ.setdefault("DEFAULT_CONFIG_ID", config_id)
    os.environ.setdefault("GUARDRAILS_CONFIG_ID", config_id)

    # NeMo defaults to packaged examples/bots (abc, abc_v2, hello_world) unless overridden.
    rails_config_path = str(prepare_server_config_from_env(source_config_path))
    examples_path = os.path.abspath(utils.get_examples_data_path("bots"))
    if os.path.abspath(rails_config_path) == examples_path:
        print(
            f"Refusing to start: rails_config_path still points at nemoguardrails examples ({examples_path})",
            file=sys.stderr,
        )
        return 1

    api.app.rails_config_path = rails_config_path
    api.set_default_config_id(config_id)

    server_app: FastAPI = api.app

    print(f"NeMo Guardrails rails_config_path={rails_config_path}", file=sys.stderr)
    print(f"NeMo Guardrails rails parent={rails_parent}", file=sys.stderr)
    print(f"NeMo Guardrails default config_id={config_id}", file=sys.stderr)

    uvicorn.run(server_app, host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
