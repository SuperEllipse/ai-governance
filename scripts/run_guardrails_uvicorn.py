#!/usr/bin/env python3
"""Start NeMo Guardrails server with configurable host (CLI hardcodes 0.0.0.0)."""
from __future__ import annotations

import argparse
import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="NeMo Guardrails uvicorn launcher")
    parser.add_argument("--config", required=True, help="Rails config directory")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default=os.environ.get("GUARDRAILS_HOST", "127.0.0.1"))
    parser.add_argument("--default-config-id", default=None)
    args = parser.parse_args()

    try:
        import uvicorn
        from fastapi import FastAPI

        from nemoguardrails.server import api
        from nemoguardrails.telemetry import DeploymentTypeEnum, set_deployment_type
    except ImportError:
        print(
            "Server dependencies are missing. Install with: pip install nemoguardrails[server]",
            file=sys.stderr,
        )
        return 1

    set_deployment_type(DeploymentTypeEnum.API.value)

    source_config_path = os.path.expanduser(args.config.rstrip(os.path.sep))
    from src.guardrails.config_composer import prepare_server_config_from_env

    config_path = str(prepare_server_config_from_env(source_config_path))
    config_id = args.default_config_id or os.path.basename(os.path.normpath(source_config_path))

    api.app.rails_config_path = config_path
    api.set_default_config_id(config_id)

    # Env overrides copy config into a temp dir; keep a stable API config id (e.g. "base").
    from nemoguardrails.server.api import lifespan as nemo_lifespan

    @asynccontextmanager
    async def lifespan_with_stable_config_id(app):
        async with nemo_lifespan(app):
            if app.single_config_mode:
                app.single_config_id = config_id
                api.set_default_config_id(config_id)
            yield

    api.app.router.lifespan_context = lifespan_with_stable_config_id

    server_app: FastAPI = api.app

    uvicorn.run(server_app, host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
