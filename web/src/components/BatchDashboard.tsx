import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, watchBatch } from "../api/client";
import type { BatchRun, ViolationRow } from "../api/types";
import { MODE_LABELS, humanize } from "../labels";
import { useSettings } from "../state/SettingsContext";
import { BarChart } from "./BarChart";
import { Markdown } from "./Markdown";

const SAMPLE_SIZES = [10, 25, 50, 100] as const;
const DRILLDOWN_CHARS = 2000;
const ALL_RUNS = "__all__";

interface Progress {
  current: number;
  total: number;
  message: string;
}

function countBy(rows: ViolationRow[], key: (r: ViolationRow) => string) {
  const counts = new Map<string, number>();
  for (const r of rows) {
    const k = key(r) || "unknown";
    counts.set(k, (counts.get(k) ?? 0) + 1);
  }
  return [...counts.entries()]
    .map(([label, value]) => ({ label: humanize(label), value }))
    .sort((a, b) => b.value - a.value);
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}

const CSV_COLUMNS: (keyof ViolationRow)[] = [
  "id", "run_id", "timestamp", "query", "policy", "rail", "blocked", "category", "expected_policy",
  "agent", "policy_reason", "violated_rule", "unguarded_response", "guarded_response",
];

function toCsv(rows: ViolationRow[]): string {
  const cell = (v: unknown) => {
    const text = Array.isArray(v) ? v.join("; ") : String(v ?? "");
    return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
  };
  return [CSV_COLUMNS.join(","), ...rows.map((r) => CSV_COLUMNS.map((c) => cell(r[c])).join(","))].join("\r\n");
}

function downloadCsv(rows: ViolationRow[], name: string) {
  const blob = new Blob(["﻿" + toCsv(rows)], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

export function BatchDashboard({ datasetSize }: { datasetSize: number }) {
  const { settings } = useSettings();
  const [sampleSize, setSampleSize] = useState<number>(100);
  const [job, setJob] = useState<{ jobId: string; runId: string } | null>(null);
  const [progress, setProgress] = useState<Progress | null>(null);
  const [outcome, setOutcome] = useState<{ tone: "good" | "warning"; text: string } | null>(null);
  const [error, setError] = useState("");
  const [runs, setRuns] = useState<BatchRun[]>([]);
  const [selectedRun, setSelectedRun] = useState<string>(""); // run_id, ALL_RUNS, or "" before load
  const [rows, setRows] = useState<ViolationRow[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [policyFilter, setPolicyFilter] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [search, setSearch] = useState("");
  const stopWatching = useRef<(() => void) | null>(null);
  const running = job !== null;

  const loadRuns = useCallback(async (select?: string) => {
    try {
      const data = await api.batchRuns();
      setRuns(data);
      setSelectedRun((current) => select ?? (current || data[0]?.run_id || ALL_RUNS));
    } catch (err) {
      setError((err as Error).message);
    }
  }, []);

  useEffect(() => {
    loadRuns();
    return () => stopWatching.current?.();
  }, [loadRuns]);

  useEffect(() => {
    if (!selectedRun) return;
    let cancelled = false;
    // Reset filters when switching runs so a stale filter can't hide everything.
    setPolicyFilter("");
    setCategoryFilter("");
    setSearch("");
    api
      .violations(selectedRun === ALL_RUNS ? undefined : selectedRun)
      .then((data) => {
        if (cancelled) return;
        setRows(data);
        setSelectedId(data[0]?.id ?? null);
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedRun]);

  const run = async () => {
    setError("");
    setOutcome(null);
    setProgress({ current: 0, total: sampleSize, message: "Starting…" });
    try {
      const { job_id, run_id } = await api.startBatch(sampleSize, settings);
      setJob({ jobId: job_id, runId: run_id });
      stopWatching.current = watchBatch(job_id, (event) => {
        if (event.type === "progress") {
          setProgress(event);
          return;
        }
        setJob(null);
        if (event.type === "done") {
          setProgress((p) => (p ? { ...p, current: p.total, message: "Batch complete." } : p));
          setOutcome({
            tone: "good",
            text: `Run ${event.summary.run_id} finished: ${event.summary.violation_count} of ${event.summary.total_queries} queries blocked.`,
          });
          loadRuns(event.summary.run_id);
        } else if (event.type === "cancelled") {
          setProgress(null);
          setOutcome({
            tone: "warning",
            text: `Run ${event.run_id} cancelled after ${event.current} of ${event.total} queries. Results so far are kept.`,
          });
          loadRuns(event.run_id);
        } else {
          setProgress(null);
          setError(event.message);
        }
      });
    } catch (err) {
      setJob(null);
      setProgress(null);
      setError((err as Error).message);
    }
  };

  const cancel = async () => {
    if (!job) return;
    try {
      await api.cancelBatch(job.jobId);
      setProgress((p) => (p ? { ...p, message: "Cancelling after the current query…" } : p));
    } catch (err) {
      setError((err as Error).message);
    }
  };

  const runInfo = runs.find((r) => r.run_id === selectedRun) ?? null;
  const policyOptions = useMemo(() => [...new Set(rows.map((r) => r.policy).filter(Boolean))].sort(), [rows]);
  const categoryOptions = useMemo(() => [...new Set(rows.map((r) => r.category).filter(Boolean))].sort(), [rows]);
  const filtered = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return rows.filter(
      (r) =>
        (!policyFilter || r.policy === policyFilter) &&
        (!categoryFilter || r.category === categoryFilter) &&
        (!needle || `${r.query} ${r.policy_reason} ${r.violated_rule}`.toLowerCase().includes(needle)),
    );
  }, [rows, policyFilter, categoryFilter, search]);

  const selected = filtered.find((r) => r.id === selectedId) ?? filtered[0] ?? null;
  const pct = progress && progress.total ? (progress.current / progress.total) * 100 : 0;
  const stats = runInfo
    ? { total: runInfo.total_queries, blocked: runInfo.violation_count }
    : selectedRun === ALL_RUNS && runs.length > 0
      ? {
          total: runs.reduce((s, r) => s + r.total_queries, 0),
          blocked: runs.reduce((s, r) => s + r.violation_count, 0),
        }
      : null;

  return (
    <section className="view">
      <div className="page-head">
        <h2>Batch Simulation Dashboard</h2>
        <p>Run the labeled query dataset through the guarded path and review violations.</p>
      </div>

      <div className="card">
        <div className="toolbar">
          <label className="field">
            <span>Sample size</span>
            <select
              className="select"
              value={sampleSize}
              disabled={running}
              onChange={(e) => setSampleSize(Number(e.target.value))}
            >
              {SAMPLE_SIZES.map((n) => (
                <option key={n} value={n}>
                  {n} queries
                </option>
              ))}
            </select>
          </label>
          {running ? (
            <button className="btn" onClick={cancel}>
              Cancel batch
            </button>
          ) : (
            <button className="btn btn-primary" onClick={run}>
              Run batch simulation
            </button>
          )}
          <span className="hint">
            Dataset: {datasetSize} queries · Mode:{" "}
            {settings.mode === "unguarded" ? "Embedded (batch always runs guarded)" : MODE_LABELS[settings.mode]} ·{" "}
            {settings.policies.length} active {settings.policies.length === 1 ? "policy" : "policies"}
          </span>
        </div>
        {settings.policies.length === 0 && !running && (
          <div className="banner banner-warning small" role="note" style={{ marginTop: 16 }}>
            <span className="banner-icon" aria-hidden="true">!</span>
            <p>No policies selected: every query runs unguarded, so no violations will be recorded.</p>
          </div>
        )}
        {sampleSize <= 40 && !running && (
          <p className="hint" style={{ marginTop: 12 }}>
            The first 40 dataset queries are all happy-path, so a sample of {sampleSize} contains no
            policy-violating queries. Use 50 or 100 to see violations.
          </p>
        )}
        {progress && (
          <div className="progress" style={{ marginTop: 16 }} aria-live="polite">
            <div
              className="progress-track"
              role="progressbar"
              aria-valuemin={0}
              aria-valuemax={progress.total}
              aria-valuenow={progress.current}
            >
              <div className="progress-fill" style={{ width: `${pct}%` }} />
            </div>
            <span className="small secondary">
              [{progress.current}/{progress.total}] {progress.message}
            </span>
          </div>
        )}
        {outcome && (
          <div className={`banner banner-${outcome.tone} small`} role="status" style={{ marginTop: 16 }}>
            <span className="banner-icon" aria-hidden="true">{outcome.tone === "good" ? "✓" : "!"}</span>
            <p>{outcome.text}</p>
          </div>
        )}
      </div>

      {error && (
        <div className="banner banner-critical" role="alert">
          <span className="banner-icon" aria-hidden="true">!</span>
          <div>
            <strong>Batch error</strong>
            <p className="small">{error}</p>
          </div>
        </div>
      )}

      {runs.length > 0 && (
        <div className="run-picker">
          <label className="field">
            <span>Showing</span>
            <select className="select" value={selectedRun} onChange={(e) => setSelectedRun(e.target.value)}>
              {runs.map((r, i) => (
                <option key={r.run_id} value={r.run_id}>
                  {i === 0 ? "Latest · " : ""}
                  {formatDate(r.started_at)} · {r.violation_count}/{r.total_queries} blocked · {r.run_id}
                </option>
              ))}
              <option value={ALL_RUNS}>All runs</option>
            </select>
          </label>
        </div>
      )}

      {stats && (
        <div className="stat-grid">
          <Stat label="Queries run" value={stats.total.toLocaleString()} />
          <Stat label="Blocked" value={stats.blocked.toLocaleString()} />
          <Stat label="Block rate" value={stats.total ? `${((stats.blocked / stats.total) * 100).toFixed(1)}%` : "—"} />
          <Stat
            label={runInfo ? "Run ID" : "Runs"}
            value={runInfo ? runInfo.run_id : runs.length.toLocaleString()}
            sub={runInfo ? formatDate(runInfo.started_at) : undefined}
          />
        </div>
      )}

      {rows.length > 0 && (
        <div className="chart-grid">
          <BarChart title="Violations by policy" data={countBy(rows, (r) => r.policy)} unit="violations" />
          <BarChart title="Violations by category" data={countBy(rows, (r) => r.category)} unit="violations" />
        </div>
      )}

      <div className="card">
        <div className="card-title">
          <h3>Violation log</h3>
          <span className="small muted">
            {filtered.length === rows.length ? `${rows.length} rows` : `${filtered.length} of ${rows.length} rows`}
          </span>
          <button
            className="btn btn-sm"
            style={{ marginLeft: "auto" }}
            disabled={filtered.length === 0}
            onClick={() => downloadCsv(filtered, `violations-${runInfo?.run_id ?? "all-runs"}.csv`)}
          >
            Export CSV
          </button>
        </div>
        {rows.length > 0 && (
          <div className="filters">
            <input
              className="input"
              type="search"
              placeholder="Search query or reason…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              aria-label="Search violations"
            />
            <select
              className="select"
              value={policyFilter}
              onChange={(e) => setPolicyFilter(e.target.value)}
              aria-label="Filter by policy"
            >
              <option value="">All policies</option>
              {policyOptions.map((p) => (
                <option key={p} value={p}>
                  {humanize(p)}
                </option>
              ))}
            </select>
            <select
              className="select"
              value={categoryFilter}
              onChange={(e) => setCategoryFilter(e.target.value)}
              aria-label="Filter by category"
            >
              <option value="">All categories</option>
              {categoryOptions.map((c) => (
                <option key={c} value={c}>
                  {humanize(c)}
                </option>
              ))}
            </select>
          </div>
        )}
        {rows.length === 0 ? (
          <p className="empty">No violations logged for this selection. Run a batch simulation.</p>
        ) : filtered.length === 0 ? (
          <p className="empty">No rows match the filters.</p>
        ) : (
          <div className="table-wrap">
            <table className="log-table">
              <thead>
                <tr>
                  <th style={{ width: 56 }}>ID</th>
                  <th>Query</th>
                  <th>Policy</th>
                  <th>Rail</th>
                  <th>Blocked</th>
                  <th>Time</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((r) => (
                  <tr
                    key={r.id}
                    className={`selectable${r.id === selected?.id ? " selected" : ""}`}
                    onClick={() => setSelectedId(r.id)}
                    tabIndex={0}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        setSelectedId(r.id);
                      }
                    }}
                    aria-selected={r.id === selected?.id}
                  >
                    <td className="num">{r.id}</td>
                    <td className="truncate" title={r.query}>
                      {r.query}
                    </td>
                    <td className="nowrap">{humanize(r.policy)}</td>
                    <td className="nowrap small">{r.rail}</td>
                    <td>{r.blocked ? "Yes" : "No"}</td>
                    <td className="nowrap small muted">
                      {new Date(r.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {selected && <Drilldown row={selected} />}
    </section>
  );
}

function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="card stat">
      <span className="stat-label">{label}</span>
      <span className="stat-value">{value}</span>
      {sub && <span className="stat-sub">{sub}</span>}
    </div>
  );
}

function Drilldown({ row }: { row: ViolationRow }) {
  return (
    <div className="card drilldown">
      <div className="card-title" style={{ marginBottom: 0 }}>
        <h3>Drill-down · violation #{row.id}</h3>
      </div>
      <p>
        <strong>Query:</strong> {row.query}
      </p>
      <dl className="detail-grid">
        <dt>Policy</dt>
        <dd>{humanize(row.policy)}</dd>
        <dt>Rail</dt>
        <dd>
          <code>{row.rail}</code>
        </dd>
        <dt>Category</dt>
        <dd>{row.category ? humanize(row.category) : "—"}</dd>
        <dt>Reason</dt>
        <dd>{row.policy_reason || row.violated_rule || "—"}</dd>
        <dt>Agent</dt>
        <dd>{row.agent || "N/A"}</dd>
        <dt>Activated rails</dt>
        <dd>{row.activated_rails.length ? row.activated_rails.join(", ") : "none"}</dd>
        <dt>Time</dt>
        <dd>{formatDate(row.timestamp)}</dd>
      </dl>
      <div className="compare">
        <div className="response-panel">
          <span className="panel-tag panel-tag-unguarded" style={{ alignSelf: "flex-start" }}>
            Unguarded response
          </span>
          <div className="response-box">
            <Markdown text={(row.unguarded_response || "").slice(0, DRILLDOWN_CHARS)} />
          </div>
        </div>
        <div className="response-panel">
          <span className="panel-tag panel-tag-guarded" style={{ alignSelf: "flex-start" }}>
            Guarded response
          </span>
          <div className="response-box">
            <Markdown text={(row.guarded_response || "").slice(0, DRILLDOWN_CHARS)} />
          </div>
        </div>
      </div>
    </div>
  );
}
