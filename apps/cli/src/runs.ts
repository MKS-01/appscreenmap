// The runs the engine has recorded, from runs/index.json (written by the engine; schema in docs/MAP_SCHEMA.md).
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

export interface RunSummary {
  id: string;
  path: string; // <project>/<run-id>, relative to runs/
  project: string;
  status: string; // running | done | stopped | failed
  app: string;
  version?: string;
  platform: "android" | "ios";
  screens: number;
  transitions: number;
  startedAt?: string;
}

interface IndexEntry {
  id: string;
  path?: string;
  project?: string;
  status?: string;
  started_at?: string;
  screens?: number;
  transitions?: number;
  app?: { label?: string; package?: string; version?: string; platform?: string };
  device?: { platform?: string };
}

/** Runs from an index.json body, newest first. */
export function parseIndex(json: string): RunSummary[] {
  const data = JSON.parse(json) as { runs?: IndexEntry[] };
  return (data.runs ?? [])
    .map((r) => ({
      id: r.id,
      path: r.path ?? r.id,
      project: r.project ?? "",
      status: r.status ?? "unknown",
      app: r.app?.label || r.app?.package || r.project || r.id,
      ...(r.app?.version ? { version: r.app.version } : {}),
      platform: (r.app?.platform ?? r.device?.platform) === "ios" ? ("ios" as const) : ("android" as const),
      screens: r.screens ?? 0,
      transitions: r.transitions ?? 0,
      ...(r.started_at ? { startedAt: r.started_at } : {}),
    }))
    .sort((a, b) => (b.startedAt ?? "").localeCompare(a.startedAt ?? ""));
}

export function readRuns(runsRoot: string): RunSummary[] {
  const file = join(runsRoot, "index.json");
  if (!existsSync(file)) return [];
  try {
    return parseIndex(readFileSync(file, "utf8"));
  } catch {
    return [];
  }
}

/** The dashboard page for a run (the viewer's `#/r/<run>/map` route). */
export function runUrl(dashboardUrl: string, run: Pick<RunSummary, "path">): string {
  return `${dashboardUrl}#/r/${encodeURIComponent(run.path)}/map`;
}

/** "3m ago", "2h ago", "4d ago". */
export function ago(iso: string | undefined, now = Date.now()): string {
  if (!iso) return "";
  const s = Math.max(0, (now - Date.parse(iso)) / 1000);
  if (Number.isNaN(s)) return "";
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}
