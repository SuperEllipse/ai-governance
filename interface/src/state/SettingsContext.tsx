import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import type { ExampleQuery, Provider, RunSettings, UiConfig } from "../api/types";

const STORAGE_KEY = "guardrails-demo-settings";
// Secrets stay in memory only; everything else survives a page reload.
const SECRET_FIELDS = ["api_key", "nim_api_key"] as const;

interface SettingsContextValue {
  config: UiConfig;
  settings: RunSettings;
  update: (patch: Partial<RunSettings>) => void;
  setProvider: (provider: Provider) => void;
  resetToDefaults: () => void;
  suggestion: ExampleQuery | null;
  applyExample: (example: ExampleQuery) => void;
}

const SettingsContext = createContext<SettingsContextValue | null>(null);

function defaultsFrom(config: UiConfig): RunSettings {
  const provider = config.default_provider;
  return {
    provider,
    api_key: "",
    base_url: config.providers[provider].base_url,
    model: config.providers[provider].model,
    safety_mode: config.default_safety_mode,
    nim_api_key: "",
    llama_guard_base_url: config.llama_guard.base_url,
    llama_guard_model: config.llama_guard.model,
    mode: config.default_mode,
    server_url: config.default_server_url,
    policies: config.policy_options.map((p) => p.key),
  };
}

function loadStored(): Partial<RunSettings> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as Partial<RunSettings>) : {};
  } catch {
    return {};
  }
}

function persist(settings: RunSettings): void {
  const copy: Partial<RunSettings> = { ...settings };
  for (const field of SECRET_FIELDS) delete copy[field];
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(copy));
  } catch {
    // Storage unavailable (private mode, quota): settings simply won't persist.
  }
}

export function SettingsProvider({ config, children }: { config: UiConfig; children: ReactNode }) {
  const [settings, setSettings] = useState<RunSettings>(() => ({
    ...defaultsFrom(config),
    ...loadStored(),
    api_key: "",
    nim_api_key: "",
  }));
  const [suggestion, setSuggestion] = useState<ExampleQuery | null>(null);

  const update = useCallback((patch: Partial<RunSettings>) => {
    setSettings((prev) => {
      const next = { ...prev, ...patch };
      persist(next);
      return next;
    });
  }, []);

  const setProvider = useCallback(
    (provider: Provider) => {
      // Switching provider resets the endpoint fields to that provider's defaults.
      update({
        provider,
        api_key: "",
        base_url: config.providers[provider].base_url,
        model: config.providers[provider].model,
      });
    },
    [config, update],
  );

  const resetToDefaults = useCallback(() => {
    const next = defaultsFrom(config);
    persist(next);
    setSettings(next);
    setSuggestion(null);
  }, [config]);

  const applyExample = useCallback(
    (example: ExampleQuery) => {
      update({ mode: example.recommended_mode, policies: [...example.recommended_policies] });
      setSuggestion(example);
    },
    [update],
  );

  const value = useMemo(
    () => ({ config, settings, update, setProvider, resetToDefaults, suggestion, applyExample }),
    [config, settings, update, setProvider, resetToDefaults, suggestion, applyExample],
  );
  return <SettingsContext.Provider value={value}>{children}</SettingsContext.Provider>;
}

export function useSettings(): SettingsContextValue {
  const ctx = useContext(SettingsContext);
  if (!ctx) throw new Error("useSettings must be used inside <SettingsProvider>");
  return ctx;
}
