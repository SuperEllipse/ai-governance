"""Parse NeMo Guardrails violation metadata and persist to SQLite."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "violations.db"


@dataclass
class ViolationRecord:
    query: str
    policy: str
    rail: str
    blocked: bool
    refusal_message: str = ""
    category: str = ""
    expected_policy: str = ""
    agent: str = ""
    unguarded_response: str = ""
    guarded_response: str = ""
    activated_rails: list[str] = field(default_factory=list)
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    run_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["activated_rails"] = self.activated_rails
        return d


class ViolationStore:
    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS violations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT,
                    query TEXT,
                    policy TEXT,
                    rail TEXT,
                    blocked INTEGER,
                    refusal_message TEXT,
                    category TEXT,
                    expected_policy TEXT,
                    agent TEXT,
                    unguarded_response TEXT,
                    guarded_response TEXT,
                    activated_rails TEXT,
                    timestamp TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS batch_runs (
                    run_id TEXT PRIMARY KEY,
                    total_queries INTEGER,
                    violation_count INTEGER,
                    started_at TEXT,
                    completed_at TEXT,
                    policies TEXT
                )
            """)

    def save_violation(self, record: ViolationRecord) -> int:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                """
                INSERT INTO violations (
                    run_id, query, policy, rail, blocked, refusal_message,
                    category, expected_policy, agent, unguarded_response,
                    guarded_response, activated_rails, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.run_id,
                    record.query,
                    record.policy,
                    record.rail,
                    int(record.blocked),
                    record.refusal_message,
                    record.category,
                    record.expected_policy,
                    record.agent,
                    record.unguarded_response,
                    record.guarded_response,
                    json.dumps(record.activated_rails),
                    record.timestamp,
                ),
            )
            return cur.lastrowid or 0

    def save_batch_run(
        self,
        run_id: str,
        total: int,
        violations: int,
        policies: list[str],
        started: str,
        completed: str,
    ) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO batch_runs
                (run_id, total_queries, violation_count, started_at, completed_at, policies)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (run_id, total, violations, started, completed, json.dumps(policies)),
            )

    def get_violations(
        self, run_id: str | None = None, limit: int = 500
    ) -> list[dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            if run_id:
                rows = conn.execute(
                    "SELECT * FROM violations WHERE run_id = ? ORDER BY id DESC LIMIT ?",
                    (run_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM violations ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get_batch_runs(self) -> list[dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM batch_runs ORDER BY started_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def _row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        d["blocked"] = bool(d["blocked"])
        try:
            d["activated_rails"] = json.loads(d.get("activated_rails") or "[]")
        except json.JSONDecodeError:
            d["activated_rails"] = []
        return d

    def clear(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM violations")
            conn.execute("DELETE FROM batch_runs")


def parse_guardrails_output(
    query: str,
    response: str,
    log_data: dict[str, Any] | None,
    output_vars: dict[str, Any] | None,
    policies: list[str],
    category: str = "",
    expected_policy: str = "",
    agent: str = "",
    unguarded_response: str = "",
    run_id: str = "",
) -> list[ViolationRecord]:
    """Extract violation records from NeMo guardrails metadata."""
    records: list[ViolationRecord] = []
    output_vars = output_vars or {}
    log_data = log_data or {}

    triggered_input = output_vars.get("triggered_input_rail")
    triggered_output = output_vars.get("triggered_output_rail")
    allowed = output_vars.get("allowed", True)
    activated = log_data.get("activated_rails", []) or []

    if isinstance(activated, dict):
        activated = list(activated.keys())

    rail_names = []
    if triggered_input:
        rail_names.append(("input", str(triggered_input)))
    if triggered_output:
        rail_names.append(("output", str(triggered_output)))

    if not rail_names and not allowed:
        rail_names.append(("input", "blocked"))

    if not rail_names and activated:
        for rail in activated:
            rail_names.append(("unknown", str(rail)))

    if not rail_names and policies:
        # No explicit violation — record pass-through for audit
        return records

    policy_label = ",".join(policies) if policies else "none"

    for rail_type, rail_name in rail_names:
        policy = _infer_policy(rail_name, policies) or policy_label
        records.append(
            ViolationRecord(
                query=query,
                policy=policy,
                rail=f"{rail_type}:{rail_name}",
                blocked=not allowed,
                refusal_message=response if not allowed else "",
                category=category,
                expected_policy=expected_policy,
                agent=agent,
                unguarded_response=unguarded_response,
                guarded_response=response,
                activated_rails=[str(r) for r in activated] if activated else [],
                run_id=run_id,
            )
        )

    if not allowed and not records:
        records.append(
            ViolationRecord(
                query=query,
                policy=policy_label,
                rail="blocked",
                blocked=True,
                refusal_message=response,
                category=category,
                expected_policy=expected_policy,
                agent=agent,
                unguarded_response=unguarded_response,
                guarded_response=response,
                activated_rails=[str(r) for r in activated] if activated else [],
                run_id=run_id,
            )
        )

    return records


def _infer_policy(rail_name: str, policies: list[str]) -> str:
    name_lower = rail_name.lower()
    mapping = {
        "pii": ["pii", "sensitive", "mask", "detect sensitive"],
        "jailbreak": ["jailbreak", "injection"],
        "topic": ["topic", "self check input"],
        "toxicity": ["toxic", "bias", "self check"],
        "prompt_injection": ["injection", "prompt"],
    }
    for policy in policies:
        keywords = mapping.get(policy, [policy])
        if any(kw in name_lower for kw in keywords):
            return policy
    return policies[0] if policies else "unknown"
