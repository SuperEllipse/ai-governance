import { useSettings } from "../state/SettingsContext";
import { useStatus } from "../state/StatusContext";

type Tone = "good" | "warning" | "critical" | "muted";

const ICONS: Record<Tone, string> = { good: "✓", warning: "!", critical: "✕", muted: "–" };

function Badge({ tone, label, detail }: { tone: Tone; label: string; detail: string }) {
  return (
    <span className={`status-badge status-${tone}`} title={detail} aria-label={`${label}. ${detail}`}>
      <span className="status-icon" aria-hidden="true">
        {ICONS[tone]}
      </span>
      {label}
    </span>
  );
}

/** Header badges: server dependencies, LLM key, guardrails server reachability. */
export function StatusBar() {
  const { settings } = useSettings();
  const { status, checking, refresh } = useStatus();

  if (!status) {
    return (
      <div className="status-bar">
        <Badge tone="muted" label={checking ? "Checking status…" : "Status unavailable"} detail="Could not load /api/status." />
      </div>
    );
  }

  const missing = status.deps.filter((d) => !d.installed);
  const providerName = settings.provider === "caiis" ? "Cloudera AI" : "OpenAI";
  const hasKey = status.llm[settings.provider] || Boolean(settings.api_key);
  const server = status.guardrails_server;

  return (
    <div className="status-bar" aria-label="System status">
      {missing.length === 0 ? (
        <Badge tone="good" label="Dependencies" detail="NeMo Guardrails, CrewAI and Presidio are installed." />
      ) : (
        <Badge
          tone="critical"
          label={`${missing.length} missing`}
          detail={`Not installed: ${missing.map((d) => d.label).join(", ")}. Run: pip install -r requirements.txt`}
        />
      )}
      {hasKey ? (
        <Badge
          tone="good"
          label={`${providerName} key`}
          detail={settings.api_key ? "Using the key entered in Settings." : "Using the key configured on the server."}
        />
      ) : (
        <Badge
          tone="warning"
          label={`No ${providerName} key`}
          detail={
            settings.provider === "caiis"
              ? "Set CDP_TOKEN in .env (or /tmp/jwt in CDSW), or enter a token under Settings → Connection."
              : "Set OPENAI_API_KEY in .env, or enter a key under Settings → Connection."
          }
        />
      )}
      {settings.mode !== "server" ? (
        <Badge tone="muted" label="Server not used" detail="The guardrails server is only used in Centralized Server mode." />
      ) : !server ? (
        <Badge tone="muted" label="Checking server…" detail={`Checking ${settings.server_url}…`} />
      ) : server.reachable ? (
        <Badge tone="good" label={`Server · ${server.latency_ms} ms`} detail={`Guardrails server reachable at ${server.url}.`} />
      ) : (
        <Badge
          tone="critical"
          label="Server down"
          detail={`Guardrails server not reachable at ${server.url}. Start it with: bash scripts/start_guardrails_server.sh${server.detail ? ` (${server.detail})` : ""}`}
        />
      )}
      <button className="icon-btn icon-btn-sm" onClick={refresh} disabled={checking} title="Re-check status" aria-label="Re-check status">
        <svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true" className={checking ? "spin" : undefined}>
          <path
            d="M20 12a8 8 0 1 1-2.34-5.66M20 4v4h-4"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </button>
    </div>
  );
}
