import { useEffect, useState } from "react";
import { api } from "./api/client";
import type { ExamplesResponse, UiConfig } from "./api/types";
import { Architecture } from "./components/Architecture";
import { BatchDashboard } from "./components/BatchDashboard";
import { ChatCompare } from "./components/ChatCompare";
import { SettingsPanel } from "./components/SettingsPanel";
import { StatusBar } from "./components/StatusBar";
import { ThemeToggle } from "./components/ThemeToggle";
import { SettingsProvider } from "./state/SettingsContext";
import { StatusProvider } from "./state/StatusContext";

const TABS = [
  { id: "chat", label: "Chat Compare" },
  { id: "batch", label: "Batch Dashboard" },
  { id: "architecture", label: "Architecture" },
] as const;

type TabId = (typeof TABS)[number]["id"];

function tabFromHash(): TabId {
  const id = window.location.hash.replace(/^#\/?/, "");
  return TABS.some((t) => t.id === id) ? (id as TabId) : "chat";
}

export default function App() {
  const [config, setConfig] = useState<UiConfig | null>(null);
  const [examples, setExamples] = useState<ExamplesResponse | null>(null);
  const [loadError, setLoadError] = useState("");
  const [tab, setTab] = useState<TabId>(tabFromHash);

  useEffect(() => {
    Promise.all([api.config(), api.examples()])
      .then(([cfg, ex]) => {
        setConfig(cfg);
        setExamples(ex);
      })
      .catch((err: Error) => setLoadError(err.message));
  }, []);

  useEffect(() => {
    const onHash = () => setTab(tabFromHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  if (loadError) {
    return (
      <div className="center-screen">
        <div className="banner banner-critical" role="alert">
          <span className="banner-icon" aria-hidden="true">!</span>
          <div>
            <strong>Could not reach the API</strong>
            <p className="small">{loadError}</p>
          </div>
        </div>
      </div>
    );
  }

  if (!config || !examples) {
    return (
      <div className="center-screen muted">
        <span className="spinner" aria-label="Loading" />
      </div>
    );
  }

  return (
    <SettingsProvider config={config}>
      <StatusProvider>
      <header className="app-header">
        <div className="brand">
          <div className="brand-mark" aria-hidden="true">FN</div>
          <div>
            <h1>NeMo Guardrails Banking Demo</h1>
            <p>CrewAI multi-agent banking assistant with modular safety policies</p>
          </div>
        </div>
        <nav className="tabs" role="tablist" aria-label="Views">
          {TABS.map((t) => (
            <button
              key={t.id}
              className="tab"
              role="tab"
              aria-selected={tab === t.id}
              onClick={() => {
                window.location.hash = `/${t.id}`;
              }}
            >
              {t.label}
            </button>
          ))}
        </nav>
        <div className="header-end">
          <StatusBar />
          <ThemeToggle />
        </div>
      </header>
      <div className="layout">
        <SettingsPanel />
        <main className="main">
          {/* Keep every view mounted so in-progress results survive tab switches. */}
          <div hidden={tab !== "chat"}>
            <ChatCompare examples={examples.examples} />
          </div>
          <div hidden={tab !== "batch"}>
            <BatchDashboard datasetSize={examples.dataset_size} />
          </div>
          <div hidden={tab !== "architecture"}>
            <Architecture />
          </div>
        </main>
      </div>
      </StatusProvider>
    </SettingsProvider>
  );
}
