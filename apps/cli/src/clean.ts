// `appscreenmap clean`: what can go, decided by a pure planner (tested), then removed after the user confirms.
//   always offered: old viewer versions (never the active one), the download cache, old command logs (runs/.logs)
//   only with --runs: finished runs older than --older-than days (never a running one)
import { existsSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import type { Home } from "./home";
import type { RunSummary } from "./runs";

export interface Removable {
  kind: "viewer" | "cache" | "log" | "run";
  path: string;
  label: string;
  bytes: number;
  runId?: string;
}

export interface CleanInput {
  viewers: { version: string; path: string; bytes: number }[];
  currentViewer: string | null;
  cache: { path: string; name: string; bytes: number }[];
  logs: { path: string; name: string; bytes: number; mtimeMs: number }[];
  runs: (Pick<RunSummary, "id" | "status" | "startedAt"> & { path: string; bytes: number })[];
  includeRuns: boolean;
  olderThanDays: number;
  now: number;
}

export function planClean(i: CleanInput): Removable[] {
  const cutoff = i.now - i.olderThanDays * 24 * 60 * 60 * 1000;
  const out: Removable[] = [];
  for (const v of i.viewers) {
    if (v.version !== i.currentViewer) out.push({ kind: "viewer", path: v.path, label: `viewer ${v.version}`, bytes: v.bytes });
  }
  for (const c of i.cache) {
    if (c.name !== "update-check.json") out.push({ kind: "cache", path: c.path, label: `cache/${c.name}`, bytes: c.bytes });
  }
  for (const l of i.logs) {
    if (l.mtimeMs < cutoff) out.push({ kind: "log", path: l.path, label: `log ${l.name}`, bytes: l.bytes });
  }
  if (i.includeRuns) {
    for (const r of i.runs) {
      const started = r.startedAt ? Date.parse(r.startedAt) : Number.NaN;
      if (r.status !== "running" && !Number.isNaN(started) && started < cutoff) {
        out.push({ kind: "run", path: r.path, label: `run ${r.id} (${r.status})`, bytes: r.bytes, runId: r.id });
      }
    }
  }
  return out;
}

export function sizeOf(path: string): number {
  try {
    const st = statSync(path);
    if (!st.isDirectory()) return st.size;
    return readdirSync(path).reduce((n, name) => n + sizeOf(join(path, name)), 0);
  } catch {
    return 0;
  }
}

export function human(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(0)} KB`;
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
}

const entries = (dir: string) => (existsSync(dir) ? readdirSync(dir).filter((n) => !n.startsWith(".")) : []);

/** Gather what's on disk for the planner. */
export function cleanInput(home: Home, runsRoot: string, runs: RunSummary[], includeRuns: boolean, olderThanDays: number): CleanInput {
  const logsDir = join(runsRoot, ".logs");
  return {
    viewers: home.viewers().map((version) => {
      const path = join(home.viewersDir, version);
      return { version, path, bytes: sizeOf(path) };
    }),
    currentViewer: home.currentViewer(),
    cache: entries(home.cacheDir).map((name) => ({ name, path: join(home.cacheDir, name), bytes: sizeOf(join(home.cacheDir, name)) })),
    logs: entries(logsDir).map((name) => {
      const path = join(logsDir, name);
      return { name, path, bytes: sizeOf(path), mtimeMs: statSync(path).mtimeMs };
    }),
    runs: includeRuns
      ? runs.map((r) => ({ id: r.id, status: r.status, startedAt: r.startedAt, path: join(runsRoot, r.path), bytes: sizeOf(join(runsRoot, r.path)) }))
      : [],
    includeRuns,
    olderThanDays,
    now: Date.now(),
  };
}

/** Remove the planned items; deleted runs also leave runs/index.json (the engine rebuilds it on its next crawl or serve). */
export function applyClean(items: Removable[], runsRoot: string): void {
  for (const item of items) rmSync(item.path, { recursive: true, force: true });
  const gone = new Set(items.filter((i) => i.kind === "run").map((i) => i.runId));
  const index = join(runsRoot, "index.json");
  if (!gone.size || !existsSync(index)) return;
  const data = JSON.parse(readFileSync(index, "utf8")) as { runs?: { id: string }[] };
  data.runs = (data.runs ?? []).filter((r) => !gone.has(r.id));
  writeFileSync(index, JSON.stringify(data, null, 1) + "\n");
}
