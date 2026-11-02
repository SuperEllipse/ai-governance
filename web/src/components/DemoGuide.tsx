import type { ExampleQuery } from "../api/types";
import { MODE_LABELS, formatPolicies } from "../labels";
import { useSettings } from "../state/SettingsContext";

export function DemoGuide({ examples }: { examples: ExampleQuery[] }) {
  const { config } = useSettings();
  return (
    <details className="disclosure">
      <summary>Demo guide: block types</summary>
      <div className="disclosure-body prose">
        <ul>
          <li>
            <strong>Centralized Server</strong> uses <code>guardrails/base/config.yml</code> only
            (self_check input + output). Policy checkboxes do <strong>not</strong> change the
            server config. Best for investment-advice / topic blocks.
          </li>
          <li>
            <strong>Embedded</strong> composes policies from the checkboxes via{" "}
            <code>config_composer</code> and checks input, then output — best for PII input
            blocks and output policy blocks (e.g. missing FDIC disclaimer).
          </li>
        </ul>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Example</th>
                <th>Block type</th>
                <th>Mode</th>
                <th>Policies</th>
                <th>Expected rail</th>
              </tr>
            </thead>
            <tbody>
              {examples.map((ex) => (
                <tr key={ex.label}>
                  <td>{ex.label}</td>
                  <td>{ex.block_type}</td>
                  <td>{MODE_LABELS[ex.recommended_mode]}</td>
                  <td>{formatPolicies(ex.recommended_policies, config.policy_options)}</td>
                  <td>{ex.expected_rail ? <code>{ex.expected_rail}</code> : "— (passes)"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="hint">
          Output-block demos may pass if the agent already includes required disclaimers. Try
          Embedded mode and open <strong>Guardrails Log</strong> to see{" "}
          <code>triggered_output_rail</code>.
        </p>
      </div>
    </details>
  );
}
