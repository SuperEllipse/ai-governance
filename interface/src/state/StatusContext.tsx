import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api } from "../api/client";
import type { StatusResponse } from "../api/types";
import { useSettings } from "./SettingsContext";

const POLL_MS = 30_000;

export interface StatusProblem {
  key: "deps" | "llm" | "server";
  message: string;
}

interface StatusContextValue {
  status: StatusResponse | null;
  checking: boolean;
  refresh: () => void;
  /** Known problems with the currently selected settings (empty when all good or unknown). */
  problems: StatusProblem[];
}

const StatusContext = createContext<StatusContextValue | null>(null);

export function StatusProvider({ children }: { children: ReactNode }) {
  const { settings } = useSettings();
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [checking, setChecking] = useState(false);
  const checkServer = settings.mode === "server";
  const serverUrl = settings.server_url;

  const requestSeq = useRef(0);

  const refresh = useCallback(() => {
    const seq = ++requestSeq.current;
    const current = () => seq === requestSeq.current;
    setChecking(true);
    // Fast pass (deps + keys) first; the server probe can take seconds when the port is closed.
    api
      .status(serverUrl, false)
      .then((fast) => {
        if (!current()) return;
        const url = serverUrl.trim().replace(/\/+$/, "");
        // Keep the previous probe result only if it was for the same server URL.
        setStatus((prev) => ({
          ...fast,
          guardrails_server:
            checkServer && prev?.guardrails_server?.url === url ? prev.guardrails_server : null,
        }));
      })
      .catch(() => {
        if (current()) setStatus(null);
      });
    if (!checkServer) {
      setChecking(false);
      return;
    }
    api
      .status(serverUrl, true)
      .then((full) => {
        if (current()) setStatus(full);
      })
      .catch(() => undefined)
      .finally(() => {
        if (current()) setChecking(false);
      });
  }, [serverUrl, checkServer]);

  // Re-check when the server URL or mode changes (debounced for typing), then every 30 s.
  useEffect(() => {
    const first = window.setTimeout(refresh, 400);
    const timer = window.setInterval(refresh, POLL_MS);
    return () => {
      window.clearTimeout(first);
      window.clearInterval(timer);
    };
  }, [refresh]);

  const problems = useMemo<StatusProblem[]>(() => {
    if (!status) return [];
    const list: StatusProblem[] = [];
    const missing = status.deps.filter((d) => !d.installed).map((d) => d.label);
    if (missing.length) {
      list.push({ key: "deps", message: `${missing.join(", ")} not installed on the server` });
    }
    if (!status.llm[settings.provider] && !settings.api_key) {
      const name = settings.provider === "caiis" ? "Cloudera AI (CDP token)" : "OpenAI";
      list.push({ key: "llm", message: `No ${name} key configured` });
    }
    if (checkServer && status.guardrails_server && !status.guardrails_server.reachable) {
      list.push({ key: "server", message: `Guardrails server not reachable at ${status.guardrails_server.url}` });
    }
    return list;
  }, [status, settings.provider, settings.api_key, checkServer]);

  const value = useMemo(() => ({ status, checking, refresh, problems }), [status, checking, refresh, problems]);
  return <StatusContext.Provider value={value}>{children}</StatusContext.Provider>;
}

export function useStatus(): StatusContextValue {
  const ctx = useContext(StatusContext);
  if (!ctx) throw new Error("useStatus must be used inside <StatusProvider>");
  return ctx;
}
