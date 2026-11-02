"""In-memory batch simulation jobs with Server-Sent Events progress."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncIterator

from src.guardrails.client import GuardrailsMode
from src.guardrails.violation_parser import ViolationStore
from src.llm.provider import LLMConfig, SafetyModelConfig
from src.simulation.batch_runner import run_batch
from src.simulation.queries import get_all_queries

logger = logging.getLogger(__name__)

_MAX_JOBS = 20


@dataclass
class BatchJob:
    job_id: str
    run_id: str
    events: list[dict[str, Any]] = field(default_factory=list)
    finished: bool = False
    _changed: asyncio.Event = field(default_factory=asyncio.Event)
    _task: asyncio.Task | None = None

    def push(self, event: dict[str, Any]) -> None:
        self.events.append(event)
        self._changed.set()

    def progress(self) -> tuple[int, int]:
        for event in reversed(self.events):
            if event["type"] == "progress":
                return event["current"], event["total"]
        return 0, 0


_jobs: OrderedDict[str, BatchJob] = OrderedDict()


def get_job(job_id: str) -> BatchJob | None:
    return _jobs.get(job_id)


def start_job(
    *,
    sample_size: int,
    policies: list[str],
    mode: GuardrailsMode,
    llm_config: LLMConfig,
    safety_config: SafetyModelConfig,
    server_url: str,
) -> BatchJob:
    """Start ``run_batch`` in the background and return its job handle."""
    job = BatchJob(job_id=uuid.uuid4().hex[:12], run_id=uuid.uuid4().hex[:8])
    _jobs[job.job_id] = job
    while len(_jobs) > _MAX_JOBS:
        _jobs.popitem(last=False)

    # The batch tab always runs a guarded path so violation metrics are meaningful.
    effective_mode: GuardrailsMode = mode if mode != "unguarded" else "embedded"
    queries = get_all_queries()[:sample_size]

    def on_progress(current: int, total: int, message: str) -> None:
        job.push({"type": "progress", "current": current, "total": total, "message": message})

    async def runner() -> None:
        started = datetime.now(timezone.utc).isoformat()
        try:
            summary = await run_batch(
                policies=policies,
                mode=effective_mode,
                llm_config=llm_config,
                safety_config=safety_config,
                server_url=server_url,
                queries=queries,
                progress_callback=on_progress,
                run_id=job.run_id,
            )
            summary = {k: v for k, v in summary.items() if k != "results"}
            summary["mode"] = effective_mode
            job.push({"type": "done", "summary": summary})
        except asyncio.CancelledError:
            # The query in flight when cancelled is discarded, so it doesn't count as completed.
            current, total = job.progress()
            completed = max(current - 1, 0)
            store = ViolationStore()
            store.save_batch_run(
                run_id=job.run_id,
                total=completed,
                violations=len({r["query"] for r in store.get_violations(run_id=job.run_id)}),
                policies=policies,
                started=started,
                completed=datetime.now(timezone.utc).isoformat(),
            )
            job.push({"type": "cancelled", "current": completed, "total": total, "run_id": job.run_id})
        except Exception as exc:
            logger.exception("Batch job %s failed", job.job_id)
            job.push({"type": "error", "message": str(exc)})
        finally:
            job.finished = True
            job._changed.set()

    job._task = asyncio.create_task(runner())
    return job


def cancel_job(job: BatchJob) -> bool:
    """Cancel a running job. The query already in flight finishes in its worker thread."""
    if job.finished or job._task is None:
        return False
    return job._task.cancel()


async def stream_events(job: BatchJob) -> AsyncIterator[str]:
    """Yield SSE frames for every job event, replaying earlier ones first."""
    sent = 0
    while True:
        while sent < len(job.events):
            event = job.events[sent]
            sent += 1
            yield f"event: {event['type']}\ndata: {json.dumps(event)}\n\n"
        if job.finished:
            return
        job._changed.clear()
        try:
            await asyncio.wait_for(job._changed.wait(), timeout=15)
        except asyncio.TimeoutError:
            # Comment frame keeps proxies from closing an idle connection.
            yield ": keep-alive\n\n"
