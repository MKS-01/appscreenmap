import type { AppMapData } from "../types";
import { plural, shortActivity } from "../util";
import { refs } from "./sources";
import type { AuditFinding, AuditReport, AuditStatus, Severity, Tone } from "./types";

// Audits derived in the browser from files every crawl already writes: map.json, a11y.json and perf.json.
// When the crawler starts writing audits/<id>.json itself, that file wins and these become the fallback.

export const statusFromScore = (score: number | null): AuditStatus =>
  score == null ? "info" : score >= 90 ? "pass" : score >= 70 ? "warn" : "fail";

const pct = (n: number, d: number) => (d > 0 ? Math.round((100 * n) / d) : 0);

export interface BuildContext {
  run: string;
  map: AppMapData;
  a11y: A11yFile | null;
  perf: PerfFile | null;
}

// ── coverage ────────────────────────────────────────────────────────────────

export function coverageReport({ map }: BuildContext): AuditReport {
  const st = map.stats;
  const app = map.screens.filter((s) => s.kind === "app");
  const el = st.elements;
  const tried = el.done ?? 0;
  const open = (el.pending ?? 0) + (el.failed ?? 0) + (el.unreachable ?? 0);
  const score = tried + open ? pct(tried, tried + open) : null;
  const budgetHit = (map.run.steps ?? 0) >= Number(map.run.config.max_steps ?? Infinity);

  const depth = new Map<number, number>();
  for (const s of app) depth.set(s.depth, (depth.get(s.depth) ?? 0) + 1);

  const findings: AuditFinding[] = [];
  const declared = map.run.app.activities ?? [];
  const visited = new Set(st.activities_visited);
  for (const a of declared.filter((a) => !visited.has(a)))
    findings.push({
      id: `activity-missed::${a}`,
      severity: "warning",
      category: "Activities",
      title: `${shortActivity(a)} was never reached`,
      detail: `${a} is declared in the manifest but no crawled screen ran in it.`,
      fix: "Raise --max-steps, add test credentials for gated areas, or check whether the activity is still used.",
    });
  for (const s of app) {
    const pending = s.elements.filter((e) => e.status === "pending").length;
    if (pending)
      findings.push({
        id: `untried::${s.id}`,
        severity: "warning",
        category: "Untried actions",
        screen: s.id,
        title: `${plural(pending, "action")} never tried on ${s.title}`,
        detail: budgetHit
          ? `The crawl stopped at its ${map.run.config.max_steps}-step budget.`
          : "The crawl ended before it could try them (time budget, or the screen became unreachable).",
        fix: budgetHit ? "Re-run with a higher --max-steps." : undefined,
      });
    for (const e of s.elements.filter((e) => e.status === "failed" || e.status === "unreachable"))
      findings.push({
        id: `nav::${s.id}::${e.id}`,
        severity: "warning",
        category: "Navigation",
        screen: s.id,
        title: `“${e.label}” ${e.status === "failed" ? "couldn't be found to tap" : "is on a screen the crawler couldn't return to"}`,
      });
    for (const e of s.elements.filter((e) => e.status === "blocked"))
      findings.push({
        id: `blocked::${s.id}::${e.id}`,
        severity: "info",
        category: "Blocked for safety",
        screen: s.id,
        title: `“${e.label}” was never tapped`,
        detail: "Its label matches blocked_text (logout, delete, pay, …).",
      });
  }

  return {
    schema: 1,
    audit: "coverage",
    title: "Crawl coverage",
    tool: map.run.tool,
    generated_at: map.run.finished_at ?? map.run.started_at,
    source: "run",
    status: statusFromScore(score),
    score,
    score_note: "Share of discovered actions the crawl actually tried (blocked and pattern-skipped ones excluded).",
    summary: `${plural(st.screens, "screen")} and ${plural(st.transitions, "transition")} mapped, ${tried} of ${tried + open} actions tried.`,
    metrics: [
      { label: "screens", value: st.screens },
      { label: "transitions", value: st.transitions },
      { label: "max depth", value: st.max_depth },
      {
        label: "activity coverage",
        value: st.activity_coverage != null ? `${Math.round(st.activity_coverage * 100)}%` : "—",
        tone: st.activity_coverage == null ? undefined : st.activity_coverage >= 0.9 ? "good" : "warn",
        hint: st.activity_coverage == null ? "Needs aapt2 to read declared activities from the APK" : undefined,
      },
      { label: "untried actions", value: el.pending ?? 0, tone: el.pending ? "warn" : "good" },
      { label: "steps", value: map.run.steps ?? "—" },
    ],
    charts: [
      {
        type: "columns",
        title: "Screens by depth",
        note: "Taps from launch",
        data: [...depth.entries()].sort((a, b) => a[0] - b[0]).map(([d, n]) => ({ label: String(d), value: n })),
      },
    ],
    findings,
    refs: [],
  };
}

// ── stability ───────────────────────────────────────────────────────────────

export function stabilityReport({ map }: BuildContext): AuditReport {
  const crashes = map.events.filter((e) => e.type === "crash");
  const navFailed = map.events.filter((e) => e.type === "nav_failed");
  const restarts = map.events.filter((e) => e.type === "restart");
  const score = Math.max(0, 100 - 30 * crashes.length - 2 * navFailed.length);
  const types = new Map<string, number>();
  for (const e of map.events) types.set(e.type, (types.get(e.type) ?? 0) + 1);
  const toneOf = (t: string): Tone | undefined => (t === "crash" ? "bad" : t === "nav_failed" ? "warn" : undefined);

  return {
    schema: 1,
    audit: "stability",
    title: "Stability",
    tool: map.run.tool,
    source: "run",
    status: crashes.length ? "fail" : statusFromScore(score),
    score,
    score_note: "100, minus 30 per crash and 2 per failed navigation during the crawl.",
    summary: crashes.length
      ? `${crashes.length} ${crashes.length === 1 ? "crash" : "crashes"} during the crawl.`
      : "No crashes during the crawl.",
    metrics: [
      { label: "crashes", value: crashes.length, tone: crashes.length ? "bad" : "good" },
      { label: "failed navigations", value: navFailed.length, tone: navFailed.length ? "warn" : "good" },
      { label: "app restarts", value: restarts.length },
      { label: "events", value: map.events.length },
    ],
    charts: types.size
      ? [{ type: "bars", title: "Run events by type", data: [...types].map(([t, n]) => ({ label: t.replace("_", " "), value: n, tone: toneOf(t) })) }]
      : [],
    findings: [
      ...crashes.map((e, i) => ({
        id: `crash::${e.step}::${i}`,
        severity: "error" as Severity,
        category: "Crashes",
        screen: e.screen ?? undefined,
        title: `Crash at step ${e.step}`,
        detail: e.log ? `${e.detail} · logcat: ${e.log}` : e.detail,
        fix: "Open the logcat file for the stack trace; replay the screen's reach path to reproduce.",
      })),
      ...navFailed.map((e, i) => ({
        id: `nav-failed::${e.step}::${i}`,
        severity: "warning" as Severity,
        category: "Navigation",
        screen: e.screen ?? undefined,
        title: `Couldn't navigate back to a screen at step ${e.step}`,
        detail: e.detail,
      })),
    ],
    refs: refs("androidVitals"),
  };
}

// ── accessibility (crawler's a11y.json) ─────────────────────────────────────

export interface A11yFile {
  standard: string;
  rules: Record<string, { sc: string; name: string; level: string; kind: string; severity: Severity; why: string; fix: string }>;
  summary: { issues: number; by_level: Record<string, number>; by_criterion: Record<string, number> };
  issues: { key: string; screen: string; rule: string; sc: string; level: string; severity: Severity; triage?: string }[];
}

export function a11yReport({ map, a11y }: BuildContext): AuditReport {
  if (!a11y) return notRun("a11y", "Accessibility (WCAG 2.2)", "Run `appscreenmap a11y <run>` to write a11y.json.");
  const app = map.screens.filter((s) => s.kind === "app");
  const issues = a11y.issues;
  // App-level issues (orientation lock, inconsistent navigation) aren't tied to one screen: 10 points each.
  const serious = issues.filter((i) => i.severity !== "info");
  const appWide = serious.filter((i) => i.screen === "app").length;
  const flagged = new Set(serious.map((i) => i.screen));
  const score = app.length ? Math.max(0, pct(app.filter((s) => !flagged.has(s.id)).length, app.length) - 10 * appWide) : null;
  const sev = (s: Severity) => issues.filter((i) => i.severity === s).length;

  const byRule = new Map<string, typeof issues>();
  for (const i of issues) byRule.set(i.rule, [...(byRule.get(i.rule) ?? []), i]);
  const findings: AuditFinding[] = [...byRule].map(([rule, list]) => {
    const r = a11y.rules[rule];
    const screens = new Set(list.map((i) => i.screen).filter((s) => s !== "app"));
    return {
      id: `a11y::${rule}`,
      severity: r?.severity ?? list[0].severity,
      category: r ? `${r.sc} · Level ${r.level}` : undefined,
      title: r ? `${r.name} (${plural(list.length, "issue")})` : rule,
      detail: `${screens.size ? `On ${plural(screens.size, "screen")}. ` : ""}${r?.why ?? ""}`,
      fix: r?.fix,
      screen: list.find((i) => i.screen !== "app")?.screen,
      refs: r ? [{ title: `WCAG 2.2 · ${r.sc} ${r.name}`, url: `https://www.w3.org/TR/WCAG22/#${slug(r.name)}`, publisher: "W3C" }] : undefined,
    };
  });

  return {
    schema: 1,
    audit: "a11y",
    title: "Accessibility (WCAG 2.2)",
    tool: map.run.tool,
    source: "run",
    status: statusFromScore(score),
    score,
    score_note: "Share of app screens with no error or warning, minus 10 per app-wide error or warning (e.g. a locked orientation).",
    summary: `${plural(issues.length, "issue")} across ${Object.keys(a11y.summary.by_criterion).length} success criteria.`,
    metrics: [
      { label: "errors", value: sev("error"), tone: sev("error") ? "bad" : "good" },
      { label: "warnings", value: sev("warning"), tone: sev("warning") ? "warn" : "good" },
      { label: "suggestions", value: sev("info") },
      { label: "level A", value: a11y.summary.by_level.A ?? 0 },
      { label: "level AA", value: a11y.summary.by_level.AA ?? 0 },
      { label: "triaged", value: `${issues.filter((i) => i.triage && i.triage !== "open").length}/${issues.length}` },
    ],
    charts: [
      {
        type: "bars",
        title: "Issues by success criterion",
        data: Object.entries(a11y.summary.by_criterion)
          .sort((a, b) => b[1] - a[1])
          .map(([label, value]) => ({ label, value })),
      },
      {
        type: "split",
        title: "Issues by severity",
        data: [
          { label: "error", value: sev("error"), tone: "bad" },
          { label: "warning", value: sev("warning"), tone: "warn" },
          { label: "info", value: sev("info"), tone: "info" },
        ],
      },
    ],
    findings,
    refs: refs("wcag22", "androidA11y"),
  };
}

const slug = (s: string) => s.toLowerCase().replace(/[()]/g, "").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");

// ── performance (crawler's perf.json) ───────────────────────────────────────

export interface PerfFile {
  budget_ms: number;
  startup?: { samples: number; median_ms: number; max_ms: number };
  screens: { screen: string; title: string; median_ms: number; frames: number; janky_pct: number; frozen_frames: number; rating: string }[];
  findings?: string[];
}

const perfTone = (rating: string): Tone => (rating === "slow" ? "bad" : rating === "needs work" ? "warn" : "good");

export function perfReport({ perf }: BuildContext): AuditReport {
  if (!perf) return notRun("perf", "Performance", "Crawl with load measurement on (the default) to write perf.json.");
  const screens = [...perf.screens].sort((a, b) => b.median_ms - a.median_ms);
  const good = screens.filter((s) => perfTone(s.rating) === "good").length;
  const score = screens.length ? pct(good, screens.length) : null;
  const over = screens.filter((s) => s.median_ms > perf.budget_ms);
  // Same rule as the crawler (perf.py): > 10% slow frames, and at least 30 frames so a 2-frame transition can't count.
  const isJanky = (s: PerfFile["screens"][number]) => s.frames >= 30 && s.janky_pct > 10;
  const janky = screens.filter(isJanky);

  return {
    schema: 1,
    audit: "perf",
    title: "Performance",
    source: "run",
    status: statusFromScore(score),
    score,
    score_note: "Share of measured screens rated good (load under budget, little jank).",
    summary: `${plural(over.length, "screen")} over the ${perf.budget_ms} ms budget, ${janky.length} janky.`,
    metrics: [
      { label: "cold start (median)", value: perf.startup?.median_ms ?? "—", unit: perf.startup ? "ms" : undefined },
      { label: "screens measured", value: screens.length },
      { label: "over budget", value: over.length, tone: over.length ? "bad" : "good" },
      { label: "janky screens", value: janky.length, tone: janky.length ? "warn" : "good" },
      { label: "slowest", value: screens[0]?.median_ms ?? "—", unit: screens[0] ? "ms" : undefined, hint: screens[0]?.title },
    ],
    charts: [
      {
        type: "bars",
        title: "Load time per screen (median)",
        unit: "ms",
        budget: perf.budget_ms,
        budgetLabel: `${perf.budget_ms} ms budget`,
        data: screens.map((s) => ({ label: s.title, value: s.median_ms, tone: perfTone(s.rating), screen: s.screen, hint: `${s.janky_pct}% of ${s.frames} frames janky` })),
      },
    ],
    findings: screens
      .filter((s) => perfTone(s.rating) !== "good" || isJanky(s))
      .map((s) => ({
        id: `perf::${s.screen}`,
        severity: (s.rating === "slow" ? "error" : s.rating === "needs work" ? "warning" : "info") as Severity,
        category: s.median_ms > perf.budget_ms ? "Load time" : "Jank",
        screen: s.screen,
        title: `${s.title}: ${s.median_ms} ms${s.frames >= 30 ? `, ${s.janky_pct}% janky frames` : ""}`,
        detail: `Rated “${s.rating}”. Budget ${perf.budget_ms} ms.${s.frozen_frames ? ` ${plural(s.frozen_frames, "frozen frame")}.` : ""}`,
        fix: "Profile the transition (Perfetto) and move work off the main thread or behind a placeholder.",
      })),
    refs: refs("androidVitals"),
  };
}

export function notRun(audit: string, title: string, how: string): AuditReport {
  return {
    schema: 1,
    audit,
    title,
    source: "none",
    status: "not_run",
    score: null,
    summary: how,
    metrics: [],
    charts: [],
    findings: [],
    refs: [],
  };
}

