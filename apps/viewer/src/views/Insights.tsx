import { useEffect, useMemo, useRef, useState } from "react";
import { densityFor } from "../a11y";
import { runFile, runKey, useIndex } from "../api";
import { ScreenLink } from "../components/common";
import { Icon, type IconName } from "../components/Icon";
import { Bars, Chart, SampleTag, toneColor } from "../insights/charts";
import { useAudits } from "../insights/registry";
import type { AuditDef, AuditFinding, AuditRef, AuditReport, AuditStatus, Platform, PlannedCheck, Requirement, Severity, Tone } from "../insights/types";
import { href } from "../router";
import { keys, useStored } from "../storage";
import type { AppMapData, RunIndexRow, Screen } from "../types";
import { STATUS_HELP, STATUSES, fmtDate, fmtDuration, plural, rootScreen, screenMap, shortActivity, statusColor } from "../util";

// Insights, as designed on the "AppScreenMap redesign" canvas (design-system skill): a plain question as the
// headline, a hairline ledger of audits sorted by what needs you first, a store/platform calendar, and one page
// per audit. Colour only where a number needs you.

const SEVERITIES: Severity[] = ["error", "warning", "info"];
const SEV_COLOR: Record<Severity, string> = { error: "var(--sev-error)", warning: "var(--sev-warning)", info: "var(--sev-info)" };
const SEV_WORD: Record<Severity, string> = { error: "Error", warning: "Warning", info: "Info" };
const STATUS_WORD: Record<AuditStatus, string> = { pass: "Passing", warn: "Needs attention", fail: "Failing", info: "Info", not_run: "Not run" };
const PLATFORM_WORD: Record<Platform, string> = { android: "Android", ios: "iOS", both: "Android + iOS" };
type View = "android" | "ios";

const statusTone = (s: AuditStatus): Tone | undefined => (s === "pass" ? "good" : s === "warn" ? "warn" : s === "fail" ? "bad" : undefined);
const statusColorOf = (s: AuditStatus) => {
  const t = statusTone(s);
  return t ? toneColor(t) : "var(--faint)";
};
const statusWord = (r: AuditReport) => r.status_label ?? STATUS_WORD[r.status];

/** Findings that apply to one platform view. A finding with no platform comes from the (Android) crawl. */
const onPlatform = (f: AuditFinding, v: View) => (v === "ios" ? f.platform === "ios" || f.platform === "both" : f.platform !== "ios");
const count = (r: AuditReport | undefined, s: Severity, v: View) => (r ? r.findings.filter((f) => f.severity === s && onPlatform(f, v)).length : 0);
/** Crawl audits describe the platform that was crawled; the other platform has no crawl data yet. */
const crawledOn = (d: AuditDef, v: View, crawled: View) => !(v !== crawled && d.group === "crawl");
const crawledPlatform = (map: AppMapData): View => (map.run.device.platform === "ios" ? "ios" : "android");

const DAY = 86_400_000;
const today = () => new Date(new Date().toDateString()).getTime();
const dayOf = (iso: string) => new Date(iso + "T00:00:00").getTime();
const daysFrom = (iso: string) => Math.round((dayOf(iso) - today()) / DAY);
const fmtDay = (iso: string, year = true) =>
  new Date(iso + "T00:00:00").toLocaleDateString(undefined, { day: "numeric", month: "short", ...(year ? { year: "numeric" } : {}) });

export default function Insights({ run, map, audit }: { run: string; map: AppMapData; audit?: string }) {
  const [prefs, setPrefs] = useStored(keys.insightsPrefs, { samples: true });
  const crawled = crawledPlatform(map);
  const [view, setView] = useState<View>(crawled);
  useEffect(() => setView(crawled), [run, crawled]);
  const { defs, reports: raw, loading } = useAudits(run, map, prefs.samples);
  // A finding with no platform comes from the crawl, so it belongs to the platform that was crawled.
  const reports = useMemo(() => {
    const out: Record<string, AuditReport> = {};
    for (const [id, r] of Object.entries(raw))
      out[id] = { ...r, findings: r.findings.map((f) => (f.platform ? f : { ...f, platform: crawled, inferred: true })) };
    return out;
  }, [raw, crawled]);
  const def = defs.find((d) => d.id === audit);

  if (loading) return <div className="empty">Loading audits…</div>;
  return (
    <div className="ins">
      {def && reports[def.id] ? (
        <AuditPage run={run} map={map} def={def} report={reports[def.id]} />
      ) : (
        <Overview
          run={run}
          map={map}
          defs={defs}
          reports={reports}
          view={view}
          crawled={crawled}
          setView={setView}
          samples={prefs.samples}
          toggleSamples={() => setPrefs((p) => ({ ...p, samples: !p.samples }))}
        />
      )}
    </div>
  );
}

// ── overview ────────────────────────────────────────────────────────────────

interface OverviewProps {
  run: string;
  map: AppMapData;
  defs: AuditDef[];
  reports: Record<string, AuditReport>;
  view: View;
  crawled: View;
  setView: (v: View) => void;
  samples: boolean;
  toggleSamples: () => void;
}

function Overview({ run, map, defs, reports, view, crawled, setView, samples, toggleSamples }: OverviewProps) {
  const ran = defs.filter((d) => reports[d.id]?.status !== "not_run" && crawledOn(d, view, crawled));
  const errors = ran.reduce((n, d) => n + count(reports[d.id], "error", view), 0);
  const warnings = ran.reduce((n, d) => n + count(reports[d.id], "warning", view), 0);
  const dated = defs
    .flatMap((d) => (reports[d.id]?.status === "not_run" ? [] : (reports[d.id]?.findings ?? [])).filter((f) => f.due).map((f) => ({ d, f })))
    .filter((x, i, all) => all.findIndex((y) => y.f.due === x.f.due && y.f.title === x.f.title) === i)
    .sort((a, b) => a.f.due!.localeCompare(b.f.due!));
  const next = dated.find(({ f }) => daysFrom(f.due!) >= 0);

  return (
    <div className="ins-page">
      <Hero run={run} map={map} audits={defs.filter((d) => reports[d.id]?.status !== "not_run").length} />

      <section className="ins-totals" aria-label="Totals">
        <Total value={map.stats.screens} label="screens mapped" />
        <Total value={map.stats.transitions} label="transitions" />
        <Total value={errors} label="errors to fix" tone={errors ? "bad" : undefined} />
        <Total value={warnings} label="warnings" tone={warnings ? "warn" : undefined} />
        <Total
          value={next ? fmtDay(next.f.due!, false) : "—"}
          label={next ? `next deadline · ${daysFrom(next.f.due!) === 0 ? "today" : plural(daysFrom(next.f.due!), "day")}` : "no upcoming deadline"}
        />
      </section>

      <section className="ins-section">
        <div className="ins-head">
          <h2>Audits</h2>
          <span className="ins-sub">Sorted by what needs you first</span>
          <span className="grow" />
          <div className="ins-seg" role="group" aria-label="Platform">
            {(["android", "ios"] as View[]).map((p) => (
              <button key={p} type="button" aria-pressed={view === p} onClick={() => setView(p)}>
                <Icon name={p === "ios" ? "apple" : "android"} size={13} /> {p === "ios" ? "iOS" : "Android"}
                {p !== crawled && " · not crawled"}
              </button>
            ))}
          </div>
          <button type="button" className="ins-btn" aria-pressed={samples} onClick={toggleSamples} title="Placeholder data for audits that don't exist yet">
            {samples ? "Hide samples" : "Show samples"}
          </button>
          <button type="button" className="ins-btn" onClick={() => download(`${run.replace(/\//g, "_")}-insights.md`, toMarkdown(map, defs, reports))}>
            <Icon name="download" size={14} /> Export report
          </button>
        </div>
        <Ledger run={run} defs={defs} reports={reports} view={view} crawled={crawled} />
      </section>

      {dated.length > 0 && (
        <section className="ins-section">
          <div className="ins-head">
            <h2>Store and platform calendar</h2>
            <span className="ins-sub">Deadlines from Google Play, the App Store and Android Developers</span>
          </div>
          <Calendar run={run} items={dated} />
        </section>
      )}

      <div className="ins-split">
        <section className="ins-section">
          <div className="ins-head">
            <h2>Findings by audit</h2>
          </div>
          <FindingsByAudit run={run} defs={ran} reports={reports} view={view} />
        </section>
        <RunsOfApp run={run} />
      </div>

      <Sources defs={defs} reports={reports} />
    </div>
  );
}

function Total({ value, label, tone }: { value: React.ReactNode; label: string; tone?: Tone }) {
  return (
    <div className="ins-total">
      <span className="ins-total-v" style={{ color: tone ? toneColor(tone) : undefined }}>
        {value}
      </span>
      <span className="ins-total-l">{label}</span>
    </div>
  );
}

/** The question, where the run was captured, and three of the app's own screens. */
function Hero({ run, map, audits }: { run: string; map: AppMapData; audits: number }) {
  const { app, device: d } = map.run;
  const label = app.label ?? app.package;
  const { scale } = densityFor(map);
  const widthDp = d.display?.width_dp ?? Math.round((d.width || 1080) / scale);
  const windowClass = d.display?.window_class ?? (widthDp < 600 ? "compact" : widthDp < 840 ? "medium" : "expanded");
  const shots = useMemo(() => heroScreens(map), [map]);
  const facts = [
    [d.name ?? ([d.manufacturer, d.model].filter(Boolean).join(" ") || "device"), d.type].filter(Boolean).join(" · "),
    d.platform === "ios"
      ? d.os?.release && `iOS ${d.os.release}`
      : d.android && `Android ${d.android}${d.sdk ? ` · API ${d.sdk}` : ""}${d.os?.skin ? ` · ${d.os.skin}` : ""}`,
    `${widthDp} dp · ${windowClass} window`,
    d.width && `${d.width} × ${d.height}${d.density ? ` · ${d.density} dpi` : ""}${d.font_scale ? ` · font ${d.font_scale}×` : ""}`,
    `${fmtDuration(map.run.elapsed_s)}${map.run.steps ? ` · ${map.run.steps} steps` : ""}`,
  ].filter(Boolean) as string[];

  return (
    <section className="ins-hero">
      <div className="ins-hero-text">
        <span className="ins-kicker">Insights · crawl of {fmtDate(map.run.started_at)}</span>
        <h1>Is {label} ready to ship?</h1>
        <p>
          {audits} audits from one crawl: what the app does on a real device, and what Google Play, the App Store and this year's Android
          and iOS releases will ask of it.
        </p>
        <div className="ins-facts">
          <Icon name="smartphone" size={14} />
          {facts.map((f) => (
            <span key={f}>{f}</span>
          ))}
        </div>
      </div>
      {shots.length > 0 && (
        <div className="ins-phones" aria-hidden>
          {shots.map((s, i) => (
            <span key={s.id} className={`ins-phone ${i === 1 ? "lead" : ""}`} style={{ aspectRatio: `${s.width || 1080} / ${s.height || 2400}` }}>
              <img src={runFile(run, s.thumb!)} alt="" loading="lazy" />
            </span>
          ))}
        </div>
      )}
    </section>
  );
}

/** Launch screen in the middle, the two busiest hubs either side. */
function heroScreens(map: AppMapData): Screen[] {
  const app = map.screens.filter((s) => s.kind === "app" && s.thumb);
  const root = rootScreen(map);
  const into = new Map<string, Set<string>>();
  for (const t of map.transitions) if (t.from !== t.to) into.set(t.to, (into.get(t.to) ?? new Set()).add(t.from));
  const hubs = app.filter((s) => s.id !== root?.id).sort((a, b) => (into.get(b.id)?.size ?? 0) - (into.get(a.id)?.size ?? 0));
  const picks = [hubs[0], root?.thumb ? root : hubs[2], hubs[1]].filter((s): s is Screen => !!s);
  return [...new Map(picks.map((s) => [s.id, s])).values()];
}

/** One row per audit in two groups, most urgent first. */
function Ledger({ run, defs, reports, view, crawled }: { run: string; defs: AuditDef[]; reports: Record<string, AuditReport>; view: View; crawled: View }) {
  const urgency = (d: AuditDef) => {
    const r = reports[d.id];
    if (!r || r.status === "not_run" || !crawledOn(d, view, crawled)) return [1, 0, 0, 0];
    return [0, -count(r, "error", view), -count(r, "warning", view), r.score ?? 100];
  };
  const order = (a: AuditDef, b: AuditDef) => {
    const [x, y] = [urgency(a), urgency(b)];
    for (let i = 0; i < x.length; i++) if (x[i] !== y[i]) return x[i] - y[i];
    return 0;
  };
  return (
    <div className="ledger">
      {(["crawl", "release"] as const).map((g) => (
        <div key={g} role="list" aria-label={g === "crawl" ? "From this crawl" : "Release readiness"}>
          <div className="ledger-cap" aria-hidden>
            <span />
            <span>{g === "release" ? "Release readiness · Android + iOS" : view !== crawled ? `From this crawl · ${crawled === "ios" ? "iOS" : "Android"} only` : "From this crawl"}</span>
            <span className="ledger-counts-cap">Err · Warn · Info</span>
            <span className="ledger-score-cap">Score</span>
            <span />
          </div>
          {defs
            .filter((d) => d.group === g)
            .sort(order)
            .map((d) => (
              <LedgerRow key={d.id} run={run} def={d} report={reports[d.id]} view={view} crawled={crawled} />
            ))}
        </div>
      ))}
    </div>
  );
}

function LedgerRow({ run, def, report, view, crawled }: { run: string; def: AuditDef; report?: AuditReport; view: View; crawled: View }) {
  const off = !report || report.status === "not_run" || !crawledOn(def, view, crawled);
  const soon = !off && report.findings.some((f) => f.due && daysFrom(f.due) >= 0 && daysFrom(f.due) <= 60 && onPlatform(f, view));
  const n = SEVERITIES.map((s) => count(report, s, view));
  const notCrawled = view !== crawled && def.group === "crawl";
  const notSetUp = def.setup === "planned" && (!report || report.status === "not_run");
  return (
    <a className={`ledger-row ${off ? "off" : ""}`} href={href("r", run, "insights", def.id)} role="listitem">
      <span className={`ins-tile ${soon ? "accent" : ""}`}>
        <Icon name={def.icon} size={18} />
      </span>
      <span className="ledger-name">
        <span className="ledger-title">
          {def.title}
          {def.qualifier && <span className="ins-qual">{def.qualifier}</span>}
          {report?.source === "sample" && <SampleTag />}
          {report?.source === "mixed" && <SampleTag label="part sample" />}
        </span>
        <span className="ledger-summary">
          {notCrawled
            ? `${view === "ios" ? "iOS" : "Android"} wasn't crawled in this run. This audit reads the ${crawled === "ios" ? "iOS" : "Android"} crawl.`
            : notSetUp
              ? plannedSummary(def, crawled)
              : off
                ? report?.summary || def.produces
                : report.summary}
        </span>
      </span>
      <span className="ledger-counts" aria-label={off ? "no findings" : SEVERITIES.map((s, i) => `${n[i]} ${s}`).join(", ")}>
        {SEVERITIES.map((s, i) => (
          <span key={s} style={{ color: !off && n[i] ? SEV_COLOR[s] : undefined }}>
            {off ? "–" : n[i]}
          </span>
        ))}
      </span>
      {off ? (
        <span className="ledger-score">
          <span className="ledger-score-v faint">—</span>
          <span className="ledger-status faint">{notCrawled ? "Not crawled" : notSetUp ? "Not set up" : "Not run"}</span>
        </span>
      ) : (
        <span className="ledger-score">
          <span className="ledger-score-v">{report.score ?? "—"}</span>
          <span className="ledger-score-meta">
            <span className="ledger-status" style={{ color: statusColorOf(report.status) }}>
              {statusWord(report)}
            </span>
            {report.score != null && <Meter score={report.score} status={report.status} />}
          </span>
        </span>
      )}
      <Icon name="chevron" size={16} className="ledger-chev" />
    </a>
  );
}

function Meter({ score, status }: { score: number; status: AuditStatus }) {
  return (
    <span className="ins-meter" role="meter" aria-valuemin={0} aria-valuemax={100} aria-valuenow={score} aria-label="score">
      <span style={{ width: `${score}%`, background: statusColorOf(status) }} />
    </span>
  );
}

/** Store and platform dates around today. Horizontal on wide screens, a list on phones. */
function Calendar({ run, items }: { run: string; items: { d: AuditDef; f: AuditFinding }[] }) {
  const now = today();
  const times = items.map(({ f }) => dayOf(f.due!));
  const start = Math.min(now, ...times) - 20 * DAY;
  const end = Math.max(now, ...times) + 35 * DAY;
  const pos = (t: number) => (100 * (t - start)) / (end - start);
  const months: { t: number; label: string }[] = [];
  for (let m = new Date(new Date(start).getFullYear(), new Date(start).getMonth() + 1, 1); m.getTime() <= end; m = new Date(m.getFullYear(), m.getMonth() + 1, 1))
    months.push({
      t: m.getTime(),
      label: m.toLocaleDateString(undefined, { month: "short" }).toUpperCase() + (m.getMonth() === 0 ? ` ${String(m.getFullYear()).slice(2)}` : ""),
    });
  const step = months.length > 9 ? 2 : 1;
  const color = (f: AuditFinding) =>
    daysFrom(f.due!) < 0 ? "var(--faint)" : f.severity === "error" ? "var(--bad)" : f.severity === "warning" ? "var(--warn)" : "var(--accent)";
  const when = (f: AuditFinding) => {
    const n = daysFrom(f.due!);
    return n < 0 ? "passed" : n === 0 ? "today" : n <= 120 ? plural(n, "day") : "";
  };
  const meta = (f: AuditFinding) =>
    [fmtDay(f.due!), f.platform && f.platform !== "both" ? PLATFORM_WORD[f.platform] : null, when(f)].filter(Boolean).join(" · ").toUpperCase();

  // Lay labels out in four lanes (two above the axis, two below), each tied to its dot by a stem. Upcoming
  // deadlines are placed first; a passed one that doesn't fit keeps its dot (and tooltip) without a label.
  const box = useRef<HTMLDivElement>(null);
  const width = useWidth(box);
  const LABEL = 210;
  const AXIS = 124;
  const LANES = [62, 152, 6, 210]; // label tops: near above, near below, far above, far below
  const placed = new Map<number, { top: number; right: boolean }>();
  const span = (j: number, right: boolean) => {
    const x = (pos(dayOf(items[j].f.due!)) / 100) * width;
    return right ? [x - LABEL, x] : [x, x + LABEL];
  };
  const order = items
    .map((it, i) => ({ i, t: dayOf(it.f.due!), past: daysFrom(it.f.due!) < 0 }))
    .sort((x, y) => (x.past === y.past ? (x.past ? y.t - x.t : x.t - y.t) : x.past ? 1 : -1));
  for (const { i, t, past } of order) {
    const px = (pos(t) / 100) * width;
    const aligns = px + LABEL <= width ? [false, true] : [true, false];
    let done = false;
    for (const top of LANES) {
      for (const right of aligns) {
        const [from, to] = span(i, right);
        if (from < -4 || to > width + 4) continue;
        const clear = [...placed].every(([j, q]) => {
          if (q.top !== top) return true;
          const [qf, qt] = span(j, q.right);
          return to + 12 <= qf || from >= qt + 12;
        });
        if (clear) {
          placed.set(i, { top, right });
          done = true;
          break;
        }
      }
      if (done) break;
    }
    if (!done && !past) placed.set(i, { top: LANES[2], right: px > width / 2 });
  }

  return (
    <>
      <div className="cal" role="list" aria-label="Deadlines" ref={box}>
        <div className="cal-axis" />
        <div className="cal-past" style={{ width: `${pos(now)}%` }} />
        {months.map((m, i) =>
          i % step ? null : (
            <span key={m.t} className="cal-month" style={{ left: `${pos(m.t)}%` }} aria-hidden>
              {m.label}
            </span>
          ),
        )}
        <div className="cal-today" style={{ left: `${pos(now)}%` }} aria-hidden>
          <span>TODAY</span>
        </div>
        {items.map(({ d, f }, i) => {
          const x = pos(dayOf(f.due!));
          const past = daysFrom(f.due!) < 0;
          const p = placed.get(i);
          const above = p ? p.top < AXIS : false;
          return (
            <div key={`${d.id}:${f.id}`} role="listitem" aria-label={`${meta(f)}: ${f.title}`}>
              {p && (
                <span
                  className="cal-stem"
                  style={{ left: `${x}%`, top: above ? p.top : AXIS, height: above ? AXIS - p.top : p.top + 14 - AXIS }}
                  aria-hidden
                />
              )}
              <span
                className={`cal-dot ${f.severity === "error" && !past ? "big" : ""}`}
                style={{ left: `${x}%`, background: color(f) }}
                title={`${meta(f)}: ${f.title}`}
              />
              {p && (
                <a
                  className={`cal-label ${p.right ? "right" : ""} ${past ? "past" : ""}`}
                  style={{ left: `${x}%`, top: p.top, width: LABEL }}
                  href={href("r", run, "insights", d.id)}
                >
                  <span className="cal-meta" style={{ color: past ? undefined : color(f) }}>
                    {meta(f)}
                  </span>
                  <span className="cal-title">{f.title}</span>
                </a>
              )}
            </div>
          );
        })}
      </div>
      <ol className="cal-list">
        {items.map(({ d, f }) => (
          <li key={`${d.id}:${f.id}`} className={daysFrom(f.due!) < 0 ? "past" : ""}>
            <span className="cal-dot" style={{ background: color(f) }} />
            <span className="cal-meta" style={{ color: daysFrom(f.due!) < 0 ? undefined : color(f) }}>
              {meta(f)}
            </span>
            <a href={href("r", run, "insights", d.id)}>{f.title}</a>
          </li>
        ))}
      </ol>
    </>
  );
}

function useWidth(ref: React.RefObject<HTMLElement>) {
  const [w, setW] = useState(1000);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setW(e.contentRect.width));
    ro.observe(el);
    return () => ro.disconnect();
  }, [ref]);
  return w;
}

function FindingsByAudit({ run, defs, reports, view }: { run: string; defs: AuditDef[]; reports: Record<string, AuditReport>; view: View }) {
  const rows = defs
    .map((d) => ({ d, n: SEVERITIES.map((s) => count(reports[d.id], s, view)) }))
    .map((r) => ({ ...r, total: r.n.reduce((a, b) => a + b, 0) }))
    .filter((r) => r.total > 0)
    .sort((a, b) => b.total - a.total);
  const max = Math.max(1, ...rows.map((r) => r.total));
  if (!rows.length) return <p className="ins-sub">No findings.</p>;
  return (
    <>
      <div className="fba" role="list">
        {rows.map(({ d, n, total }) => (
          <a
            key={d.id}
            className="fba-row"
            role="listitem"
            href={href("r", run, "insights", d.id)}
            aria-label={`${d.title}: ${SEVERITIES.map((s, k) => `${n[k]} ${s}`).join(", ")}`}
          >
            <span className="fba-label">{d.title}</span>
            <span className="fba-track">
              {SEVERITIES.map((s, k) => (n[k] ? <span key={s} style={{ width: `${(100 * n[k]) / max}%`, background: SEV_COLOR[s] }} /> : null))}
            </span>
            <span className="fba-total">{total}</span>
          </a>
        ))}
      </div>
      <div className="ins-legend">
        {SEVERITIES.map((s) => (
          <span key={s}>
            <i style={{ background: SEV_COLOR[s] }} /> {s}
          </span>
        ))}
      </div>
    </>
  );
}

/** Runs of the same app, latest first, with the change from the run before. */
function RunsOfApp({ run }: { run: string }) {
  const { data } = useIndex();
  const rows = useMemo(() => {
    const me = data?.runs.find((r) => runKey(r) === run);
    if (!me) return [];
    return data!.runs
      .filter((r) => (me.project ? r.project === me.project : r.app.package === me.app.package))
      .sort((a, b) => b.started_at.localeCompare(a.started_at))
      .slice(0, 6);
  }, [data, run]);
  if (rows.length < 2) return null;
  const me = rows.find((r) => runKey(r) === run);
  const delta = (cur: number, prev: number | undefined, worseUp: boolean) => {
    if (prev == null || cur === prev) return null;
    const d = cur - prev;
    const bad = worseUp ? d > 0 : d < 0;
    return <span style={{ color: bad ? "var(--bad)" : "var(--faint)" }}>{d > 0 ? `+${d}` : `−${-d}`}</span>;
  };
  const when = (r: RunIndexRow) => new Date(r.started_at).toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  return (
    <section className="ins-section">
      <div className="ins-head">
        <h2>Runs of this app</h2>
        <span className="ins-sub">Latest first</span>
      </div>
      <div className="runs-tbl" role="table">
        <div className="runs-row cap" role="row">
          <span role="columnheader">Run</span>
          <span role="columnheader">Screens</span>
          <span role="columnheader">Links</span>
          <span role="columnheader">Crashes</span>
        </div>
        {rows.map((r, i) => {
          const prev = rows[i + 1];
          const mine = runKey(r) === run;
          return (
            <a key={runKey(r)} className={`runs-row ${mine ? "mine" : ""}`} role="row" href={href("r", runKey(r), "insights")}>
              <span role="cell" className="runs-when">
                <span>
                  {when(r)}
                  {i === 0 && <span className="ins-tag accent">latest</span>}
                  {mine && <span className="ins-tag">this run</span>}
                </span>
                <span className="ins-meta">{[r.app.version && `v${r.app.version}`, r.device.model, r.steps && `${r.steps} steps`].filter(Boolean).join(" · ")}</span>
              </span>
              <span role="cell">
                {r.screens} {delta(r.screens, prev?.screens, false)}
              </span>
              <span role="cell">
                {r.transitions} {delta(r.transitions, prev?.transitions, false)}
              </span>
              <span role="cell" style={{ color: r.crashes ? "var(--bad)" : undefined }}>
                {r.crashes} {delta(r.crashes, prev?.crashes, true)}
              </span>
            </a>
          );
        })}
      </div>
      <a className="ins-link" href={href("r", run, "compare", me?.diffs[0])}>
        Compare with an earlier run →
      </a>
    </section>
  );
}

function Sources({ defs, reports }: { defs: AuditDef[]; reports: Record<string, AuditReport> }) {
  const seen = new Map<string, AuditRef>();
  for (const d of defs) {
    const r = reports[d.id];
    if (r && r.status !== "not_run") for (const ref of r.refs) if (!seen.has(ref.url)) seen.set(ref.url, ref);
  }
  const refs = [...seen.values()];
  if (!refs.length) return null;
  const checked = refs
    .map((r) => r.date)
    .filter((x): x is string => !!x)
    .sort()
    .pop();
  return (
    <footer className="ins-sources">
      <span className="ins-kicker faint">Checks follow{checked ? ` · checked ${fmtDay(checked)}` : ""}</span>
      <div>
        {refs.map((r) => (
          <a key={r.url} href={r.url} target="_blank" rel="noreferrer" title={r.publisher}>
            {r.title} ↗
          </a>
        ))}
      </div>
    </footer>
  );
}

// ── one audit ───────────────────────────────────────────────────────────────

function AuditPage({ run, map, def, report }: { run: string; map: AppMapData; def: AuditDef; report: AuditReport }) {
  const back = (
    <a className="ins-back" href={href("r", run, "insights")}>
      ← Insights
    </a>
  );
  if (report.status === "not_run")
    return (
      <div className="ins-page">
        {back}
        {def.setup === "planned" ? <NotSetUp run={run} map={map} def={def} /> : <NotRun def={def} report={report} />}
      </div>
    );

  const requirements = report.findings.filter((f) => f.requirement);
  return (
    <div className="ins-page">
      <div className="ins-audit-top">
        {back}
        <section className="ins-audit-head">
          <span className={`ins-tile big ${def.group === "release" ? "accent" : ""}`}>
            <Icon name={def.icon} size={24} />
          </span>
          <div className="ins-audit-title">
            <span className="ins-kicker">
              {def.group === "release" ? "Release readiness" : "From this crawl"}
              {def.qualifier ? ` · ${def.qualifier}` : ""}
            </span>
            <h1>
              {report.title}
              {report.source === "sample" && <SampleTag label="sample data" />}
              {report.source === "mixed" && <SampleTag label="part sample" />}
            </h1>
            <p>{report.summary}</p>
            {(report.tool || report.generated_at) && (
              <span className="ins-meta">{[report.tool, report.generated_at && fmtDate(report.generated_at)].filter(Boolean).join(" · ")}</span>
            )}
          </div>
          {report.score != null && (
            <div className="ins-audit-score">
              <span className="ins-audit-score-row">
                <span className="ins-audit-score-v">{report.score}</span>
                <span style={{ color: statusColorOf(report.status) }}>{statusWord(report)}</span>
              </span>
              <Meter score={report.score} status={report.status} />
              {report.score_note && <span className="ins-meta">{report.score_note}</span>}
            </div>
          )}
        </section>
      </div>

      {report.metrics.length > 0 && (
        <section className="ins-totals" aria-label="Metrics">
          {report.metrics.map((m) => (
            <div key={m.label} className="ins-total" title={m.hint}>
              <span className="ins-total-v" style={{ color: m.tone && m.tone !== "good" ? toneColor(m.tone) : undefined }}>
                {m.value}
                {m.unit && <span className="ins-unit"> {m.unit}</span>}
              </span>
              <span className="ins-total-l">
                {m.hint ? `${m.label} · ${m.hint}` : m.label}
                {m.sample && <SampleTag />}
              </span>
            </div>
          ))}
        </section>
      )}

      {requirements.length > 0 && <Requirements store={def.id === "store"} items={requirements} />}
      {def.id === "store" && <ListingScreens run={run} map={map} />}
      {def.id === "coverage" && <CoverageExtras run={run} map={map} />}
      {def.id === "a11y" && (
        <a className="ins-btn wide" href={href("r", run, "a11y")}>
          <Icon name="a11y" size={14} /> Triage every finding on the Accessibility tab
        </a>
      )}

      {report.charts.length > 0 && (
        <div className="ins-charts">
          {report.charts.map((c) => (
            <Chart key={c.title} chart={c} run={run} />
          ))}
        </div>
      )}

      {def.id === "stability" && <EventsList run={run} map={map} />}

      <Findings run={run} map={map} report={report} />

      {report.refs.length > 0 && (
        <footer className="ins-sources">
          <span className="ins-kicker faint">Sources</span>
          <div>
            {report.refs.map((r) => (
              <a key={r.url} href={r.url} target="_blank" rel="noreferrer">
                {r.publisher ? `${r.publisher}: ` : ""}
                {r.title} ↗
              </a>
            ))}
          </div>
        </footer>
      )}
    </div>
  );
}

/** "14 checks planned: exported components, hard-coded secrets, …" for the overview row of an audit that isn't set up. */
function plannedSummary(def: AuditDef, crawled: View): string {
  const checks = (def.planned ?? []).filter((c) => !c.platform || c.platform === "both" || c.platform === crawled);
  if (!checks.length) return def.blurb;
  const names = checks.slice(0, 3).map((c) => c.title.charAt(0).toLowerCase() + c.title.slice(1));
  return `${plural(checks.length, "check")} planned: ${names.join(", ")}${checks.length > 3 ? ", …" : ""}`;
}

/** An audit the viewer can build from run files, when this crawl simply lacks them. */
function NotRun({ def, report }: { def: AuditDef; report: AuditReport }) {
  return (
    <section className="ins-empty">
      <span className="ins-tile big">
        <Icon name={def.icon} size={24} />
      </span>
      <h1>{def.title} hasn't run for this crawl</h1>
      <p>{def.blurb}</p>
      <p>
        <b>How to get it:</b> {report.summary || def.produces}
      </p>
    </section>
  );
}

/**
 * An audit whose checks don't exist yet (Security, Platform changes, Store readiness, Adaptive UI): say so plainly, then
 * list every check it will run, grouped, each marked "not set up", so the page shows what coverage means before it ships.
 */
function NotSetUp({ map, def }: { run: string; map: AppMapData; def: AuditDef }) {
  const crawled = crawledPlatform(map);
  const [all, setAll] = useState(false);
  const planned = def.planned ?? [];
  const mine = (c: PlannedCheck) => !c.platform || c.platform === "both" || c.platform === crawled;
  const shown = all ? planned : planned.filter(mine);
  const hidden = planned.length - planned.filter(mine).length;
  const groups = new Map<string, PlannedCheck[]>();
  for (const c of shown) groups.set(c.category ?? "Planned checks", [...(groups.get(c.category ?? "Planned checks") ?? []), c]);
  const sev = (c: PlannedCheck) => (c.severity ? SEV_WORD[c.severity].toUpperCase() : "");

  return (
    <>
      <section className="ins-audit-head">
        <span className="ins-tile big">
          <Icon name={def.icon} size={24} />
        </span>
        <div className="ins-audit-title">
          <span className="ins-kicker">
            {def.group === "release" ? "Release readiness" : "From this crawl"}
            {def.qualifier ? ` · ${def.qualifier}` : ""}
          </span>
          <h1>
            {def.title} isn't set up yet
            <span className="ins-state">NOT SET UP</span>
          </h1>
          <p>{def.blurb} Nothing below has run, so this audit is not a pass: it simply has no coverage yet.</p>
        </div>
      </section>

      <section className="ins-totals" aria-label="Coverage">
        <div className="ins-total">
          <span className="ins-total-v">0</span>
          <span className="ins-total-l">checks run</span>
        </div>
        <div className="ins-total">
          <span className="ins-total-v">{planned.length}</span>
          <span className="ins-total-l">checks planned</span>
        </div>
        {planned.some((c) => c.severity) && (
          <div className="ins-total">
            <span className="ins-total-v">{planned.filter((c) => c.severity === "error").length}</span>
            <span className="ins-total-l">would block a release</span>
          </div>
        )}
        <div className="ins-total">
          <span className="ins-total-v">{[...new Set(planned.map((c) => c.needs).filter(Boolean))].length}</span>
          <span className="ins-total-l">kinds of input needed</span>
        </div>
      </section>

      <section className="ins-section">
        <div className="ins-head">
          <h2>What it will check</h2>
          <span className="ins-sub">
            {shown.length} for {all ? "every platform" : crawled === "ios" ? "iOS" : "Android"}
          </span>
          <span className="grow" />
          {hidden > 0 && (
            <button type="button" className="ins-btn sm" aria-pressed={all} onClick={() => setAll(!all)}>
              {all ? "This platform only" : `Show ${hidden} for the other platform`}
            </button>
          )}
        </div>
        {[...groups].map(([cat, list]) => (
          <div key={cat} className="plan-group">
            <div className="plan-cap">
              {cat} · {list.length}
            </div>
            <ul className="plan-list">
              {list.map((c) => (
                <li key={c.id ?? c.title} className="plan-row">
                  <span className="plan-glyph" title="Not set up">
                    <Icon name="status-unknown" size={18} label="not set up" />
                  </span>
                  <div className="plan-main">
                    <span className="plan-title">
                      {c.title}
                      {c.platform && c.platform !== "both" && <span className="ins-tag">{PLATFORM_WORD[c.platform]}</span>}
                    </span>
                    <span className="plan-detail">{c.detail}</span>
                    {c.fix && (
                      <span className="plan-fix">
                        <span className="faint">Fix</span> {c.fix}
                      </span>
                    )}
                    {c.refs && c.refs.length > 0 && (
                      <span className="plan-refs">
                        {c.refs.map((r) => (
                          <a key={r.url} href={r.url} target="_blank" rel="noreferrer">
                            {r.publisher ? `${r.publisher}: ` : ""}
                            {r.title} ↗
                          </a>
                        ))}
                      </span>
                    )}
                  </div>
                  <div className="plan-meta">
                    {c.severity && <span style={{ color: SEV_COLOR[c.severity] }}>{sev(c)}</span>}
                    {c.needs && <span>needs {c.needs}</span>}
                  </div>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </section>

      {def.enable && def.enable.length > 0 && (
        <section className="ins-section">
          <div className="ins-head">
            <h2>Turn it on</h2>
          </div>
          <pre className="plan-cmd">{def.enable.join("\n")}</pre>
        </section>
      )}

      <p className="ins-sub">
        Any tool can fill this page: write <code>audits/{def.id}.json</code> into the run folder (docs/MAP_SCHEMA.md) and it
        replaces this placeholder. The rules and how to run them live in the {def.id === "security" ? "security-rules and security-audit skills" : "audit's skill"}.
      </p>
    </>
  );
}

const REQ: Record<Requirement, { icon: IconName; color: string; word: string }> = {
  met: { icon: "status-met", color: "var(--good)", word: "met" },
  due: { icon: "status-due", color: "var(--warn)", word: "due" },
  blocked: { icon: "status-blocked", color: "var(--bad)", word: "blocked" },
  upcoming: { icon: "status-upcoming", color: "var(--accent)", word: "upcoming" },
  not_checked: { icon: "status-unknown", color: "var(--faint)", word: "not checked" },
};

/** Requirements side by side per platform: Google Play | App Store for the store audit. */
function Requirements({ store, items }: { store: boolean; items: AuditFinding[] }) {
  const cols: { p: View; title: string; icon: IconName }[] = [
    { p: "android", title: store ? "Google Play" : "Android", icon: "android" },
    { p: "ios", title: store ? "App Store" : "iOS", icon: "apple" },
  ];
  return (
    <section className="req-grid">
      {cols.map(({ p, title, icon }) => {
        const list = items.filter((f) => onPlatform(f, p)).sort((a, b) => (a.due ?? "9").localeCompare(b.due ?? "9"));
        if (!list.length) return null;
        return (
          <div key={p} className="req-col">
            <div className="req-head">
              <Icon name={icon} size={18} />
              <b>{title}</b>
            </div>
            {list.map((f) => {
              const r = REQ[f.requirement!];
              const n = f.due ? daysFrom(f.due) : null;
              const quiet = f.requirement === "met" || f.requirement === "not_checked";
              return (
                <div key={f.id} className="req-row">
                  <span style={{ color: r.color }}>
                    <Icon name={r.icon} size={18} label={r.word} />
                  </span>
                  <span className="req-text">
                    <span>{f.title}</span>
                    {f.detail && <span className="ins-meta">{f.detail}</span>}
                  </span>
                  <span className="req-when" style={{ color: quiet ? "var(--faint)" : r.color }}>
                    {f.due ? fmtDay(f.due).toUpperCase() : "—"}
                    <br />
                    {quiet || n == null ? r.word : n < 0 ? "passed" : n === 0 ? "today" : plural(n, "day")}
                  </span>
                </div>
              );
            })}
          </div>
        );
      })}
    </section>
  );
}

/** Crawl screenshots that could seed a store listing, checked against the stores' size rules. */
function ListingScreens({ run, map }: { run: string; map: AppMapData }) {
  const shots = heroScreens(map).filter((s) => s.screenshot);
  if (!shots.length) return null;
  const w = shots[0].width || 1080;
  const h = shots[0].height || 2400;
  const ratio = Math.max(w, h) / Math.min(w, h);
  const playOk = ratio <= 2 && Math.min(w, h) >= 320 && Math.max(w, h) <= 3840;
  return (
    <section className="ins-section">
      <div className="ins-head">
        <h2>Screens you can use for the listing</h2>
        <span className="ins-sub">Straight from the crawl, at the device's real size</span>
      </div>
      <div className="listing">
        {shots.map((s) => (
          <figure key={s.id}>
            <span className="ins-phone" style={{ aspectRatio: `${s.width || 1080} / ${s.height || 2400}` }}>
              <img src={runFile(run, s.thumb ?? s.screenshot!)} alt={`${s.title} screen`} loading="lazy" />
            </span>
            <figcaption>
              <ScreenLink run={run} screen={s}>
                {s.title}
              </ScreenLink>
              <span className="ins-meta">
                {s.id} · {s.width}×{s.height}
              </span>
            </figcaption>
          </figure>
        ))}
        <ul className="listing-checks">
          <li>
            <span style={{ color: playOk ? "var(--good)" : "var(--warn)" }}>
              <Icon name={playOk ? "status-met" : "status-due"} size={16} label={playOk ? "fits" : "needs work"} />
            </span>
            {playOk
              ? `Google Play phone · ${ratio.toFixed(2)}:1 fits Play's 2:1 limit`
              : `Google Play phone · ${ratio.toFixed(2)}:1 is over Play's 2:1 limit, crop or pad`}
          </li>
          <li className="faint">
            <Icon name="status-unknown" size={16} label="not checked" />
            Play 7" and 10" tablet · needs a tablet crawl
          </li>
          <li className="faint">
            <Icon name="status-unknown" size={16} label="not checked" />
            iPhone and iPhone Duo · needs an iOS crawl
          </li>
        </ul>
      </div>
    </section>
  );
}

function Findings({ run, map, report }: { run: string; map: AppMapData; report: AuditReport }) {
  const byId = useMemo(() => screenMap(map), [map]);
  const [sev, setSev] = useState<Severity[]>(SEVERITIES);
  const [platform, setPlatform] = useState<View | "all">("all");
  const platforms = (["android", "ios"] as View[]).filter((p) => report.findings.some((f) => onPlatform(f, p)));
  const inPlatform = (f: AuditFinding) => platform === "all" || onPlatform(f, platform);
  const shown = report.findings
    .filter((f) => sev.includes(f.severity) && inPlatform(f))
    .sort((a, b) => SEVERITIES.indexOf(a.severity) - SEVERITIES.indexOf(b.severity));
  return (
    <section className="ins-section">
      <div className="ins-head">
        <h2>Findings</h2>
        <span className="grow" />
        {platforms.length > 1 &&
          (["all", ...platforms] as const).map((p) => (
            <button key={p} type="button" className="ins-btn sm" aria-pressed={platform === p} onClick={() => setPlatform(p)}>
              {p === "all" ? "All" : PLATFORM_WORD[p]} {report.findings.filter((f) => p === "all" || onPlatform(f, p)).length}
            </button>
          ))}
        {SEVERITIES.map((s) => (
          <button
            key={s}
            type="button"
            className="ins-btn sm"
            aria-pressed={sev.includes(s)}
            onClick={() => setSev((p) => (p.includes(s) ? p.filter((x) => x !== s) : [...p, s]))}
          >
            <i className="ins-dot" style={{ background: SEV_COLOR[s] }} /> {SEV_WORD[s]} {report.findings.filter((f) => f.severity === s && inPlatform(f)).length}
          </button>
        ))}
      </div>
      {!report.findings.length ? (
        <p className="ins-sub">Nothing to report.</p>
      ) : !shown.length ? (
        <p className="ins-sub">No findings match these filters.</p>
      ) : (
        <ul className="findings">
          {shown.map((f) => {
            const screen = f.screen ? byId.get(f.screen) : undefined;
            const tags = [f.category, !f.inferred && f.platform && PLATFORM_WORD[f.platform], f.due && `due ${fmtDay(f.due)}`].filter(Boolean).join(" · ");
            return (
              <li key={f.id} className="finding">
                <span className="finding-sev" style={{ color: SEV_COLOR[f.severity] }}>
                  ● {f.severity.toUpperCase()}
                </span>
                <div className="finding-body">
                  <span className="finding-title">
                    {f.title}
                    {f.sample && <SampleTag />}
                  </span>
                  {f.detail && <span className="finding-detail">{f.detail}</span>}
                  {f.fix && (
                    <span className="finding-fix">
                      <span className="faint">Fix</span> {f.fix}
                    </span>
                  )}
                  {(tags || screen || f.refs?.length) && (
                    <span className="finding-meta">
                      {tags && <span className="ins-mono">{tags.toUpperCase()}</span>}
                      {screen && (
                        <span>
                          on <ScreenLink run={run} screen={screen} />
                        </span>
                      )}
                      {f.refs?.map((r) => (
                        <a key={r.url} href={r.url} target="_blank" rel="noreferrer">
                          {r.publisher ? `${r.publisher}: ` : ""}
                          {r.title} ↗
                        </a>
                      ))}
                    </span>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

// ── audit-specific extras ───────────────────────────────────────────────────

function CoverageExtras({ run, map }: { run: string; map: AppMapData }) {
  const st = map.stats;
  const app = map.screens.filter((s) => s.kind === "app");
  const totalEls = Object.values(st.elements).reduce((a, b) => a + (b ?? 0), 0);
  const outBy = new Map<string, Set<string>>();
  const inBy = new Map<string, Set<string>>();
  for (const t of map.transitions) {
    if (t.from === t.to) continue;
    outBy.set(t.from, (outBy.get(t.from) ?? new Set()).add(t.kind));
    inBy.set(t.to, (inBy.get(t.to) ?? new Set()).add(t.from));
  }
  const deadEnds = app.filter((s) => {
    const kinds = outBy.get(s.id);
    return s.patterns.includes("dead_end") || !kinds || [...kinds].every((k) => k === "back" || k === "up");
  });
  const hubs = [...app]
    .sort((a, b) => (inBy.get(b.id)?.size ?? 0) - (inBy.get(a.id)?.size ?? 0))
    .slice(0, 8)
    .filter((s) => inBy.get(s.id)?.size);
  const declared = map.run.app.activities ?? [];
  const visited = new Set(st.activities_visited);

  return (
    <>
      <section className="ins-section">
        <div className="ins-head">
          <h2>Element outcomes</h2>
          <span className="ins-sub">{plural(totalEls, "action")} found</span>
        </div>
        <div className="ins-stack">
          {STATUSES.filter((s) => st.elements[s]).map((s) => (
            <span key={s} style={{ width: `${(100 * (st.elements[s] ?? 0)) / Math.max(1, totalEls)}%`, background: statusColor(s) }} title={`${s}: ${st.elements[s]}`} />
          ))}
        </div>
        <div className="ins-legend">
          {STATUSES.filter((s) => st.elements[s]).map((s) => (
            <span key={s} title={STATUS_HELP[s]}>
              <i style={{ background: statusColor(s) }} /> <b className="ins-mono">{st.elements[s]}</b> {s}
            </span>
          ))}
        </div>
      </section>
      <div className="ins-charts">
        <figure className="chart">
          <figcaption className="chart-head">
            <b>Hubs</b>
            <span className="faint small">Screens reached from the most other screens</span>
          </figcaption>
          <Bars run={run} data={hubs.map((s) => ({ label: s.title, value: inBy.get(s.id)?.size ?? 0, screen: s.id }))} />
        </figure>
        <figure className="chart">
          <figcaption className="chart-head">
            <b>Activities</b>
            <span className="faint small">
              {visited.size} visited{declared.length ? ` of ${declared.length} declared` : ""}
            </span>
          </figcaption>
          <ul className="plain-list">
            {(declared.length ? declared : [...visited]).map((a) => (
              <li key={a} className="row" style={{ gap: 8 }}>
                <span className="ins-mono ellipsis grow" title={a}>
                  {shortActivity(a)}
                </span>
                {visited.has(a) ? <span style={{ color: "var(--good)" }}>visited</span> : <span className="faint">not reached</span>}
              </li>
            ))}
          </ul>
        </figure>
        <figure className="chart">
          <figcaption className="chart-head">
            <b>Dead ends</b>
            <span className="faint small">The only way out is back</span>
          </figcaption>
          {deadEnds.length ? (
            <ul className="plain-list">
              {deadEnds.map((s) => (
                <li key={s.id}>
                  <ScreenLink run={run} screen={s} />
                </li>
              ))}
            </ul>
          ) : (
            <div className="small muted">No dead ends.</div>
          )}
        </figure>
      </div>
    </>
  );
}

function EventsList({ run, map }: { run: string; map: AppMapData }) {
  const byId = screenMap(map);
  if (!map.events.length) return null;
  return (
    <section className="ins-section">
      <div className="ins-head">
        <h2>Run events</h2>
        <span className="ins-sub">{map.events.length}</span>
      </div>
      <ul className="events">
        {map.events.map((e, k) => (
          <li key={k}>
            <span className="ins-mono faint">#{e.step}</span>
            <b style={{ color: e.type === "crash" ? "var(--bad)" : undefined }}>{e.type.replace("_", " ")}</b>
            <span className="muted">{(e.screen && byId.get(e.screen)?.title) || byId.get(e.detail)?.title || e.detail}</span>
            {e.log && (
              <a href={runFile(run, e.log)} target="_blank" rel="noreferrer">
                logcat ↗
              </a>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

// ── export ──────────────────────────────────────────────────────────────────

function toMarkdown(map: AppMapData, defs: AuditDef[], reports: Record<string, AuditReport>): string {
  const { app, device } = map.run;
  const out = [
    `# Is ${app.label ?? app.package}${app.version ? ` v${app.version}` : ""} ready to ship?`,
    "",
    `Run \`${map.run.id}\` on ${device.name ?? [device.manufacturer, device.model].filter(Boolean).join(" ")}, ${device.platform === "ios" ? `iOS ${device.os?.release ?? "?"}` : `Android ${device.android ?? "?"} (API ${device.sdk ?? "?"})`}, ${fmtDate(map.run.started_at)}.`,
    "",
    "| Audit | Score | Status | Errors | Warnings | Info | Data |",
    "|---|---|---|---|---|---|---|",
    ...defs.map((d) => {
      const r = reports[d.id];
      const n = (s: Severity) => (r ? r.findings.filter((f) => f.severity === s).length : 0);
      const data = r?.source === "sample" ? "sample" : r?.source === "mixed" ? "part sample" : r?.source === "none" ? "—" : "run";
      return `| ${d.title} | ${r?.score ?? "—"} | ${r ? statusWord(r) : "Not run"} | ${n("error")} | ${n("warning")} | ${n("info")} | ${data} |`;
    }),
  ];
  for (const d of defs) {
    const r = reports[d.id];
    if (!r || r.status === "not_run") continue;
    out.push("", `## ${r.title}${r.source === "sample" ? " (sample data)" : ""}`, "", r.summary, "");
    if (r.score != null) out.push(`Score **${r.score}**: ${statusWord(r)}.${r.score_note ? ` ${r.score_note}` : ""}`, "");
    for (const f of r.findings) {
      out.push(`- **${SEV_WORD[f.severity]}** ${f.title}${f.platform ? ` _(${PLATFORM_WORD[f.platform]})_` : ""}${f.due ? `, due ${f.due}` : ""}${f.sample ? " _(sample)_" : ""}`);
      if (f.detail) out.push(`  ${f.detail}`);
      if (f.fix) out.push(`  Fix: ${f.fix}`);
      for (const ref of f.refs ?? []) out.push(`  [${ref.title}](${ref.url})`);
    }
    if (r.refs.length) out.push("", "Sources: " + r.refs.map((ref) => `[${ref.title}](${ref.url})`).join(" · "));
  }
  return out.join("\n") + "\n";
}

function download(name: string, text: string) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([text], { type: "text/markdown" }));
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}
