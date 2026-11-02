import { useEffect, useRef, useState, type FormEvent } from "react";
import { api } from "../api/client";
import type { ExampleQuery, QueryResult } from "../api/types";
import { MODE_LABELS, blockKind, formatPolicies } from "../labels";
import { useSettings } from "../state/SettingsContext";
import { useStatus } from "../state/StatusContext";
import { CopyButton } from "./CopyButton";
import { DemoGuide } from "./DemoGuide";
import { JsonPanel } from "./JsonPanel";
import { Markdown } from "./Markdown";
import { PolicyStatus } from "./PolicyStatus";

const HISTORY_LIMIT = 20;

interface HistoryEntry {
  id: number;
  at: Date;
  result: QueryResult;
}

function formatSeconds(ms: number): string {
  return ms < 10_000 ? `${(ms / 1000).toFixed(1)} s` : `${Math.round(ms / 1000)} s`;
}

function useElapsed(running: boolean): number {
  const [elapsed, setElapsed] = useState(0);
  const started = useRef(0);
  useEffect(() => {
    if (!running) return;
    started.current = performance.now();
    setElapsed(0);
    const t = window.setInterval(() => setElapsed(performance.now() - started.current), 250);
    return () => window.clearInterval(t);
  }, [running]);
  return elapsed;
}

export function ChatCompare({ examples }: { examples: ExampleQuery[] }) {
  const { config, settings, suggestion, applyExample } = useSettings();
  const { problems } = useStatus();
  const [query, setQuery] = useState("");
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [viewingId, setViewingId] = useState<number | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const nextId = useRef(1);
  const elapsed = useElapsed(running);

  const viewing = history.find((h) => h.id === viewingId) ?? null;

  const pickExample = (ex: ExampleQuery) => {
    applyExample(ex);
    setQuery(ex.query);
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const text = query.trim();
    if (!text || running) return;
    setRunning(true);
    setError("");
    try {
      const result = await api.query(text, settings);
      const entry = { id: nextId.current++, at: new Date(), result };
      setHistory((prev) => [entry, ...prev].slice(0, HISTORY_LIMIT));
      setViewingId(entry.id);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setRunning(false);
    }
  };

  // Problems that will make this query fail (server status only matters in server mode).
  const blocking = problems.filter((p) => p.key !== "server" || settings.mode === "server");

  return (
    <section className="view">
      <div className="page-head">
        <h2>Chat Compare</h2>
        <p>Side-by-side unguarded vs guarded responses for the same customer query.</p>
      </div>

      <div className="examples" aria-label="Example queries">
        {examples.map((ex) => {
          const kind = blockKind(ex.block_type);
          return (
            <button
              key={ex.label}
              className="example"
              aria-pressed={suggestion?.label === ex.label}
              onClick={() => pickExample(ex)}
            >
              <span className={`badge badge-${kind}`}>
                <span className="badge-dot" aria-hidden="true" />
                {ex.block_type}
              </span>
              <span className="example-label">{ex.label}</span>
            </button>
          );
        })}
      </div>

      {suggestion && (
        <div className="banner banner-info small" role="status">
          <span className="banner-icon" aria-hidden="true">i</span>
          <p>
            <strong className="inline">{suggestion.label}:</strong> settings switched to{" "}
            {MODE_LABELS[suggestion.recommended_mode]} with{" "}
            {formatPolicies(suggestion.recommended_policies, config.policy_options)}. Expected rail:{" "}
            <code>{suggestion.expected_rail || "none (passes)"}</code>
          </p>
        </div>
      )}

      <DemoGuide examples={examples} />

      <div className="chat-grid">
        <form className="card composer" onSubmit={submit}>
          <label className="field">
            <span>Customer query</span>
            <textarea
              className="textarea"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) submit(e);
              }}
              placeholder="e.g. What are your current 30-year mortgage rates?"
            />
          </label>
          {blocking.length > 0 && (
            <div className="banner banner-warning small" role="note">
              <span className="banner-icon" aria-hidden="true">!</span>
              <div>
                <strong>This query will probably fail</strong>
                {blocking.map((p) => (
                  <p key={p.key}>{p.message}</p>
                ))}
              </div>
            </div>
          )}
          <div className="composer-actions">
            <button className="btn btn-primary" type="submit" disabled={running || !query.trim()}>
              {running && <span className="spinner" aria-hidden="true" />}
              {running ? `Running… ${Math.floor(elapsed / 1000)} s` : "Send query"}
            </button>
            <span className="hint">
              {MODE_LABELS[settings.mode]} ·{" "}
              {settings.mode === "unguarded" ? "no safety rails" : formatPolicies(settings.policies, config.policy_options)}
              {" · "}Ctrl+Enter to send
            </span>
          </div>
        </form>

        <HistoryList
          history={history}
          viewingId={viewingId}
          onSelect={setViewingId}
          onClear={() => {
            setHistory([]);
            setViewingId(null);
          }}
        />
      </div>

      {error && (
        <div className="banner banner-critical" role="alert">
          <span className="banner-icon" aria-hidden="true">!</span>
          <div>
            <strong>Request failed</strong>
            <p className="small">{error}</p>
          </div>
        </div>
      )}

      {viewing ? <ResultView result={viewing.result} /> : !running && <EmptyState />}
    </section>
  );
}

function HistoryList({
  history,
  viewingId,
  onSelect,
  onClear,
}: {
  history: HistoryEntry[];
  viewingId: number | null;
  onSelect: (id: number) => void;
  onClear: () => void;
}) {
  return (
    <div className="card history">
      <div className="card-title">
        <h3>Recent queries</h3>
        {history.length > 0 && (
          <button className="btn-link" style={{ marginLeft: "auto" }} onClick={onClear}>
            Clear
          </button>
        )}
      </div>
      {history.length === 0 ? (
        <p className="hint">Queries you send in this session appear here. Click one to view it again.</p>
      ) : (
        <ul className="history-list">
          {history.map((h) => {
            const blocked = h.result.actual_violation;
            return (
              <li key={h.id}>
                <button className={`history-item${h.id === viewingId ? " is-active" : ""}`} onClick={() => onSelect(h.id)}>
                  <span className="history-query">{h.result.query}</span>
                  <span className="history-meta">
                    <span className={`badge ${blocked ? "badge-input" : "badge-pass"}`}>
                      <span className="badge-dot" aria-hidden="true" />
                      {blocked ? "Blocked" : "Passed"}
                    </span>
                    <span>{MODE_LABELS[h.result.mode as keyof typeof MODE_LABELS] ?? h.result.mode}</span>
                    <span>{h.at.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</span>
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

function EmptyState() {
  return (
    <div className="card empty-state">
      <h3>Compare a query with and without guardrails</h3>
      <ol className="steps">
        <li>
          <span className="step-num">1</span>
          <span>
            <strong>Pick an example</strong> above (it also sets the recommended mode and policies) or type your own
            query.
          </span>
        </li>
        <li>
          <span className="step-num">2</span>
          <span>
            <strong>Send it.</strong> The banking agents answer first, then the guardrails check runs.
          </span>
        </li>
        <li>
          <span className="step-num">3</span>
          <span>
            <strong>Compare the columns:</strong> the unguarded reply on the left, the guarded reply or refusal on the
            right, plus which rail fired.
          </span>
        </li>
      </ol>
    </div>
  );
}

function ResultView({ result }: { result: QueryResult }) {
  const trace = result.agent_trace;
  return (
    <>
      <div className="compare" aria-live="polite">
        <article className="card response-panel">
          <header>
            <span className="panel-tag panel-tag-unguarded">Without guardrails</span>
            <span className="panel-actions">
              <CopyButton text={result.unguarded_response} />
            </span>
          </header>
          <Markdown text={result.unguarded_response} />
          <div className="meta-row">
            {trace.routed_agent && <span>Agent: {trace.routed_agent}</span>}
            {trace.tools_called.length > 0 && <span>Tools: {trace.tools_called.join(", ")}</span>}
          </div>
        </article>
        <article className="card response-panel">
          <header>
            <span className="panel-tag panel-tag-guarded">With guardrails</span>
            <span className="small muted">
              {MODE_LABELS[result.mode as keyof typeof MODE_LABELS] ?? result.mode}
              {typeof result.elapsed_ms === "number" && ` · ${formatSeconds(result.elapsed_ms)} total`}
            </span>
            <span className="panel-actions">
              <CopyButton text={result.guarded_response} />
            </span>
          </header>
          <PolicyStatus result={result} />
          <Markdown text={result.guarded_response} />
          {result.actual_violation && result.violations.length > 0 && (
            <ul className="violation-list">
              {result.violations.map((v, i) => (
                <li key={i}>
                  <strong>Policy:</strong> {v.policy} · <strong>Rail:</strong> {v.rail} ·{" "}
                  <strong>Blocked:</strong> {v.blocked ? "yes" : "no"}
                  {(v.policy_reason || v.violated_rule) && (
                    <>
                      {" "}· <strong>Reason:</strong> {v.policy_reason || v.violated_rule}
                    </>
                  )}
                </li>
              ))}
            </ul>
          )}
        </article>
      </div>
      <JsonPanel title="Agent Trace" data={trace} />
      <JsonPanel
        title="Guardrails Log"
        data={{
          output_vars: result.output_vars,
          log: result.guardrails_log,
          ...(result.violations.length > 0 && {
            policy_violations: result.violations.map((v) => ({
              rail: v.rail,
              policy: v.policy,
              policy_reason: v.policy_reason,
              violated_rule: v.violated_rule,
            })),
          }),
        }}
      />
    </>
  );
}
