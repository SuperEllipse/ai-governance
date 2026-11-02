import { CopyButton } from "./CopyButton";

/** Collapsible pretty-printed JSON block (Agent Trace, Guardrails Log). */
export function JsonPanel({ title, data }: { title: string; data: unknown }) {
  const json = JSON.stringify(data, null, 2);
  return (
    <details className="disclosure">
      <summary>{title}</summary>
      <div className="disclosure-body">
        <div className="disclosure-actions">
          <CopyButton text={json} label="Copy JSON" />
        </div>
        <pre>{json}</pre>
      </div>
    </details>
  );
}
