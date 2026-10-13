import { useMemo, useState } from "react";
import { runFile, runKey, useIndex } from "../api";
import { ScreenLink, Stat } from "../components/common";
import { Icon } from "../components/Icon";
import { Bars, Chart, Columns, Meter, SampleTag, toneColor } from "../insights/charts";
import { useAudits } from "../insights/registry";
import type { AuditDef, AuditFinding, AuditRef, AuditReport, AuditStatus, Platform, Severity, Tone } from "../insights/types";
import { href } from "../router";
import { keys, useStored } from "../storage";
import type { AppMapData, Screen } from "../types";
import { STATUS_HELP, STATUSES, fmtDate, fmtDuration, plural, screenMap, shortActivity, statusColor } from "../util";

const SEVERITIES: Severity[] = ["error", "warning", "info"];
const SEV_COLOR: Record<Severity, string> = { error: "var(--st-blocked)", warning: "var(--st-pending)", info: "var(--st-unreachable)" };
const SEV_WORD: Record<Severity, string> = { error: "Error", warning: "Warning", info: "Info" };
const STATUS_WORD: Record<AuditStatus, string> = { pass: "Passing", warn: "Needs attention", fail: "Failing", info: "Info", not_run: "Not run" };
const PLATFORM_WORD: Record<Platform, string> = { android: "Android", ios: "iOS", both: "Android + iOS" };

export default function Insights({ run, map, audit }: { run: string; map: AppMapData; audit?: string }) {
  const [prefs, setPrefs] = useStored(keys.insightsPrefs, { samples: true });
  const { defs, reports, loading } = useAudits(run, map, prefs.samples);
  const def = defs.find((d) => d.id === audit);
  const report = def ? reports[def.id] : undefined;

  return (
    <div className="page insights">
      <div className="row wrap" style={{ gap: 12, marginBottom: 14 }}>
        <div className="grow" style={{ minWidth: "min(100%, 320px)" }}>
          <h1>Insights</h1>
          <div className="muted">Every audit of this run in one place, each checked against the official platform and store docs.</div>
        </div>
        <button className={`chip ${prefs.samples ? "on" : ""}`} aria-pressed={prefs.samples} onClick={() => setPrefs((p) => ({ ...p, samples: !p.samples }))}>
          Show sample audits
        </button>
        <button className="btn" disabled={loading} onClick={() => download(`${run.replace(/\//g, "_")}-insights.md`, toMarkdown(map, defs, reports))}>
          <Icon name="file" size={14} /> Export report
        </button>
      </div>

      <nav className="audit-nav" aria-label="Audits">
        <a href={href("r", run, "insights")} className={!def ? "on" : ""} aria-current={!def ? "page" : undefined}>
          <Icon name="grid" size={14} /> Overview
        </a>
        {defs.map((d) => {
          const r = reports[d.id];
          return (
            <a key={d.id} href={href("r", run, "insights", d.id)} className={def?.id === d.id ? "on" : ""} aria-current={def?.id === d.id ? "page" : undefined}>
              <Icon name={d.icon} size={14} /> {d.title}
              {r && r.status !== "not_run" && <i className="dot" style={{ background: statusTone(r.status) }} aria-hidden />}
            </a>
          );
        })}
      </nav>

      {loading ? (
        <div className="empty">Loading audits…</div>
      ) : def && report ? (
        <AuditPage run={run} map={map} def={def} report={report} />
      ) : (
        <Overview run={run} map={map} defs={defs} reports={reports} />
      )}
    </div>
  );
}

const statusTone = (s: AuditStatus) => (s === "pass" ? toneColor("good") : s === "warn" ? toneColor("warn") : s === "fail" ? toneColor("bad") : "var(--faint)");
const meterTone = (s: AuditStatus): Tone | undefined => (s === "pass" ? "good" : s === "warn" ? "warn" : s === "fail" ? "bad" : undefined);
const count = (r: AuditReport, s: Severity) => r.findings.filter((f) => f.severity === s).length;

// ── overview ────────────────────────────────────────────────────────────────

function Overview({ run, map, defs, reports }: { run: string; map: AppMapData; defs: AuditDef[]; reports: Record<string, AuditReport> }) {
  const ran = defs.filter((d) => reports[d.id]?.status !== "not_run");
  const deadlines = defs
    .flatMap((d) => (reports[d.id]?.findings ?? []).filter((f) => f.due).map((f) => ({ d, f })))
    .sort((a, b) => a.f.due!.localeCompare(b.f.due!));

  return (
    <>
      <RunContext map={map} />

      <div className="audit-grid section">
        {defs.map((d) => (
          <AuditCard key={d.id} run={run} def={d} report={reports[d.id]} />
        ))}
      </div>

      <div className="grid2 section">
        <figure className="panel panel-pad chart">
          <figcaption className="chart-head">
            <b>Findings by audit</b>
            <span className="faint small">By severity</span>
          </figcaption>
          <FindingsByAudit run={run} defs={ran} reports={reports} />
        </figure>
        <figure className="panel panel-pad chart">
          <figcaption className="chart-head">
            <b>Store and platform deadlines</b>
            <span className="faint small">From the official docs each audit cites</span>
          </figcaption>
          <Deadlines run={run} items={deadlines} />
        </figure>
      </div>

      <History run={run} />
      <Sources defs={defs} reports={reports} />
    </>
  );
}

/** Where the run was captured: app, device, OS. Uses the richer device record when the crawl has one. */
function RunContext({ map }: { map: AppMapData }) {
  const { app, device: d } = map.run;
  const name = d.name ?? ([d.manufacturer, d.model].filter(Boolean).join(" ") || "—");
  const kind = [d.type, d.form_factor].filter(Boolean).join(" · ");
  const os = d.android ? `Android ${d.android}${d.sdk ? ` (API ${d.sdk})` : ""}${d.os?.skin ? ` · ${d.os.skin}` : ""}` : "—";
  const dp = d.display?.width_dp ? ` · ${d.display.width_dp} dp${d.display.window_class ? ` (${d.display.window_class})` : ""}` : "";
  const st = d.settings;
  const items: [string, React.ReactNode][] = [
    ["App", <>{app.label ?? app.package} {app.version && <span className="faint">v{app.version}</span>}</>],
    ["Package", <span className="mono">{app.package}</span>],
    ["Device", <>{name}{kind && <span className="faint small"> · {kind}</span>}</>],
    ["OS", os],
    ["Screen", d.width ? `${d.width}×${d.height} px${d.density ? ` · ${d.density} dpi` : ""}${dp}` : "—"],
    [
      "Settings",
      [d.font_scale ? `font ${d.font_scale}×` : null, st?.locale, st?.dark_mode == null ? null : st.dark_mode ? "dark" : "light", st?.navigation]
        .filter(Boolean)
        .join(" · ") || "—",
    ],
    ["Crawled", `${fmtDate(map.run.started_at)} · ${fmtDuration(map.run.elapsed_s)}`],
  ];
  return (
    <dl className="panel run-context">
      {items.map(([k, v]) => (
        <div key={k}>
          <dt className="faint small">{k}</dt>
          <dd>{v}</dd>
        </div>
      ))}
    </dl>
  );
}

function AuditCard({ run, def, report }: { run: string; def: AuditDef; report?: AuditReport }) {
  const notRun = !report || report.status === "not_run";
  return (
    <a className={`panel audit-card ${notRun ? "not-run" : ""}`} href={href("r", run, "insights", def.id)}>
      <span className="row" style={{ gap: 8 }}>
        <span className="audit-icon">
          <Icon name={def.icon} size={16} />
        </span>
        <b className="grow">{def.title}</b>
        {report?.source === "sample" && <SampleTag />}
        {report?.source === "mixed" && <span className="chip sample-tag">part sample</span>}
      </span>
      {notRun ? (
        <>
          <span className="audit-status muted">Not run</span>
          <span className="small faint">{def.produces}</span>
        </>
      ) : (
        <>
          <span className="row" style={{ gap: 10, alignItems: "baseline" }}>
            <span className="audit-score">{report.score ?? "—"}</span>
            <span className="audit-status" style={{ color: statusTone(report.status) }}>
              {STATUS_WORD[report.status]}
            </span>
          </span>
          <Meter score={report.score} label={`${def.title} score`} tone={meterTone(report.status)} />
          <span className="row small muted" style={{ gap: 12 }}>
            {SEVERITIES.map((s) => (
              <span key={s} className="row" style={{ gap: 4 }}>
                <i className="dot" style={{ background: SEV_COLOR[s] }} aria-hidden />
                {count(report, s)} {s === "info" ? "info" : plural(count(report, s), s).replace(/^\d+ /, "")}
              </span>
            ))}
          </span>
          <span className="small muted clamp2">{report.summary}</span>
        </>
      )}
    </a>
  );
}

/** One row per audit: errors, warnings and info as a stacked bar on a shared scale. */
function FindingsByAudit({ run, defs, reports }: { run: string; defs: AuditDef[]; reports: Record<string, AuditReport> }) {
  const rows = defs.map((d) => ({ d, n: SEVERITIES.map((s) => count(reports[d.id], s)) }));
  const max = Math.max(1, ...rows.map((r) => r.n.reduce((a, b) => a + b, 0)));
  if (!rows.length) return <div className="small muted">No audits have run.</div>;
  return (
    <>
      <div className="bars" role="list">
        {rows.map(({ d, n }) => {
          const total = n.reduce((a, b) => a + b, 0);
          const text = `${d.title}: ${SEVERITIES.map((s, k) => `${n[k]} ${s}`).join(", ")}`;
          return (
            <div key={d.id} className="bars-row" role="listitem" title={text} aria-label={text}>
              <a className="bars-label ellipsis" href={href("r", run, "insights", d.id)}>
                {d.title}
              </a>
              <span className="bars-track stacked">
                {SEVERITIES.map((s, k) =>
                  n[k] ? <span key={s} className="bars-fill" style={{ width: `${(100 * n[k]) / max}%`, background: SEV_COLOR[s] }} /> : null,
                )}
              </span>
              <span className="bars-value mono">{total}</span>
            </div>
          );
        })}
      </div>
      <div className="legend chart-legend">
        {SEVERITIES.map((s) => (
          <span key={s}>
            <i className="dot" style={{ background: SEV_COLOR[s] }} aria-hidden /> {s}
          </span>
        ))}
      </div>
    </>
  );
}

const DAY = 86_400_000;
function Deadlines({ run, items }: { run: string; items: { d: AuditDef; f: AuditFinding }[] }) {
  if (!items.length) return <div className="small muted">No dated requirements in the audits that ran.</div>;
  const today = new Date(new Date().toDateString()).getTime();
  return (
    <ol className="deadlines">
      {items.map(({ d, f }) => {
        const due = new Date(f.due! + "T00:00:00").getTime();
        const days = Math.round((due - today) / DAY);
        const when = days === 0 ? "today" : days > 0 ? `in ${plural(days, "day")}` : `${plural(-days, "day")} ago`;
        return (
          <li key={`${d.id}:${f.id}`} className={days < 0 ? "past" : days <= 60 ? "soon" : ""}>
            <time dateTime={f.due} className="mono small">
              {new Date(due).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" })}
            </time>
            <span className="grow">
              <a href={href("r", run, "insights", d.id)}>{f.title}</a>
              <span className="small faint">
                {" "}
                · {when}
                {f.platform && ` · ${PLATFORM_WORD[f.platform]}`}
              </span>
            </span>
          </li>
        );
      })}
    </ol>
  );
}

/** Same project's runs over time, as small multiples on separate scales (never a dual axis). */
function History({ run }: { run: string }) {
  const { data } = useIndex();
  const rows = useMemo(() => {
    const me = data?.runs.find((r) => runKey(r) === run);
    if (!me) return [];
    const same = data!.runs.filter((r) => (me.project ? r.project === me.project : r.app.package === me.app.package));
    return same.sort((a, b) => a.started_at.localeCompare(b.started_at)).slice(-12);
  }, [data, run]);
  if (rows.length < 2) return null;
  const current = rows.findIndex((r) => runKey(r) === run);
  const day = (r: (typeof rows)[number]) => new Date(r.started_at).toLocaleDateString(undefined, { month: "short", day: "numeric" });
  const sameDay = new Set(rows.map(day)).size < rows.length;
  const label = (r: (typeof rows)[number]) =>
    sameDay ? new Date(r.started_at).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : day(r);
  const series: [string, (r: (typeof rows)[number]) => number][] = [
    ["Screens", (r) => r.screens],
    ["Transitions", (r) => r.transitions],
    ["Crashes", (r) => r.crashes],
    ["Steps", (r) => r.steps ?? 0],
  ];
  return (
    <div className="section">
      <h3>Run history</h3>
      <div className="history-grid">
        {series.map(([title, get]) => (
          <figure key={title} className="panel panel-pad chart">
            <figcaption className="chart-head">
              <b>{title}</b>
              <span className="faint small">{plural(rows.length, "run")} · this run highlighted</span>
            </figcaption>
            <Columns
              data={rows.map((r) => ({ label: label(r), value: get(r), hint: `${r.app.version ? `v${r.app.version} · ` : ""}${r.id}`, tone: title === "Crashes" && get(r) ? "bad" : undefined }))}
              highlight={current}
            />
          </figure>
        ))}
      </div>
    </div>
  );
}

function Sources({ defs, reports }: { defs: AuditDef[]; reports: Record<string, AuditReport> }) {
  const seen = new Map<string, AuditRef>();
  for (const d of defs) {
    const r = reports[d.id];
    if (!r || r.status === "not_run") continue;
    for (const ref of r.refs) if (!seen.has(ref.url)) seen.set(ref.url, ref);
  }
  const refs = [...seen.values()];
  const groups = new Map<string, AuditRef[]>();
  for (const r of refs) groups.set(r.publisher ?? "Other", [...(groups.get(r.publisher ?? "Other") ?? []), r]);
  if (!refs.length) return null;
  return (
    <div className="section">
      <h3>Official sources these checks follow</h3>
      <div className="panel panel-pad sources">
        {[...groups].map(([pub, list]) => (
          <div key={pub}>
            <div className="small faint">{pub}</div>
            <ul>
              {list.map((r) => (
                <li key={r.url}>
                  <a href={r.url} target="_blank" rel="noreferrer">
                    {r.title}
                  </a>
                  {r.date && <span className="faint small"> · checked {r.date}</span>}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── one audit ───────────────────────────────────────────────────────────────

function AuditPage({ run, map, def, report }: { run: string; map: AppMapData; def: AuditDef; report: AuditReport }) {
  if (report.status === "not_run")
    return (
      <div className="panel panel-pad empty-audit">
        <span className="audit-icon">
          <Icon name={def.icon} size={20} />
        </span>
        <h2>{def.title} hasn't run for this crawl</h2>
        <p className="muted">{def.blurb}</p>
        <p className="small">
          <b>How to get it:</b> {report.summary || def.produces}
        </p>
        <p className="small faint">
          Any tool can add an audit by writing <code>audits/{def.id}.json</code> into the run folder (see docs/MAP_SCHEMA.md).
        </p>
      </div>
    );

  return (
    <>
      <div className="panel panel-pad audit-head">
        <span className="audit-icon">
          <Icon name={def.icon} size={20} />
        </span>
        <div className="grow col" style={{ gap: 4 }}>
          <span className="row wrap" style={{ gap: 8 }}>
            <h2>{report.title}</h2>
            {report.source === "sample" && <SampleTag />}
            {report.source === "mixed" && <span className="chip sample-tag">part sample</span>}
          </span>
          <span className="muted">{report.summary}</span>
          {(report.tool || report.generated_at) && (
            <span className="small faint">
              {report.tool}
              {report.tool && report.generated_at && " · "}
              {report.generated_at && fmtDate(report.generated_at)}
            </span>
          )}
        </div>
        {report.score != null && (
          <div className="audit-head-score" title={report.score_note}>
            <span className="audit-score">{report.score}</span>
            <span className="audit-status" style={{ color: statusTone(report.status) }}>
              {STATUS_WORD[report.status]}
            </span>
            <Meter score={report.score} label={`${def.title} score`} tone={meterTone(report.status)} />
            {report.score_note && <span className="small faint">{report.score_note}</span>}
          </div>
        )}
      </div>

      {report.metrics.length > 0 && (
        <div className="stats section">
          {report.metrics.map((m) => (
            <Stat
              key={m.label}
              title={m.hint}
              label={m.hint ? `${m.label} · ${m.hint}` : m.label}
              value={
                <span style={{ color: m.tone && m.tone !== "good" ? toneColor(m.tone) : undefined }}>
                  {m.value}
                  {m.unit && <span className="stat-unit"> {m.unit}</span>}
                </span>
              }
            />
          ))}
        </div>
      )}

      {def.id === "coverage" && <CoverageExtras run={run} map={map} />}
      {def.id === "a11y" && (
        <div className="section">
          <a className="btn" href={href("r", run, "a11y")}>
            <Icon name="a11y" size={14} /> Triage findings on the Accessibility tab
          </a>
        </div>
      )}

      {report.charts.length > 0 && (
        <div className="chart-grid section">
          {report.charts.map((c) => (
            <Chart key={c.title} chart={c} run={run} />
          ))}
        </div>
      )}

      {def.id === "stability" && <EventsList run={run} map={map} />}

      <Findings run={run} map={map} report={report} />

      {report.refs.length > 0 && (
        <div className="section">
          <h3>Sources</h3>
          <div className="panel panel-pad">
            <ul className="ref-list">
              {report.refs.map((r) => (
                <li key={r.url}>
                  <a href={r.url} target="_blank" rel="noreferrer">
                    {r.title}
                  </a>
                  {r.publisher && <span className="faint small"> · {r.publisher}</span>}
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </>
  );
}

function Findings({ run, map, report }: { run: string; map: AppMapData; report: AuditReport }) {
  const byId = useMemo(() => screenMap(map), [map]);
  const [sev, setSev] = useState<Severity[]>(SEVERITIES);
  const [platform, setPlatform] = useState<Platform | "all">("all");
  const platforms = [...new Set(report.findings.map((f) => f.platform).filter((p): p is Platform => !!p))];
  const shown = report.findings.filter((f) => sev.includes(f.severity) && (platform === "all" || f.platform === platform || f.platform === "both"));
  const groups = new Map<string, AuditFinding[]>();
  for (const f of [...shown].sort((a, b) => SEVERITIES.indexOf(a.severity) - SEVERITIES.indexOf(b.severity)))
    groups.set(f.category ?? "Findings", [...(groups.get(f.category ?? "Findings") ?? []), f]);

  return (
    <div className="section">
      <div className="row wrap" style={{ gap: 8, marginBottom: 10 }}>
        <h3 className="grow" style={{ margin: 0 }}>
          Findings ({report.findings.length})
        </h3>
        {SEVERITIES.map((s) => (
          <button
            key={s}
            className={`chip ${sev.includes(s) ? "on" : ""}`}
            aria-pressed={sev.includes(s)}
            onClick={() => setSev((p) => (p.includes(s) ? p.filter((x) => x !== s) : [...p, s]))}
          >
            <i className="dot" style={{ background: SEV_COLOR[s] }} aria-hidden /> {SEV_WORD[s]} {count(report, s)}
          </button>
        ))}
        {platforms.length > 1 && (
          <div className="seg" role="group" aria-label="Platform">
            {(["all", ...platforms] as const).map((p) => (
              <button key={p} className={platform === p ? "on" : ""} aria-pressed={platform === p} onClick={() => setPlatform(p)}>
                {p === "all" ? "All" : PLATFORM_WORD[p]}
              </button>
            ))}
          </div>
        )}
      </div>
      {!report.findings.length ? (
        <div className="panel panel-pad muted">Nothing to report.</div>
      ) : !shown.length ? (
        <div className="panel panel-pad muted">No findings match these filters.</div>
      ) : (
        <div className="col" style={{ gap: 14 }}>
          {[...groups].map(([cat, list]) => (
            <div key={cat}>
              <div className="small faint finding-group">
                {cat} · {list.length}
              </div>
              <ul className="panel findings">
                {list.map((f) => (
                  <FindingRow key={f.id} run={run} f={f} screen={f.screen ? byId.get(f.screen) : undefined} />
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function FindingRow({ run, f, screen }: { run: string; f: AuditFinding; screen?: Screen }) {
  return (
    <li className="finding">
      <span className="finding-sev" style={{ color: SEV_COLOR[f.severity] }}>
        <i className="dot" style={{ background: SEV_COLOR[f.severity] }} aria-hidden /> {SEV_WORD[f.severity]}
      </span>
      <div className="col grow" style={{ gap: 4, minWidth: 0 }}>
        <span className="row wrap" style={{ gap: 6 }}>
          <b>{f.title}</b>
          {f.platform && <span className="chip">{PLATFORM_WORD[f.platform]}</span>}
          {f.sample && <SampleTag />}
        </span>
        {f.detail && <span className="small muted">{f.detail}</span>}
        {f.fix && (
          <span className="small">
            <b>Fix:</b> {f.fix}
          </span>
        )}
        {(screen || f.due || f.refs?.length) && (
          <span className="row wrap small" style={{ gap: 12 }}>
            {screen && (
              <span>
                on <ScreenLink run={run} screen={screen} />
              </span>
            )}
            {f.due && <span className="faint">due {new Date(f.due + "T00:00:00").toLocaleDateString(undefined, { dateStyle: "medium" })}</span>}
            {f.refs?.map((r) => (
              <a key={r.url} href={r.url} target="_blank" rel="noreferrer">
                {r.publisher ? `${r.publisher}: ` : ""}
                {r.title}
              </a>
            ))}
          </span>
        )}
      </div>
    </li>
  );
}

// ── audit-specific extras (data the generic layout doesn't cover) ──────────

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
      <div className="section">
        <figure className="panel panel-pad chart">
          <figcaption className="chart-head">
            <b>Element outcomes</b>
            <span className="faint small">{plural(totalEls, "action")} found</span>
          </figcaption>
          <div className="stack split-bar">
            {STATUSES.filter((s) => st.elements[s]).map((s) => (
              <div key={s} style={{ width: `${(100 * (st.elements[s] ?? 0)) / Math.max(1, totalEls)}%`, background: statusColor(s) }} title={`${s}: ${st.elements[s]}`} />
            ))}
          </div>
          <div className="legend chart-legend">
            {STATUSES.filter((s) => st.elements[s]).map((s) => (
              <span key={s} title={STATUS_HELP[s]}>
                <i className="dot" style={{ background: statusColor(s) }} aria-hidden /> <b className="mono">{st.elements[s]}</b> {s}
              </span>
            ))}
          </div>
        </figure>
      </div>
      <div className="chart-grid section">
        <figure className="panel panel-pad chart">
          <figcaption className="chart-head">
            <b>Hubs</b>
            <span className="faint small">Screens reached from the most other screens</span>
          </figcaption>
          <Bars run={run} data={hubs.map((s) => ({ label: s.title, value: inBy.get(s.id)?.size ?? 0, screen: s.id }))} />
        </figure>
        <figure className="panel panel-pad chart">
          <figcaption className="chart-head">
            <b>Activities</b>
            <span className="faint small">
              {visited.size} visited{declared.length ? ` of ${declared.length} declared` : ""}
            </span>
          </figcaption>
          <ul className="plain-list">
            {(declared.length ? declared : [...visited]).map((a) => (
              <li key={a} className="row" style={{ gap: 8 }}>
                <span className="mono small ellipsis grow" title={a}>
                  {shortActivity(a)}
                </span>
                {visited.has(a) ? <span style={{ color: "var(--st-done)" }}>visited</span> : <span className="faint">not reached</span>}
              </li>
            ))}
          </ul>
        </figure>
        <figure className="panel panel-pad chart">
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
    <div className="section">
      <h3>Run events ({map.events.length})</h3>
      <div className="panel" style={{ maxHeight: 320, overflow: "auto" }}>
        <table className="tbl">
          <tbody>
            {map.events.map((e, k) => (
              <tr key={k}>
                <td className="mono small">#{e.step}</td>
                <td>
                  <b style={{ color: e.type === "crash" ? "var(--st-blocked)" : undefined }}>{e.type}</b>{" "}
                  <span className="muted small">{byId.get(e.detail)?.title ?? e.detail}</span>
                  {e.log && (
                    <>
                      {" "}
                      <a className="small" href={runFile(run, e.log)} target="_blank" rel="noreferrer">
                        logcat
                      </a>
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── export ──────────────────────────────────────────────────────────────────

function toMarkdown(map: AppMapData, defs: AuditDef[], reports: Record<string, AuditReport>): string {
  const { app, device } = map.run;
  const out = [
    `# Insights: ${app.label ?? app.package}${app.version ? ` v${app.version}` : ""}`,
    "",
    `Run \`${map.run.id}\` on ${device.name ?? [device.manufacturer, device.model].filter(Boolean).join(" ")}, Android ${device.android ?? "?"} (API ${device.sdk ?? "?"}), ${fmtDate(map.run.started_at)}.`,
    "",
    "| Audit | Score | Status | Errors | Warnings | Info | Data |",
    "|---|---|---|---|---|---|---|",
    ...defs.map((d) => {
      const r = reports[d.id];
      return `| ${d.title} | ${r?.score ?? "—"} | ${STATUS_WORD[r?.status ?? "not_run"]} | ${r ? count(r, "error") : 0} | ${r ? count(r, "warning") : 0} | ${r ? count(r, "info") : 0} | ${r?.source === "sample" ? "sample" : r?.source === "mixed" ? "part sample" : r?.source === "none" ? "—" : "run"} |`;
    }),
  ];
  for (const d of defs) {
    const r = reports[d.id];
    if (!r || r.status === "not_run") continue;
    out.push("", `## ${r.title}${r.source === "sample" ? " (sample data)" : ""}`, "", r.summary, "");
    if (r.score != null) out.push(`Score **${r.score}**: ${STATUS_WORD[r.status]}.${r.score_note ? ` ${r.score_note}` : ""}`, "");
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
