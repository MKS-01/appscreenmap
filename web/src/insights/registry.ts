import { useEffect, useMemo, useState } from "react";
import { runFile } from "../api";
import type { AppMapData } from "../types";
import { a11yReport, coverageReport, notRun, perfReport, stabilityReport, type A11yFile, type BuildContext, type PerfFile } from "./builtin";
import { adaptiveReport, platformReport, securityReport, storeReport } from "./samples";
import type { AuditDef, AuditReport } from "./types";

// The audits Insights knows about, in display order. Adding one = a def here plus a builder (or nothing at all,
// if the crawler writes audits/<id>.json: unknown ids listed in audits/index.json show up automatically).

interface Entry extends AuditDef {
  build: (ctx: BuildContext) => AuditReport;
}

export const AUDITS: Entry[] = [
  {
    id: "coverage",
    title: "Crawl coverage",
    icon: "map",
    blurb: "How much of the app the crawl reached: screens, actions, activities.",
    produces: "Every crawl (map.json).",
    build: coverageReport,
  },
  {
    id: "stability",
    title: "Stability",
    icon: "alert",
    blurb: "Crashes and failed navigations seen while crawling.",
    produces: "Every crawl (map.json events).",
    build: stabilityReport,
  },
  {
    id: "a11y",
    title: "Accessibility",
    icon: "a11y",
    blurb: "WCAG 2.2 checks across every mapped screen.",
    produces: "`appscreenmap a11y <run>` (a11y.json), also written at the end of every crawl.",
    build: a11yReport,
  },
  {
    id: "perf",
    title: "Performance",
    icon: "rocket",
    blurb: "Cold start, load time per screen and jank against a budget.",
    produces: "Crawls with load measurement (perf.json).",
    build: perfReport,
  },
  {
    id: "adaptive",
    title: "Adaptive UI",
    icon: "smartphone",
    blurb: "Orientation, window size classes, large screens and foldables.",
    produces: "Manifest orientation locks today; multi-size crawls (600 / 840 dp) are planned.",
    build: adaptiveReport,
  },
  {
    id: "platform",
    title: "Platform changes",
    icon: "cpu",
    blurb: "This year's Android and iOS behavior changes, checked against the app.",
    produces: "Planned: manifest + jadx signals matched to the yearly behavior-change list.",
    build: () => platformReport(),
  },
  {
    id: "store",
    title: "Store readiness",
    icon: "check",
    blurb: "Google Play and App Store requirements, with deadlines.",
    produces: "Planned: target/min SDK from the APK, store listing assets from the crawl.",
    build: storeReport,
  },
  {
    id: "security",
    title: "Security",
    icon: "shield",
    blurb: "Static (jadx), manifest and dynamic (frida) checks.",
    produces: "Planned: `appscreenmap security <run>` with jadx and frida.",
    build: securityReport,
  },
];

async function getJson<T>(url: string): Promise<T | null> {
  try {
    const r = await fetch(url, { cache: "no-store" });
    if (!r.ok) return null;
    return (await r.json()) as T;
  } catch {
    return null; // missing file, or not JSON (e.g. an SPA fallback page)
  }
}

const isReport = (x: unknown): x is AuditReport =>
  !!x && typeof x === "object" && (x as AuditReport).schema === 1 && typeof (x as AuditReport).audit === "string" && Array.isArray((x as AuditReport).findings);

/** Fill optional fields so a hand-written or third-party audit file can't crash the view. */
function normalize(r: AuditReport): AuditReport {
  return {
    ...r,
    source: r.source ?? "run",
    status: r.status ?? "info",
    score: typeof r.score === "number" ? Math.max(0, Math.min(100, r.score)) : null,
    summary: r.summary ?? "",
    metrics: r.metrics ?? [],
    charts: r.charts ?? [],
    refs: r.refs ?? [],
  };
}

/** A mixed report with its placeholder parts removed. */
const withoutSamples = (r: AuditReport): AuditReport => ({
  ...r,
  source: "run",
  metrics: r.metrics.filter((m) => !m.sample),
  charts: r.charts.filter((c) => !c.sample),
  findings: r.findings.filter((f) => !f.sample),
});

interface Files {
  a11y: A11yFile | null;
  perf: PerfFile | null;
  written: Record<string, AuditReport>; // audits/<id>.json files in the run folder
  extra: AuditDef[]; // ids from audits/index.json that the viewer has no def for
}

export interface LoadedAudits {
  defs: AuditDef[];
  reports: Record<string, AuditReport>;
  loading: boolean;
}

export function useAudits(run: string, map: AppMapData, showSamples: boolean): LoadedAudits {
  const [files, setFiles] = useState<Files | null>(null);

  useEffect(() => {
    let alive = true;
    setFiles(null);
    (async () => {
      const index = await getJson<{ audits?: { id: string; title?: string }[] }>(runFile(run, "audits/index.json"));
      const known = new Set(AUDITS.map((a) => a.id));
      const extra: AuditDef[] = (index?.audits ?? [])
        .filter((a) => a?.id && !known.has(a.id))
        .map((a) => ({ id: a.id, title: a.title ?? a.id, icon: "file", blurb: "", produces: `audits/${a.id}.json` }));
      const ids = [...AUDITS.map((a) => a.id), ...extra.map((a) => a.id)];
      const [a11y, perf, ...written] = await Promise.all([
        getJson<A11yFile>(runFile(run, "a11y.json")),
        getJson<PerfFile>(runFile(run, "perf.json")),
        ...ids.map((id) => getJson<unknown>(runFile(run, `audits/${id}.json`))),
      ]);
      if (!alive) return;
      const byId: Record<string, AuditReport> = {};
      written.forEach((w, k) => {
        if (isReport(w)) byId[ids[k]] = normalize(w);
      });
      setFiles({ a11y: a11y as A11yFile | null, perf: perf as PerfFile | null, written: byId, extra });
    })();
    return () => {
      alive = false;
    };
  }, [run]);

  const reports = useMemo(() => {
    const out: Record<string, AuditReport> = {};
    if (!files) return out;
    const ctx: BuildContext = { run, map, a11y: files.a11y, perf: files.perf };
    for (const a of AUDITS) {
      let r = files.written[a.id];
      if (!r) {
        try {
          r = a.build(ctx);
        } catch {
          r = notRun(a.id, a.title, "Couldn't build this audit from the run's files.");
        }
      }
      if (r.source === "sample" && !showSamples) r = notRun(a.id, a.title, a.produces);
      else if (r.source === "mixed" && !showSamples) r = withoutSamples(r);
      out[a.id] = r;
    }
    for (const a of files.extra) out[a.id] = files.written[a.id] ?? notRun(a.id, a.title, a.produces);
    return out;
  }, [files, run, map, showSamples]);

  const defs = useMemo(() => [...AUDITS, ...(files?.extra ?? [])], [files]);
  return { defs, reports, loading: !files };
}
