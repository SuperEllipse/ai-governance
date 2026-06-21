#!/usr/bin/env python3
"""Start NeMo Guardrails server with configurable host (CLI hardcodes 0.0.0.0)."""
from __future__ import annotations

import argparse
import logging
import os
import sys


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

    config_path = os.path.expanduser(args.config.rstrip(os.path.sep))
    setattr(api.app, "rails_config_path", config_path)

    if args.default_config_id:
        api.set_default_config_id(args.default_config_id)

    server_app: FastAPI = api.app

    uvicorn.run(server_app, host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
