import { createHash, randomUUID } from "node:crypto";
import { readFile } from "node:fs/promises";

export function nowIso(): string {
  return new Date().toISOString();
}

export function stableJson(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(stableJson).join(",")}]`;
  if (value && typeof value === "object") {
    const object = value as Record<string, unknown>;
    return `{${Object.keys(object).sort().map((key) => `${JSON.stringify(key)}:${stableJson(object[key])}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

export function sha256Text(value: unknown): string {
  return createHash("sha256").update(typeof value === "string" ? value : stableJson(value)).digest("hex");
}

export async function sha256File(path: string): Promise<string> {
  return createHash("sha256").update(await readFile(path)).digest("hex");
}

export function makeId(prefix: string): string {
  return `${prefix}_${randomUUID().replaceAll("-", "").slice(0, 12)}`;
}

export function estimateTokens(value: unknown): number {
  return Math.ceil((typeof value === "string" ? value : stableJson(value)).length / 4);
}

export function trimToTokens(text: string, maxTokens: number): string {
  const maxChars = Math.max(0, Math.floor(maxTokens * 4));
  if (text.length <= maxChars) return text;
  if (!maxChars) return "";
  // The previous 80-character allowance erased the entire content of 12–20
  // token fields, and the marker itself could exceed the requested budget.
  // A short marker preserves the locator/meaning and makes omission explicit.
  const marker = maxChars >= 24 ? " …[truncated]" : "…";
  return `${text.slice(0, maxChars - marker.length)}${marker}`;
}
