// "Is the latest run ready to ship?": the home panel's summary of a run, from the files the engine writes in it
// (map.json stats, a11y.json, perf.json, audits/security.json), and the one next step worth taking.
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { PLAYGROUND_CRAWL, type Suggestion } from "./content";
import type { RunSummary } from "./runs";

export type Verdict = "ok" | "warn" | "failing" | "not run";

export interface Readiness {
  explored: { done: number; total: number } | null; // elements tried vs found
  screens: number;
  transitions: number;
  crashes: number;
  a11y: { open: number; levelA: number; levelAA: number } | null;
  perf: { slow: number; needsWork: number; coldMs: number | null; timed: boolean } | null;
  security: { score: number; status: string; errors: number; warnings: number } | null;
}

type Json = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

export function fromMap(m: Json): Pick<Readiness, "explored" | "screens" | "transitions" | "crashes"> {
  const s = (m.stats ?? {}) as Json;
  const el = (s.elements ?? {}) as Record<string, number>;
  const total = Object.values(el).reduce((a, b) => a + b, 0);
  return {
    explored: total ? { done: el.done ?? 0, total } : null,
    screens: s.screens ?? 0,
    transitions: s.transitions ?? 0,
    crashes: s.crashes ?? 0,
  };
}

export function fromA11y(a: Json): Readiness["a11y"] {
  const s = (a.summary ?? {}) as Json;
  return { open: s.open ?? s.issues ?? 0, levelA: s.by_level?.A ?? 0, levelAA: s.by_level?.AA ?? 0 };
}

export function fromPerf(p: Json): Readiness["perf"] {
  const screens = (p.screens ?? []) as { rating?: string }[];
  const coldMs = (p.startup?.median_ms as number | null | undefined) ?? null;
  return {
    slow: screens.filter((s) => s.rating === "slow").length,
    needsWork: screens.filter((s) => s.rating === "needs work").length,
    coldMs,
    timed: screens.length > 0 || coldMs !== null,
  };
}

export function fromSecurity(s: Json): Readiness["security"] {
  const findings = (s.findings ?? []) as { severity?: string }[];
  return {
    score: s.score ?? 0,
    status: s.status ?? "info",
    errors: findings.filter((f) => f.severity === "error").length,
    warnings: findings.filter((f) => f.severity === "warning").length,
  };
}

const readJson = (file: string): Json | null => {
  try {
    return existsSync(file) ? (JSON.parse(readFileSync(file, "utf8")) as Json) : null;
  } catch {
    return null;
  }
};

export function readReadiness(runsRoot: string, run: Pick<RunSummary, "path">): Readiness | null {
  const dir = join(runsRoot, run.path);
  const map = readJson(join(dir, "map.json"));
  if (!map) return null;
  const a11y = readJson(join(dir, "a11y.json"));
  const perf = readJson(join(dir, "perf.json"));
  const security = readJson(join(dir, "audits", "security.json"));
  return {
    ...fromMap(map),
    a11y: a11y ? fromA11y(a11y) : null,
    perf: perf ? fromPerf(perf) : null,
    security: security ? fromSecurity(security) : null,
  };
}

// ── verdicts ─────────────────────────────────────────────────────────────────

export const crashVerdict = (r: Readiness): Verdict => (r.crashes ? "failing" : "ok");

export function a11yVerdict(r: Readiness): Verdict {
  if (!r.a11y) return "not run";
  if (!r.a11y.open) return "ok";
  return r.a11y.levelA ? "failing" : "warn";
}

export function perfVerdict(r: Readiness): Verdict | null {
  if (!r.perf) return "not run";
  if (!r.perf.timed) return null; // crawled without load timings: nothing to judge
  return r.perf.slow || r.perf.needsWork ? "warn" : "ok";
}

export function securityVerdict(r: Readiness): Verdict {
  if (!r.security) return "not run";
  return r.security.status === "fail" ? "failing" : r.security.status === "warn" ? "warn" : "ok";
}

// ── the next step ────────────────────────────────────────────────────────────

export interface NextContext {
  dashboardOk: boolean;
  devices: number; // ready Android devices + booted simulators
  crawling: boolean;
  latest: (Pick<RunSummary, "status" | "platform"> & { dir: string }) | null;
  readiness: Readiness | null;
  inCheckout: boolean;
}

/** The single most useful thing to do now, as a command to copy (or run with x when it's an engine command). */
export function nextStep(c: NextContext): Suggestion {
  if (!c.dashboardOk) return { cmd: "appscreenmap setup", what: "install or repair the dashboard" };
  if (c.crawling) return { cmd: "2 crawl", what: "a crawl is running: follow it live on the crawl tab" };
  if (!c.devices) return { cmd: "emulator -list-avds", what: "start an Android emulator (or boot an iOS simulator) to crawl on" };
  if (!c.latest) {
    return c.inCheckout
      ? { ...PLAYGROUND_CRAWL, what: "map the Playground sample (x starts it)" }
      : { cmd: "appscreenmap crawl --apk path/to/app.apk --clear-data", what: "map your first app" };
  }
  const run = c.latest.dir;
  if (c.latest.status === "failed" || c.latest.status === "stopped") {
    return { cmd: `appscreenmap report ${run}`, what: `the last run ${c.latest.status}: see why`, engine: ["report", run] };
  }
  const r = c.readiness;
  if (!r) return { cmd: `appscreenmap report ${run}`, what: "crawl health of the last run", engine: ["report", run] };
  if (r.crashes) return { cmd: `appscreenmap report ${run}`, what: `${r.crashes} crash(es) during the crawl: the report links the logs`, engine: ["report", run] };
  if (!r.a11y) return { cmd: `appscreenmap a11y ${run} --report`, what: "run the WCAG 2.2 checks", engine: ["a11y", run, "--report"] };
  if (r.a11y.open) return { cmd: "/a11y-audit", what: `triage ${r.a11y.open} open WCAG finding(s) with an agent` };
  if (!r.security && c.latest.platform === "android") {
    return { cmd: `appscreenmap security ${run} --pull`, what: "security audit of the installed build", engine: ["security", run, "--pull"] };
  }
  if (r.perf && (r.perf.slow || r.perf.needsWork)) {
    return { cmd: `appscreenmap perf ${run}`, what: `${r.perf.slow + r.perf.needsWork} screen(s) over the load-time budget`, engine: ["perf", run] };
  }
  return { cmd: `appscreenmap verify ${run} --apk path/to/next.apk`, what: "looks ready: replay every path on the next build" };
}
