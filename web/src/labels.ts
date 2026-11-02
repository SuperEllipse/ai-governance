import type { GuardrailsMode, Option, PolicyKey } from "./api/types";

export const MODE_LABELS: Record<GuardrailsMode, string> = {
  server: "Centralized Server",
  embedded: "Embedded",
  unguarded: "Unguarded Only",
};

export function formatPolicies(keys: PolicyKey[], options: Option<PolicyKey>[]): string {
  if (keys.length === 0) return "none (happy path)";
  const labels = new Map(options.map((o) => [o.key, o.label]));
  return keys.map((k) => labels.get(k) ?? k).join(", ");
}

export type BlockKind = "pass" | "input" | "output" | "other";

/** Classify an example's block type for its badge (happy path / input / output). */
export function blockKind(blockType: string): BlockKind {
  if (blockType === "Happy path") return "pass";
  if (blockType.startsWith("Input block")) return "input";
  if (blockType.startsWith("Output block")) return "output";
  return "other";
}

const ACRONYMS: Record<string, string> = { pii: "PII" };

/** "happy_path" → "Happy path", "pii" → "PII" */
export function humanize(key: string): string {
  if (ACRONYMS[key]) return ACRONYMS[key];
  const text = key.replace(/_/g, " ").trim();
  return text ? text[0].toUpperCase() + text.slice(1) : key;
}
