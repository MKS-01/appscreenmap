import { useEffect, useMemo, useState } from "react";
import { runFile } from "../api";
import type { AppMapData } from "../types";
import { a11yReport, coverageReport, notRun, perfReport, stabilityReport, type A11yFile, type BuildContext, type PerfFile } from "./builtin";
import { adaptiveReport, platformReport, securityReport, storeReport } from "./samples";
import securityRules from "../../../apps/engine/src/appscreenmap/security_rules.json";
import { SOURCES } from "./sources";
import type { AuditDef, AuditReport, PlannedCheck, Platform, Severity } from "./types";

// The audits Insights knows about, in display order. Adding one = a def here plus a builder (or nothing at all,
// if the crawler writes audits/<id>.json: unknown ids listed in audits/index.json show up automatically).

/** Security rules from the shared catalogue (apps/engine/src/appscreenmap/security_rules.json, documented in the security-rules skill).
 *  Each is a placeholder until a scanner implements it. */
const SECURITY_CHECKS: PlannedCheck[] = securityRules.rules
  .filter((r) => r.status === "planned")
  .map((r) => ({
    id: r.id,
    title: r.title,
    detail: r.why,
    fix: r.fix,
    severity: r.severity as Severity,
    category: (securityRules.categories as Record<string, string>)[r.category],
    platform: r.platform as Platform,
    needs: r.needs.join(", "),
    refs: r.refs,
  }));

interface Entry extends AuditDef {
  build: (ctx: BuildContext) => AuditReport;
}

export const AUDITS: Entry[] = [
  {
    id: "coverage",
    title: "Crawl coverage",
    icon: "map",
    group: "crawl",
    blurb: "How much of the app the crawl reached: screens, actions, activities.",
    produces: "Every crawl (map.json).",
    build: coverageReport,
  },
  {
    id: "stability",
    title: "Stability",
    icon: "crash",
    group: "crawl",
    blurb: "Crashes and failed navigations seen while crawling.",
    produces: "Every crawl (map.json events).",
    build: stabilityReport,
  },
  {
    id: "a11y",
    title: "Accessibility",
    icon: "a11y",
    group: "crawl",
    qualifier: "WCAG 2.2",
    blurb: "WCAG 2.2 checks across every mapped screen.",
    produces: "`appscreenmap a11y <run>` (a11y.json), also written at the end of every crawl.",
    build: a11yReport,
  },
  {
    id: "perf",
    title: "Performance",
    icon: "gauge",
    group: "crawl",
    blurb: "Cold start, load time per screen and jank against a budget.",
    produces: "Crawls with load measurement (perf.json).",
    build: perfReport,
  },
  {
    id: "adaptive",
    title: "Adaptive UI",
    icon: "adaptive",
    group: "release",
    blurb: "Orientation, window size classes, large screens and foldables.",
    produces: "Manifest orientation locks today; multi-size crawls (600 / 840 dp) are planned.",
    setup: "planned",
    planned: [
      { title: "Layouts at 600 dp and 840 dp", detail: "Crawl again at the medium and expanded window size classes and compare each screen with the compact one: stretched lists, a bottom bar where a navigation rail belongs, clipped content.", needs: "a tablet or resizable emulator", refs: [SOURCES.windowSizeClasses] },
      { title: "Orientation and resizability locks", detail: "Activities locked to one orientation are ignored on large screens at API 37, and fail WCAG 1.3.4. Read from the manifest today.", refs: [SOURCES.android17LargeScreens] },
      { title: "Foldable postures", detail: "Check the app across folded, half-open and flat postures, and that content avoids the hinge.", needs: "a foldable emulator (iOS: idb hinge)" },
      { title: "iPhone Duo poses", detail: "Every pose and orientation in Device Hub after recompiling with Xcode 27.1.", platform: "ios", needs: "an iOS crawl", refs: [SOURCES.appleIphoneDuoPrepare] },
    ],
    enable: ["Crawl on a tablet or resizable emulator, then run the audit on both runs (planned: appscreenmap adaptive <compact-run> <expanded-run>)"],
    build: adaptiveReport,
  },
  {
    id: "platform",
    title: "Platform changes",
    icon: "layers",
    group: "release",
    qualifier: "Android 17 · iOS 27",
    blurb: "This year's Android and iOS behavior changes, checked against the app.",
    produces: "Planned: manifest + jadx signals matched to the yearly behavior-change list.",
    setup: "planned",
    planned: [
      { title: "Orientation and resizability at API 37", detail: "The Android 16 opt-out for ignoring orientation and aspect-ratio limits on large screens is removed for apps targeting 37.", platform: "android", needs: "the manifest and target SDK", refs: [SOURCES.android17] },
      { title: "Local network permission", detail: "Apps targeting 37 need ACCESS_LOCAL_NETWORK for LAN access. Flags code that opens local sockets or discovers devices.", platform: "android", needs: "jadx (static scan)", refs: [SOURCES.localNetwork] },
      { title: "Static final fields and reflection", detail: "Reflective writes to static final fields throw at API 37, and JNI writes crash. Flags reflection on final fields.", platform: "android", needs: "jadx (static scan)", refs: [SOURCES.android17] },
      { title: "Cleartext traffic deprecation", detail: "usesCleartextTraffic is on a deprecation path; the replacement is a network security config.", platform: "android", needs: "the manifest", refs: [SOURCES.android17All] },
      { title: "New devices and SDK deadlines", detail: "iPhone Duo (available Oct 23, 2026) and the Xcode and SDK versions App Store Connect accepts.", platform: "ios", needs: "the .app's Info.plist", refs: [SOURCES.appleUpcoming] },
    ],
    enable: ["Matched against the yearly behavior-change lists in web/src/insights/sources.ts; needs the manifest and a jadx scan of the build (planned: appscreenmap platform <run>)"],
    build: () => platformReport(),
  },
  {
    id: "store",
    title: "Store readiness",
    icon: "store",
    group: "release",
    qualifier: "Play · App Store",
    blurb: "Google Play and App Store requirements, with deadlines.",
    produces: "Planned: target/min SDK from the APK, store listing assets from the crawl.",
    setup: "planned",
    planned: [
      { title: "Target and minimum SDK", detail: "Compares the build's targetSdk with Google Play's requirement for new apps and updates, and the deadline for each.", platform: "android", needs: "aapt2 on the APK", refs: [SOURCES.playTargetSdk] },
      { title: "Data safety form", detail: "Lists the SDKs and permissions the build uses so the Data safety answers can be checked against them.", platform: "android", needs: "the manifest and a jadx scan", refs: [SOURCES.playDataSafety] },
      { title: "Built with a required SDK", detail: "App Store Connect only accepts builds made with the Xcode and SDK versions Apple lists.", platform: "ios", needs: "the .app's Info.plist", refs: [SOURCES.appleUpcoming] },
      { title: "Privacy manifest", detail: "Checks that the app ships a privacy manifest declaring the data and required-reason APIs it uses.", platform: "ios", needs: "the .app bundle", refs: [SOURCES.applePrivacyManifest] },
      { title: "Listing screenshots", detail: "Crawl screenshots checked against each store's size and aspect-ratio rules (Play phone is 2:1 at most).", refs: [SOURCES.appleScreenshotSpecs] },
    ],
    enable: ["Needs the build's APK or .app: crawl with --apk or --app (planned: appscreenmap store <run>)"],
    build: storeReport,
  },
  {
    id: "security",
    title: "Security",
    icon: "security",
    group: "release",
    qualifier: "jadx · frida",
    blurb: "Static (jadx), manifest and dynamic (frida) checks.",
    produces: "Planned: `appscreenmap security <run>` with jadx and frida.",
    setup: "planned",
    planned: SECURITY_CHECKS,
    enable: ["Install the tools: brew install jadx; uv tool install frida-tools", "Then, once it ships: appscreenmap security runs/<project>/<run-id>"],
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
        .map((a) => ({ id: a.id, title: a.title ?? a.id, icon: "file", group: "release", blurb: "", produces: `audits/${a.id}.json` }));
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
