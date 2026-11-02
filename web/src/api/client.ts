import type {
  BatchEvent,
  BatchRun,
  StatusResponse,
  ExamplesResponse,
  QueryResult,
  RunSettings,
  UiConfig,
  ViolationRow,
} from "./types";

// Relative URLs (no leading slash) so the app works under any proxy path prefix.
const API = "api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`${API}/${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      const body = await resp.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
    } catch {
      // Non-JSON error body: keep the status text.
    }
    throw new Error(`${resp.status} ${detail}`);
  }
  return resp.json() as Promise<T>;
}

export const api = {
  config: () => request<UiConfig>("config"),
  examples: () => request<ExamplesResponse>("examples"),
  query: (query: string, settings: RunSettings) =>
    request<QueryResult>("query", {
      method: "POST",
      body: JSON.stringify({ query, settings }),
    }),
  startBatch: (sampleSize: number, settings: RunSettings) =>
    request<{ job_id: string; run_id: string }>("batch", {
      method: "POST",
      body: JSON.stringify({ sample_size: sampleSize, settings }),
    }),
  status: (serverUrl: string, checkServer: boolean) =>
    request<StatusResponse>(
      `status?server_url=${encodeURIComponent(serverUrl)}&check_server=${checkServer}`,
    ),
  cancelBatch: (jobId: string) =>
    request<{ cancelled: boolean }>(`batch/${encodeURIComponent(jobId)}`, { method: "DELETE" }),
  batchRuns: () => request<BatchRun[]>("batch-runs"),
  violations: (runId?: string) =>
    request<ViolationRow[]>(
      runId ? `violations?run_id=${encodeURIComponent(runId)}` : "violations",
    ),
};

/** Subscribe to batch progress; returns a function that closes the stream. */
export function watchBatch(jobId: string, onEvent: (event: BatchEvent) => void): () => void {
  const source = new EventSource(`${API}/batch/${encodeURIComponent(jobId)}/events`);
  const handle = (msg: MessageEvent<string>) => {
    const event = JSON.parse(msg.data) as BatchEvent;
    onEvent(event);
    if (event.type !== "progress") source.close();
  };
  for (const type of ["progress", "done", "error", "cancelled"]) {
    source.addEventListener(type, handle as EventListener);
  }
  source.onerror = () => {
    if (source.readyState === EventSource.CLOSED) return;
    source.close();
    onEvent({ type: "error", message: "Lost connection to the batch progress stream." });
  };
  return () => source.close();
}
