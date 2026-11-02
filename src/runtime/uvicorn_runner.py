"""Run a uvicorn server safely from a script, CLI, or CAI ipykernel entry point."""

from __future__ import annotations

import asyncio
import sys
import threading
from typing import Any


def _has_running_asyncio_loop() -> bool:
    """True when ipykernel/Jupyter already owns the main-thread event loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return False
    return True


def _uvicorn_thread_target(
    app: Any,
    host: str,
    port: int,
    result: dict[str, object],
) -> None:
    import uvicorn

    try:
        uvicorn.run(app, host=host, port=port, log_level="info")
    except SystemExit as exc:
        code = exc.code if exc.code is not None else 0
        result["exit_code"] = int(code)
        if int(code) != 0:
            result["error"] = exc
    except BaseException as exc:
        result["exit_code"] = 1
        result["error"] = exc


def serve(app: Any, host: str, port: int, *, thread_name: str = "uvicorn") -> int:
    """Run ``app`` with uvicorn and return a process exit code.

    CAI runs Application scripts under ipykernel, which already owns an asyncio loop;
    in that case uvicorn runs in a non-daemon background thread instead.
    """
    import uvicorn

    if _has_running_asyncio_loop():
        print(
            "Detected running asyncio event loop (ipykernel/Jupyter); "
            "starting uvicorn in a background thread.",
            file=sys.stderr,
        )
        result: dict[str, object] = {"exit_code": 0, "error": None}
        thread = threading.Thread(
            target=_uvicorn_thread_target,
            args=(app, host, port, result),
            name=thread_name,
            daemon=False,
        )
        thread.start()
        thread.join()
        exit_code = int(result.get("exit_code", 0))
        error = result.get("error")
        if error is not None:
            print(f"ERROR: uvicorn thread failed: {error!r}", file=sys.stderr)
            return exit_code if exit_code != 0 else 1
        return exit_code

    try:
        uvicorn.run(app, host=host, port=port, log_level="info")
    except SystemExit as exc:
        code = exc.code if exc.code is not None else 0
        return int(code) if int(code) != 0 else 1
    except OSError as exc:
        print(f"ERROR: uvicorn failed to bind or start: {exc}", file=sys.stderr)
        return 1
    return 0
