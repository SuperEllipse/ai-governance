"""Batch simulation runner with violation aggregation."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from src.guardrails.client import GuardrailsClient, GuardrailsMode, GuardedResult
from src.guardrails.violation_parser import ViolationStore
from src.llm.provider import LLMConfig, SafetyModelConfig
from src.simulation.queries import SimQuery, get_all_queries


async def run_batch(
    policies: list[str],
    mode: GuardrailsMode = "embedded",
    llm_config: LLMConfig | None = None,
    safety_config: SafetyModelConfig | None = None,
    server_url: str = "http://localhost:8000",
    queries: list[SimQuery] | None = None,
    progress_callback: Callable[[int, int, str], None] | None = None,
    store: ViolationStore | None = None,
) -> dict[str, Any]:
    """Run all simulation queries and store violations."""
    query_list = queries or get_all_queries()
    run_id = str(uuid.uuid4())[:8]
    started = datetime.now(timezone.utc).isoformat()
    client = GuardrailsClient(llm_config, safety_config, server_url)
    violation_store = store or ViolationStore()

    results: list[GuardedResult] = []
    total = len(query_list)

    for i, q in enumerate(query_list):
        if progress_callback:
            progress_callback(i + 1, total, q["query"][:60])

        result = await client.run_query(
            query=q["query"],
            policies=policies,
            mode=mode,
            category=q["category"],
            expected_policy=q.get("expected_policy", ""),
            run_id=run_id,
        )
        results.append(result)

        for violation in result.violations:
            violation_store.save_violation(violation)

        if result.blocked and not result.violations:
            from src.guardrails.violation_parser import ViolationRecord

            violation_store.save_violation(
                ViolationRecord(
                    query=q["query"],
                    policy=",".join(policies),
                    rail="blocked",
                    blocked=True,
                    category=q["category"],
                    expected_policy=q.get("expected_policy", ""),
                    agent=result.agent_trace.get("routed_agent", ""),
                    unguarded_response=result.unguarded_response,
                    guarded_response=result.guarded_response,
                    run_id=run_id,
                )
            )

    completed = datetime.now(timezone.utc).isoformat()
    violation_count = sum(1 for r in results if r.blocked or r.violations)

    violation_store.save_batch_run(
        run_id=run_id,
        total=total,
        violations=violation_count,
        policies=policies,
        started=started,
        completed=completed,
    )

    return aggregate_results(results, run_id)


def aggregate_results(results: list[GuardedResult], run_id: str) -> dict[str, Any]:
    total = len(results)
    blocked = sum(1 for r in results if r.blocked)
    by_category: dict[str, int] = {}
    by_policy: dict[str, int] = {}
    expected_hits = 0
    expected_total = 0

    for r in results:
        cat = next(
            (v.category for v in r.violations if v.category),
            "happy_path",
        )
        by_category[cat] = by_category.get(cat, 0) + (1 if r.blocked or r.violations else 0)
        for v in r.violations:
            by_policy[v.policy] = by_policy.get(v.policy, 0) + 1
            if v.expected_policy and v.policy.startswith(v.expected_policy.split(",")[0]):
                expected_hits += 1
            if v.expected_policy:
                expected_total += 1

    return {
        "run_id": run_id,
        "total_queries": total,
        "violation_count": blocked,
        "violation_rate": blocked / total if total else 0,
        "by_category": by_category,
        "by_policy": by_policy,
        "expected_hits": expected_hits,
        "expected_total": expected_total,
        "results": [r.to_dict() for r in results],
    }


def run_batch_sync(**kwargs: Any) -> dict[str, Any]:
    return asyncio.run(run_batch(**kwargs))
