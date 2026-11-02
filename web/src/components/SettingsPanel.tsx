import { useState } from "react";
import type { GuardrailsMode, PolicyKey, Provider } from "../api/types";
import { useSettings } from "../state/SettingsContext";

const PROVIDERS: { key: Provider; label: string }[] = [
  { key: "openai", label: "OpenAI" },
  { key: "caiis", label: "Cloudera AI" },
];

const MODES: { key: GuardrailsMode; label: string; description: string }[] = [
  {
    key: "server",
    label: "Server",
    description: "Centralized NeMo Guardrails server; it writes and checks its own reply.",
  },
  {
    key: "embedded",
    label: "Embedded",
    description: "Checks the agents' own reply in-process, using the policies below.",
  },
  { key: "unguarded", label: "Unguarded", description: "No safety rails; both columns show the agents' reply." },
];

export function SettingsPanel() {
  const { config, settings, update, setProvider, resetToDefaults } = useSettings();
  const providerDefaults = config.providers[settings.provider];
  const isCaiis = settings.provider === "caiis";
  const caiisMismatch = settings.provider === "openai" && config.caiis_configured;
  const [connectionOpen, setConnectionOpen] = useState(caiisMismatch);

  const order = config.policy_options.map((p) => p.key);
  const setPolicies = (keys: PolicyKey[]) => update({ policies: order.filter((k) => keys.includes(k)) });
  const togglePolicy = (key: PolicyKey, checked: boolean) =>
    setPolicies(checked ? [...settings.policies, key] : settings.policies.filter((p) => p !== key));

  const policiesNote =
    settings.mode === "server"
      ? "Server mode uses guardrails/base only — these apply in Embedded mode."
      : settings.mode === "unguarded"
        ? "No rails run in Unguarded mode."
        : "";

  const keySource = settings.api_key ? "key entered" : providerDefaults.has_api_key ? "server key" : "no key";
  const providerLabel = PROVIDERS.find((p) => p.key === settings.provider)?.label ?? settings.provider;
  const activeMode = MODES.find((m) => m.key === settings.mode);

  return (
    <aside className="settings" aria-label="Settings">
      <div className="settings-head">
        <h2>Settings</h2>
        <button className="btn-link" onClick={resetToDefaults}>
          Reset to defaults
        </button>
      </div>

      <section className="settings-section">
        <h3>Guardrails mode</h3>
        <div className="segmented" role="group" aria-label="Guardrails mode">
          {MODES.map((m) => (
            <button key={m.key} aria-pressed={settings.mode === m.key} onClick={() => update({ mode: m.key })}>
              {m.label}
            </button>
          ))}
        </div>
        {activeMode && <p className="hint">{activeMode.description}</p>}
      </section>

      <section className="settings-section">
        <div className="section-head">
          <h3>Active policies</h3>
          <span className="section-actions">
            <button className="btn-link" onClick={() => setPolicies(order)}>
              All
            </button>
            <button className="btn-link" onClick={() => setPolicies([])}>
              None
            </button>
          </span>
        </div>
        <div className={`choice-list${policiesNote ? " is-muted" : ""}`}>
          {config.policy_options.map((opt) => (
            <label key={opt.key} className="choice">
              <input
                type="checkbox"
                checked={settings.policies.includes(opt.key)}
                onChange={(e) => togglePolicy(opt.key, e.target.checked)}
              />
              {opt.label}
            </label>
          ))}
        </div>
        {policiesNote && <p className="hint">{policiesNote}</p>}
      </section>

      <section className="settings-section">
        <h3>Safety check engine</h3>
        <div className="choice-list" role="radiogroup" aria-label="Safety check engine">
          {config.safety_options.map((opt) => (
            <label key={opt.key} className="choice">
              <input
                type="radio"
                name="safety-mode"
                checked={settings.safety_mode === opt.key}
                onChange={() => update({ safety_mode: opt.key })}
              />
              {opt.label}
            </label>
          ))}
        </div>
        {settings.safety_mode === "nim" && (
          <label className="field">
            <span>NVIDIA API key</span>
            <input
              className="input"
              type="password"
              autoComplete="off"
              value={settings.nim_api_key}
              placeholder={config.has_nim_api_key ? "Using server-configured key" : "Not configured"}
              onChange={(e) => update({ nim_api_key: e.target.value })}
            />
            {!config.has_nim_api_key && !settings.nim_api_key && (
              <span className="hint">NIM not configured — falls back to self_check behavior.</span>
            )}
          </label>
        )}
        {settings.safety_mode === "llama_guard" && (
          <>
            <label className="field">
              <span>Llama Guard base URL</span>
              <input
                className="input"
                value={settings.llama_guard_base_url}
                onChange={(e) => update({ llama_guard_base_url: e.target.value })}
              />
            </label>
            <label className="field">
              <span>Llama Guard model</span>
              <input
                className="input"
                value={settings.llama_guard_model}
                onChange={(e) => update({ llama_guard_model: e.target.value })}
              />
            </label>
            {!config.llama_guard.configured && settings.llama_guard_base_url.includes("YOUR-DOMAIN") && (
              <span className="hint">
                Set LLAMA_GUARD_BASE_URL (or LLAMA_GUARD_HOST + ENDPOINT) on the server, or enter your Llama Guard
                CAII endpoint above.
              </span>
            )}
          </>
        )}
      </section>

      <details
        className="settings-connection"
        open={connectionOpen}
        onToggle={(e) => setConnectionOpen(e.currentTarget.open)}
      >
        <summary>
          <span className="connection-title">Connection</span>
          <span className="connection-summary">
            {providerLabel} · {settings.model || providerDefaults.model} · {keySource}
          </span>
        </summary>
        <div className="settings-section connection-body">
          <div className="segmented" role="group" aria-label="LLM provider">
            {PROVIDERS.map((p) => (
              <button key={p.key} aria-pressed={settings.provider === p.key} onClick={() => setProvider(p.key)}>
                {p.label}
              </button>
            ))}
          </div>
          {caiisMismatch && (
            <div className="banner banner-warning small" role="note">
              <span className="banner-icon" aria-hidden="true">!</span>
              <p>Cloudera AI Inference is configured on the server but OpenAI is selected.</p>
            </div>
          )}
          <label className="field">
            <span>{isCaiis ? "CDP token (Bearer)" : "API key"}</span>
            <input
              className="input"
              type="password"
              autoComplete="off"
              value={settings.api_key}
              placeholder={providerDefaults.has_api_key ? "Using server-configured key" : "Not configured"}
              onChange={(e) => update({ api_key: e.target.value })}
            />
            <span className="hint">
              {isCaiis
                ? "Leave blank to use CDP_TOKEN or /tmp/jwt on the server."
                : "Leave blank to use OPENAI_API_KEY on the server."}
            </span>
          </label>
          <label className="field">
            <span>Base URL</span>
            <input className="input" value={settings.base_url} onChange={(e) => update({ base_url: e.target.value })} />
          </label>
          <label className="field">
            <span>Model</span>
            <input className="input" value={settings.model} onChange={(e) => update({ model: e.target.value })} />
            {isCaiis && (
              <span className="hint">
                Reasoning models (e.g. nemotron-3-nano) need max_tokens ≥ 1024 (server: {providerDefaults.max_tokens}).
              </span>
            )}
          </label>
          <label className="field">
            <span>Guardrails server URL</span>
            <input
              className="input"
              value={settings.server_url}
              onChange={(e) => update({ server_url: e.target.value })}
            />
          </label>
        </div>
      </details>
    </aside>
  );
}
