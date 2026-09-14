import { readdir, readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

const args = parseArgs(process.argv.slice(2));
if (!args.judgeDir) throw new Error("Usage: validate-isolated-judge-outputs.ts --judge-dir <dir>");
const judgeDir = resolve(args.judgeDir);
const bundleDir = resolve(judgeDir, "bundles");
const rawDir = resolve(judgeDir, "raw_outputs");
const bundleIds = new Set((await readdir(bundleDir)).filter((name) => name.endsWith(".json")).map((name) => name.replace(/\.json$/, "")));
let rawFiles: string[] = [];
try { rawFiles = (await readdir(rawDir)).filter((name) => name.endsWith(".json")); } catch { rawFiles = []; }

const errors: string[] = [];
const seen = new Set<string>();
for (const file of rawFiles) {
  let value: any;
  try { value = JSON.parse(await readFile(resolve(rawDir, file), "utf8")); }
  catch (error) { errors.push(`${file}: invalid JSON (${error instanceof Error ? error.message : String(error)})`); continue; }
  const sampleId = String(value.sample_id ?? "");
  if (!bundleIds.has(sampleId)) errors.push(`${file}: sample_id ${sampleId || "<missing>"} has no matching bundle`);
  if (seen.has(sampleId)) errors.push(`${file}: duplicate sample_id ${sampleId}`);
  seen.add(sampleId);
  const dimensions = Array.isArray(value.dimensions) ? value.dimensions : [];
  const byId = new Map(dimensions.map((item: any) => [String(item?.id), item]));
  for (const id of ["J1", "J2", "J3", "J4", "J5"]) {
    const item: any = byId.get(id);
    if (!item) { errors.push(`${file}: missing ${id}`); continue; }
    if (![0, 1, 2].includes(Number(item.score))) errors.push(`${file}: ${id}.score must be 0, 1, or 2`);
    if (!Array.isArray(item.evidence_ids) || !item.evidence_ids.length) errors.push(`${file}: ${id}.evidence_ids must be non-empty`);
    if (!String(item.reason ?? "").trim()) errors.push(`${file}: ${id}.reason is empty`);
    if (!Number.isFinite(Number(item.confidence)) || Number(item.confidence) < 0 || Number(item.confidence) > 1) errors.push(`${file}: ${id}.confidence must be in [0,1]`);
  }
  if (dimensions.length !== 5 || byId.size !== 5) errors.push(`${file}: dimensions must contain J1--J5 exactly once`);
  const computed = [...byId.values()].reduce((sum: number, item: any) => sum + Number(item?.score ?? 0), 0);
  if (Number(value.total) !== computed) errors.push(`${file}: total=${value.total} but dimension sum=${computed}`);
  if (!Array.isArray(value.severe_semantic_errors)) errors.push(`${file}: severe_semantic_errors must be an array`);
  if (typeof value.uncertainty !== "string") errors.push(`${file}: uncertainty must be a string`);
}
for (const sampleId of bundleIds) if (!seen.has(sampleId)) errors.push(`${sampleId}: missing raw judge output`);

const report = { judgeDir, bundles: bundleIds.size, rawOutputs: rawFiles.length, valid: errors.length === 0, errors };
await writeFile(resolve(judgeDir, "judge_validation_report.json"), JSON.stringify(report, null, 2), "utf8");
console.log(JSON.stringify(report, null, 2));
if (errors.length) process.exitCode = 1;

function parseArgs(values: string[]): { judgeDir?: string } {
  const out: Record<string, string> = {};
  for (let i = 0; i < values.length; i += 2) out[values[i].replace(/^--/, "")] = values[i + 1] ?? "";
  return { judgeDir: out["judge-dir"] };
}
