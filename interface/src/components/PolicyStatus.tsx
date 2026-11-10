import type { QueryResult } from "../api/types";

function firstReason(result: QueryResult): string {
  for (const v of result.violations) {
    const reason = v.policy_reason || v.violated_rule;
    if (reason) return reason;
  }
  const fromVars = result.output_vars.policy_reason;
  return typeof fromVars === "string" ? fromVars : "";
}

/** Blocked / passed / infrastructure-error banner for the guarded column. */
export function PolicyStatus({ result }: { result: QueryResult }) {
  const vars = result.output_vars;
  const rail = (vars.triggered_input_rail || vars.triggered_output_rail) as string | undefined;

  if (result.infra_error && !result.actual_violation) {
    return (
      <div className="banner banner-warning" role="status">
        <span className="banner-icon" aria-hidden="true">!</span>
        <div>
          <strong>Safety check did not complete</strong>
          <p className="small">{result.infra_error}</p>
        </div>
      </div>
    );
  }

  if (result.actual_violation) {
    const reason = firstReason(result);
    return (
      <div className="banner banner-critical" role="status">
        <span className="banner-icon" aria-hidden="true">✕</span>
        <div>
          <strong>Request blocked by safety policy</strong>
          {rail && (
            <p className="small">
              Rail: <code>{rail}</code>
            </p>
          )}
          {reason && <p className="small">Policy violated: {reason}</p>}
        </div>
      </div>
    );
  }

  if (result.checks_passed) {
    return (
      <div className="banner banner-good" role="status">
        <span className="banner-icon" aria-hidden="true">✓</span>
        <div>
          <strong>Policies checked — no violations</strong>
        </div>
      </div>
    );
  }

  return null;
}
