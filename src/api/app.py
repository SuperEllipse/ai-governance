"""FastAPI app: JSON API under /api plus the built React UI from interface/dist."""

from __future__ import annotations

import importlib.util
import time
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from src.api import batch_jobs
from src.api.schemas import BatchRequest, QueryRequest
from src.api.settings import build_configs, default_guardrails_server_url, ui_defaults
from src.guardrails.client import GuardrailsClient
from src.guardrails.violation_parser import (
    ViolationStore,
    is_actual_violation,
    policies_checked_and_passed,
)
from src.simulation.queries import EXAMPLE_QUERIES, get_all_queries

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WEB_DIST = PROJECT_ROOT / "interface" / "dist"

_MISSING_BUILD_HTML = """<!doctype html>
<html><head><title>Web UI not built</title></head>
<body style="font-family: system-ui, sans-serif; max-width: 40rem; margin: 4rem auto;">
<h1>Web UI not built</h1>
<p>The API is running, but <code>interface/dist/</code> was not found.</p>
<pre>cd interface
npm ci
npm run build</pre>
<p>Then restart the app. API health: <a href="api/health">api/health</a></p>
</body></html>"""


_DEPENDENCIES = {
    "nemoguardrails": "NeMo Guardrails",
    "crewai": "CrewAI",
    "presidio_analyzer": "Presidio (PII detection)",
}


async def _probe_guardrails_server(server_url: str) -> dict[str, Any]:
    """Check that a NeMo Guardrails server answers on ``/v1/rails/configs``."""
    url = server_url.rstrip("/")
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{url}/v1/rails/configs")
        latency_ms = round((time.perf_counter() - started) * 1000)
        if resp.status_code != 200:
            detail = f"HTTP {resp.status_code} from {url}/v1/rails/configs"
        else:
            # NeMo answers with a JSON list of configs; anything else is a different server.
            try:
                is_nemo = isinstance(resp.json(), list)
            except ValueError:
                is_nemo = False
            if is_nemo:
                return {"url": url, "reachable": True, "latency_ms": latency_ms, "detail": ""}
            detail = f"{url} answered, but it is not a NeMo Guardrails server"
        return {"url": url, "reachable": False, "latency_ms": latency_ms, "detail": detail}
    except httpx.HTTPError as exc:
        return {
            "url": url,
            "reachable": False,
            "latency_ms": None,
            "detail": f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__,
        }


def _query_response(result: Any) -> dict[str, Any]:
    """``GuardedResult.to_dict()`` plus the status flags the UI renders."""
    output_vars = result.output_vars or {}
    log_data = result.guardrails_log or {}
    payload = result.to_dict()
    payload["actual_violation"] = bool(
        result.blocked or is_actual_violation(output_vars, log_data)
    )
    payload["checks_passed"] = policies_checked_and_passed(
        result.policies, output_vars, log_data
    )
    payload["infra_error"] = output_vars.get("guardrails_error") or ""
    return payload


def create_app() -> FastAPI:
    app = FastAPI(
        title="NeMo Guardrails Banking Demo API",
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
        swagger_ui_oauth2_redirect_url="/api/docs/oauth2-redirect",
    )

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/config")
    async def config() -> dict[str, Any]:
        return ui_defaults()

    @app.get("/api/status")
    async def status(server_url: str = "", check_server: bool = True) -> dict[str, Any]:
        defaults = ui_defaults()
        deps = [
            {"module": module, "label": label, "installed": importlib.util.find_spec(module) is not None}
            for module, label in _DEPENDENCIES.items()
        ]
        result: dict[str, Any] = {
            "deps": deps,
            "llm": {name: info["has_api_key"] for name, info in defaults["providers"].items()},
            "guardrails_server": None,
        }
        if check_server:
            result["guardrails_server"] = await _probe_guardrails_server(
                server_url.strip() or default_guardrails_server_url()
            )
        return result

    @app.get("/api/examples")
    async def examples() -> dict[str, Any]:
        return {"examples": EXAMPLE_QUERIES, "dataset_size": len(get_all_queries())}

    @app.post("/api/query")
    async def query(req: QueryRequest) -> dict[str, Any]:
        llm_config, safety_config, server_url = build_configs(req.settings)
        client = GuardrailsClient(llm_config, safety_config, server_url)
        started = time.perf_counter()
        result = await client.run_query(
            req.query.strip(),
            policies=req.settings.policies,
            mode=req.settings.mode,
        )
        payload = _query_response(result)
        payload["elapsed_ms"] = round((time.perf_counter() - started) * 1000)
        return payload

    @app.post("/api/batch")
    async def start_batch(req: BatchRequest) -> dict[str, str]:
        llm_config, safety_config, server_url = build_configs(req.settings)
        job = batch_jobs.start_job(
            sample_size=req.sample_size,
            policies=req.settings.policies,
            mode=req.settings.mode,
            llm_config=llm_config,
            safety_config=safety_config,
            server_url=server_url,
        )
        return {"job_id": job.job_id, "run_id": job.run_id}

    @app.get("/api/batch/{job_id}/events")
    async def batch_events(job_id: str) -> StreamingResponse:
        job = batch_jobs.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Unknown batch job")
        return StreamingResponse(
            batch_jobs.stream_events(job),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.delete("/api/batch/{job_id}")
    async def cancel_batch(job_id: str) -> dict[str, bool]:
        job = batch_jobs.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Unknown batch job")
        return {"cancelled": batch_jobs.cancel_job(job)}

    @app.get("/api/violations")
    async def violations(run_id: str | None = None) -> list[dict[str, Any]]:
        return ViolationStore().get_violations(run_id=run_id or None)

    @app.get("/api/batch-runs")
    async def batch_runs() -> list[dict[str, Any]]:
        return ViolationStore().get_batch_runs()

    _mount_frontend(app)
    return app


def _mount_frontend(app: FastAPI) -> None:
    index = WEB_DIST / "index.html"
    if not index.is_file():

        @app.get("/", response_class=HTMLResponse, include_in_schema=False)
        async def missing_build() -> str:
            return _MISSING_BUILD_HTML

        return

    assets = WEB_DIST / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str) -> FileResponse:
        if path.startswith("api/"):
            raise HTTPException(status_code=404)
        candidate = (WEB_DIST / path).resolve()
        if path and candidate.is_file() and WEB_DIST.resolve() in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(index)
