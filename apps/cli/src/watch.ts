// Live view of crawls from the files the engine already writes: runs/index.json (a run starts and ends), the run's
// map.json (rewritten after every step: budget, counts) and trace.jsonl (one line per step). Works for any crawl,
// including one an agent started in another terminal.
import { closeSync, existsSync, fstatSync, openSync, readFileSync, readSync } from "node:fs";
import { join } from "node:path";
import type { RunSummary } from "./runs";

export interface TraceStep {
  step: number;
  screen: string;
  label: string;
  to?: string;
  effect: string; // new_screen | known_screen | same_screen | left_app | crash | not_found | …
}

export interface Progress {
  runId: string;
  status: string;
  app: string;
  device?: string;
  steps: number;
  maxSteps?: number;
  elapsedS: number;
  maxMinutes?: number;
  screens: number;
  transitions: number;
  crashes: number;
  stopReason?: string;
  recent: (TraceStep & { screenTitle?: string; toTitle?: string })[];
}

export type RunEvent = { kind: "started" | "finished"; run: RunSummary };

/** The last `maxLines` lines of a file, reading at most `maxBytes` from its end. */
export function tail(file: string, maxLines = 6, maxBytes = 16_384): string[] {
  if (!existsSync(file)) return [];
  const fd = openSync(file, "r");
  try {
    const size = fstatSync(fd).size;
    const len = Math.min(size, maxBytes);
    const buf = Buffer.alloc(len);
    readSync(fd, buf, 0, len, size - len);
    const lines = buf.toString("utf8").split("\n").filter(Boolean);
    if (len < size) lines.shift(); // the first line may be cut
    return lines.slice(-maxLines);
  } finally {
    closeSync(fd);
  }
}

export function parseTrace(lines: string[]): TraceStep[] {
  const out: TraceStep[] = [];
  for (const line of lines) {
    try {
      const r = JSON.parse(line) as Record<string, unknown>;
      if (typeof r.step !== "number") continue;
      out.push({
        step: r.step,
        screen: String(r.screen ?? ""),
        label: String(r.label ?? r.action ?? ""),
        ...(r.to ? { to: String(r.to) } : {}),
        effect: String(r.effect ?? ""),
      });
    } catch {
      // a line still being written
    }
  }
  return out;
}

interface MapJson {
  run?: {
    id?: string;
    status?: string;
    steps?: number;
    elapsed_s?: number;
    stop_reason?: string;
    app?: { label?: string; package?: string; version?: string };
    device?: { name?: string };
    config?: { max_steps?: number; max_minutes?: number };
  };
  stats?: { screens?: number; transitions?: number; crashes?: number };
  screens?: { id: string; title?: string }[];
}

export function parseProgress(mapJson: string, trace: TraceStep[]): Progress {
  const m = JSON.parse(mapJson) as MapJson;
  const run = m.run ?? {};
  const titles = new Map((m.screens ?? []).map((s) => [s.id, s.title]));
  const app = [run.app?.label || run.app?.package || "the app", run.app?.version].filter(Boolean).join(" ");
  return {
    runId: run.id ?? "",
    status: run.status ?? "unknown",
    app,
    ...(run.device?.name ? { device: run.device.name } : {}),
    steps: run.steps ?? trace.at(-1)?.step ?? 0,
    ...(run.config?.max_steps ? { maxSteps: run.config.max_steps } : {}),
    elapsedS: run.elapsed_s ?? 0,
    ...(run.config?.max_minutes ? { maxMinutes: run.config.max_minutes } : {}),
    screens: m.stats?.screens ?? titles.size,
    transitions: m.stats?.transitions ?? 0,
    crashes: m.stats?.crashes ?? 0,
    ...(run.stop_reason ? { stopReason: run.stop_reason } : {}),
    recent: trace
      .slice()
      .reverse()
      .map((t) => ({
        ...t,
        ...(titles.get(t.screen) ? { screenTitle: titles.get(t.screen) } : {}),
        ...(t.to && titles.get(t.to) ? { toTitle: titles.get(t.to) } : {}),
      })),
  };
}

/** Progress of one run from its folder, or null if it can't be read yet. */
export function readProgress(runsRoot: string, run: Pick<RunSummary, "path">, recent = 6): Progress | null {
  const dir = join(runsRoot, run.path);
  try {
    return parseProgress(readFileSync(join(dir, "map.json"), "utf8"), parseTrace(tail(join(dir, "trace.jsonl"), recent)));
  } catch {
    return null;
  }
}

/** What changed between two readings of the runs: a run appeared, or a running one ended. */
export function runEvents(prev: RunSummary[], next: RunSummary[]): RunEvent[] {
  const before = new Map(prev.map((r) => [r.id, r]));
  const out: RunEvent[] = [];
  for (const run of next) {
    const old = before.get(run.id);
    if (!old) out.push({ kind: run.status === "running" ? "started" : "finished", run });
    else if (old.status === "running" && run.status !== "running") out.push({ kind: "finished", run });
  }
  return out;
}

/** 0–1: how much of the step or time budget is used, whichever is further along. */
export function budgetUsed(p: Progress): number {
  const bySteps = p.maxSteps ? p.steps / p.maxSteps : 0;
  const byTime = p.maxMinutes ? p.elapsedS / (p.maxMinutes * 60) : 0;
  return Math.min(1, Math.max(bySteps, byTime));
}

/** "3m 10s", "45s", "1h 02m". */
export function duration(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, "0")}s`;
  return `${Math.floor(s / 3600)}h ${String(Math.floor((s % 3600) / 60)).padStart(2, "0")}m`;
}
