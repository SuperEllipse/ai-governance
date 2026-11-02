// Typed mirrors of the FastAPI responses in src/api/app.py.

export type Provider = "openai" | "caiis";
export type SafetyMode = "self_check" | "llama_guard" | "nim";
export type GuardrailsMode = "server" | "embedded" | "unguarded";
export type PolicyKey = "pii" | "jailbreak" | "topic" | "toxicity";

export interface Option<K extends string = string> {
  key: K;
  label: string;
}

export interface ProviderDefaults {
  base_url: string;
  model: string;
  max_tokens: number;
  has_api_key: boolean;
}

export interface UiConfig {
  default_provider: Provider;
  providers: Record<Provider, ProviderDefaults>;
  caiis_configured: boolean;
  default_safety_mode: SafetyMode;
  safety_options: Option<SafetyMode>[];
  has_nim_api_key: boolean;
  llama_guard: { base_url: string; model: string; configured: boolean };
  default_mode: GuardrailsMode;
  mode_options: Option<GuardrailsMode>[];
  default_server_url: string;
  policy_options: Option<PolicyKey>[];
}

export interface ExampleQuery {
  query: string;
  label: string;
  block_type: string;
  recommended_mode: GuardrailsMode;
  recommended_policies: PolicyKey[];
  expected_rail: string;
}

export interface ExamplesResponse {
  examples: ExampleQuery[];
  dataset_size: number;
}

export interface RunSettings {
  provider: Provider;
  api_key: string;
  base_url: string;
  model: string;
  safety_mode: SafetyMode;
  nim_api_key: string;
  llama_guard_base_url: string;
  llama_guard_model: string;
  mode: GuardrailsMode;
  server_url: string;
  policies: PolicyKey[];
}

export interface Violation {
  query: string;
  policy: string;
  rail: string;
  blocked: boolean;
  refusal_message: string;
  category: string;
  expected_policy: string;
  agent: string;
  unguarded_response: string;
  guarded_response: string;
  activated_rails: string[];
  policy_reason: string;
  violated_rule: string;
  timestamp: string;
  run_id: string;
}

export interface AgentTrace {
  routed_agent: string;
  tools_called: string[];
  raw_output: string;
}

export interface QueryResult {
  query: string;
  unguarded_response: string;
  guarded_response: string;
  violations: Violation[];
  agent_trace: AgentTrace;
  mode: string;
  policies: PolicyKey[];
  blocked: boolean;
  guardrails_log: Record<string, unknown>;
  output_vars: Record<string, unknown>;
  actual_violation: boolean;
  checks_passed: boolean;
  infra_error: string;
  elapsed_ms: number;
}

export interface StatusResponse {
  deps: { module: string; label: string; installed: boolean }[];
  llm: Record<Provider, boolean>;
  guardrails_server: {
    url: string;
    reachable: boolean;
    latency_ms: number | null;
    detail: string;
  } | null;
}

export interface BatchRun {
  run_id: string;
  total_queries: number;
  violation_count: number;
  started_at: string;
  completed_at: string;
  policies: string;
}

export interface BatchSummary {
  run_id: string;
  total_queries: number;
  violation_count: number;
  violation_rate: number;
  by_category: Record<string, number>;
  by_policy: Record<string, number>;
  expected_hits: number;
  expected_total: number;
  mode: GuardrailsMode;
}

export interface ViolationRow extends Violation {
  id: number;
}

export type BatchEvent =
  | { type: "progress"; current: number; total: number; message: string }
  | { type: "done"; summary: BatchSummary }
  | { type: "error"; message: string }
  | { type: "cancelled"; current: number; total: number; run_id: string };
