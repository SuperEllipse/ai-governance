"""Parse NeMo Guardrails violation metadata and persist to SQLite."""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "violations.db"

# Default human-readable reasons when log/completion parsing is unavailable.
POLICY_REASONS: dict[str, str] = {
    "self check input": "Input policy violation (off-topic, unsafe, or non-compliant request)",
    "self check output": "Output policy violation (missing disclaimer, PII, or unsafe content)",
    "detect sensitive data on input": "Personal data detected in input (PII)",
    "detect sensitive data on output": "Personal data detected in output (PII)",
    "check jailbreak": "Prompt injection / jailbreak attempt",
    "jailbreak detection heuristics": "Prompt injection / jailbreak attempt",
    "topic safety check input": "Off-topic request (not retail banking)",
    "topic safety check output": "Off-topic content in response",
    "llama guard input": "Content flagged as unsafe by Llama Guard",
    "llama guard output": "Bot response flagged as unsafe by Llama Guard",
}

# Keyword → reason when inferring from user query (self_check input blocks).
_QUERY_REASON_HINTS: list[tuple[list[str], str]] = [
    (
        [
            r"invest",
            r"mutual fund",
            r"\betf\b",
            r"crypto",
            r"bitcoin",
            r"stock",
            r"securities",
        ],
        "Investment advice not permitted (mutual funds, crypto, stocks, ETFs)",
    ),
    (
        [r"ignore.*rule", r"bypass", r"system prompt", r"jailbreak", r"\bdan\b", r"override", r"disregard"],
        "Prompt injection / jailbreak attempt",
    ),
    (
        [r"politic", r"\bvote\b", r"election"],
        "Politics and unrelated topics not permitted",
    ),
    (
        [r"competitor", r"chase bank", r"wells fargo", r"bank of america"],
        "Competitor discussion not permitted",
    ),
    (
        [r"discriminat", r"\bhate\b", r"terrible with money", r"morons", r"refuse service"],
        "Discriminatory or abusive language not permitted",
    ),
    (
        [r"\bssn\b", r"social security", r"\d{3}-\d{2}-\d{4}", r"account number"],
        "Raw PII in user message not permitted",
    ),
]

_OUTPUT_REASON_HINTS: list[tuple[list[str], str]] = [
    ([r"fdic", r"deposit", r"insured"], "Missing required FDIC disclaimer for deposit discussion"),
    ([r"\bssn\b", r"account number", r"credit card \d"], "Unmasked PII in bot response"),
    ([r"discriminat", r"deny.*loan", r"only lend to"], "Discriminatory lending language in response"),
]


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
    policy_reason: str = ""
    violated_rule: str = ""
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
                    policy_reason TEXT,
                    violated_rule TEXT,
                    timestamp TEXT
                )
            """)
            for col in ("policy_reason", "violated_rule"):
                try:
                    conn.execute(f"ALTER TABLE violations ADD COLUMN {col} TEXT")
                except sqlite3.OperationalError:
                    pass
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
                    guarded_response, activated_rails, policy_reason, violated_rule,
                    timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    record.policy_reason,
                    record.violated_rule,
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


def _normalize_activated_rails(log_data: dict[str, Any] | None) -> list[str]:
    """Return rail names from guardrails log activated_rails (list or dict)."""
    log_data = log_data or {}
    activated = log_data.get("activated_rails", []) or []
    if isinstance(activated, dict):
        return [str(k) for k in activated.keys()]
    return [str(r) for r in activated]


def _rail_has_stop(log_data: dict[str, Any] | None) -> bool:
    """True if any rail in the log stopped the flow (stop: true)."""
    log_data = log_data or {}
    activated = log_data.get("activated_rails", []) or []
    if isinstance(activated, dict):
        for rail_info in activated.values():
            if isinstance(rail_info, dict) and rail_info.get("stop"):
                return True
    for key in ("rails", "rail_events", "internal_events"):
        events = log_data.get(key)
        if isinstance(events, list):
            for event in events:
                if isinstance(event, dict) and event.get("stop"):
                    return True
    return False


def _stopped_rail_names(log_data: dict[str, Any] | None) -> list[str]:
    """Rail names that stopped the flow when triggered_*_rail is unset."""
    log_data = log_data or {}
    stopped: list[str] = []
    activated = log_data.get("activated_rails", []) or []
    if isinstance(activated, dict):
        for name, rail_info in activated.items():
            if isinstance(rail_info, dict) and rail_info.get("stop"):
                stopped.append(str(name))
    for key in ("rails", "rail_events", "internal_events"):
        events = log_data.get(key)
        if isinstance(events, list):
            for event in events:
                if isinstance(event, dict) and event.get("stop"):
                    name = event.get("rail") or event.get("name")
                    if name:
                        stopped.append(str(name))
    return stopped


def _normalize_rail_name(rail: str) -> str:
    """Strip input:/output: prefix from rail identifiers."""
    if ":" in rail:
        return rail.split(":", 1)[1].strip().lower()
    return rail.strip().lower()


def _iter_activated_rail_entries(log_data: dict[str, Any] | None) -> Iterator[dict[str, Any]]:
    """Yield activated rail dicts from NeMo log (list or name→info dict)."""
    log_data = log_data or {}
    activated = log_data.get("activated_rails") or []
    if isinstance(activated, dict):
        for name, info in activated.items():
            entry = dict(info) if isinstance(info, dict) else {}
            entry.setdefault("name", name)
            yield entry
    elif isinstance(activated, list):
        for entry in activated:
            if isinstance(entry, dict):
                yield entry
            else:
                yield {"name": str(entry)}


def _iter_llm_calls(log_data: dict[str, Any] | None) -> Iterator[dict[str, Any]]:
    """Yield LLM call dicts from activated_rails actions and top-level log."""
    log_data = log_data or {}
    for entry in _iter_activated_rail_entries(log_data):
        for action in entry.get("executed_actions") or []:
            if not isinstance(action, dict):
                continue
            for call in action.get("llm_calls") or []:
                if isinstance(call, dict):
                    yield call
    for call in log_data.get("llm_calls") or []:
        if isinstance(call, dict):
            yield call


def _completion_is_yes(completion: str) -> bool:
    text = (completion or "").strip().lower()
    if not text:
        return False
    first = text.splitlines()[0].strip()
    return first.startswith("yes") or first == "y"


def _parse_violated_rule_from_completion(completion: str) -> str:
    """Extract 'Violated rule: ...' line from self_check LLM completion."""
    if not completion:
        return ""
    for line in completion.splitlines():
        match = re.search(r"violated rule:\s*(.+)", line, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip().rstrip(".")
    return ""


def _extract_policy_bullets(prompt: str) -> list[str]:
    bullets: list[str] = []
    for line in (prompt or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            bullets.append(stripped[2:].strip())
    return bullets


def _humanize_policy_bullet(bullet: str) -> str:
    lower = bullet.lower()
    if "investment advice" in lower or "crypto" in lower or "stock" in lower:
        return "Investment advice not permitted (mutual funds, crypto, stocks, ETFs)"
    if "bypass safety" in lower or "system prompt" in lower:
        return "Prompt injection / jailbreak attempt"
    if "politic" in lower or "competitor" in lower or "unrelated topic" in lower:
        return "Off-topic request (politics, competitors, or unrelated topics)"
    if "discriminat" in lower or "abusive" in lower:
        return "Discriminatory or abusive language not permitted"
    if "ssn" in lower or "pii" in lower or "account number" in lower:
        return "Raw PII in message not permitted"
    if "fdic" in lower:
        return "Missing required FDIC disclaimer for deposit discussion"
    if bullet.lower().startswith("should not ") or bullet.lower().startswith("must not "):
        return bullet[0].upper() + bullet[1:]
    return bullet


def _infer_reason_from_hints(text: str, hints: list[tuple[list[str], str]]) -> str:
    lower = text.lower()
    for patterns, reason in hints:
        if any(re.search(pat, lower) for pat in patterns):
            return reason
    return ""


def _infer_from_prompt_bullets(prompt: str, query: str) -> str:
    query_lower = query.lower()
    for bullet in _extract_policy_bullets(prompt):
        lower = bullet.lower()
        if not (lower.startswith("should not") or lower.startswith("must not")):
            continue
        keywords = re.findall(r"\(([^)]+)\)", bullet)
        terms = [t.strip() for group in keywords for t in group.split(",")]
        for term in terms:
            if term and term.lower() in query_lower:
                return _humanize_policy_bullet(bullet)
        for word in re.findall(r"[a-z]{4,}", lower):
            if word in {"should", "contain", "discuss", "attempt", "reveal"}:
                continue
            if word in query_lower:
                return _humanize_policy_bullet(bullet)
    return ""


def _find_self_check_llm_call(
    log_data: dict[str, Any] | None,
    rail_name: str,
    rail_type: str,
) -> dict[str, Any] | None:
    """Find the self_check LLM call for a blocking rail."""
    log_data = log_data or {}
    target = _normalize_rail_name(rail_name)
    task_hints = ("self_check_input", "self_check_output", "self check")

    for entry in _iter_activated_rail_entries(log_data):
        entry_name = str(entry.get("name", "")).lower()
        if target and entry_name and target not in entry_name and "self check" not in entry_name:
            continue
        if entry.get("stop") is False and target:
            continue
        for call in _iter_llm_calls({"activated_rails": [entry]}):
            task = str(call.get("task") or "").lower()
            prompt = str(call.get("prompt") or "").lower()
            if any(h in task or h in prompt for h in task_hints):
                if rail_type == "output" and "output" not in task and "bot response" not in prompt:
                    continue
                if rail_type == "input" and "output" in task and "user message" not in prompt:
                    continue
                return call

    for call in _iter_llm_calls(log_data):
        task = str(call.get("task") or "").lower()
        prompt = str(call.get("prompt") or "").lower()
        if not any(h in task or h in prompt for h in task_hints):
            continue
        if rail_type == "output" and "bot response" not in prompt:
            continue
        if rail_type == "input" and "user message" not in prompt and "bot response" in prompt:
            continue
        return call
    return None


def extract_policy_reason(
    rail_name: str,
    rail_type: str,
    query: str,
    log_data: dict[str, Any] | None,
) -> tuple[str, str]:
    """Return (policy_reason, violated_rule) for a blocking rail."""
    normalized = _normalize_rail_name(rail_name)

    if "detect sensitive data" in normalized:
        if "output" in normalized:
            reason = POLICY_REASONS["detect sensitive data on output"]
        else:
            reason = POLICY_REASONS["detect sensitive data on input"]
        return reason, reason

    if "jailbreak" in normalized:
        reason = POLICY_REASONS["check jailbreak"]
        return reason, reason

    call = _find_self_check_llm_call(log_data, rail_name, rail_type)
    completion = str((call or {}).get("completion") or "")
    prompt = str((call or {}).get("prompt") or "")

    violated_rule = _parse_violated_rule_from_completion(completion)
    if violated_rule:
        humanized = _humanize_policy_bullet(violated_rule)
        return humanized, humanized

    if call and _completion_is_yes(completion):
        from_prompt = _infer_from_prompt_bullets(prompt, query)
        if from_prompt:
            return from_prompt, from_prompt

    hints = _OUTPUT_REASON_HINTS if rail_type == "output" else _QUERY_REASON_HINTS
    inferred = _infer_reason_from_hints(query, hints)
    if inferred:
        return inferred, inferred

    if call and prompt:
        from_prompt = _infer_from_prompt_bullets(prompt, query)
        if from_prompt:
            return from_prompt, from_prompt

    fallback = POLICY_REASONS.get(normalized, "")
    if fallback:
        return fallback, fallback

    return "", ""


def is_actual_violation(
    output_vars: dict[str, Any] | None,
    log_data: dict[str, Any] | None = None,
) -> bool:
    """True when guardrails blocked or a rail explicitly stopped the request."""
    output_vars = output_vars or {}
    if output_vars.get("allowed") is False:
        return True
    if output_vars.get("triggered_input_rail"):
        return True
    if output_vars.get("triggered_output_rail"):
        return True
    return _rail_has_stop(log_data)


def policies_checked_and_passed(
    policies: list[str],
    output_vars: dict[str, Any] | None,
    log_data: dict[str, Any] | None = None,
) -> bool:
    """True when policies ran but no block was recorded."""
    if not policies or is_actual_violation(output_vars, log_data):
        return False
    log_data = log_data or {}
    output_vars = output_vars or {}
    if log_data.get("activated_rails"):
        return True
    return "allowed" in output_vars and output_vars.get("allowed") is not False


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

    if not is_actual_violation(output_vars, log_data):
        return records

    triggered_input = output_vars.get("triggered_input_rail")
    triggered_output = output_vars.get("triggered_output_rail")
    allowed = output_vars.get("allowed", True)
    activated = _normalize_activated_rails(log_data)

    rail_names: list[tuple[str, str]] = []
    if triggered_input:
        rail_names.append(("input", str(triggered_input)))
    if triggered_output:
        rail_names.append(("output", str(triggered_output)))

    if not rail_names and not allowed:
        rail_names.append(("input", "blocked"))

    if not rail_names:
        for rail in _stopped_rail_names(log_data):
            rail_names.append(("unknown", rail))
        if not rail_names:
            rail_names.append(("unknown", "blocked"))

    policy_label = ",".join(policies) if policies else "none"

    for rail_type, rail_name in rail_names:
        policy = _infer_policy(rail_name, policies) or policy_label
        bare_rail = _normalize_rail_name(rail_name)
        policy_reason, violated_rule = extract_policy_reason(
            bare_rail, rail_type, query, log_data
        )
        if not policy_reason and output_vars.get("policy_reason"):
            policy_reason = str(output_vars["policy_reason"])
            violated_rule = policy_reason
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
                activated_rails=activated,
                policy_reason=policy_reason,
                violated_rule=violated_rule,
                run_id=run_id,
            )
        )

    if not allowed and not records:
        policy_reason, violated_rule = extract_policy_reason("blocked", "unknown", query, log_data)
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
                activated_rails=activated,
                policy_reason=policy_reason,
                violated_rule=violated_rule,
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
