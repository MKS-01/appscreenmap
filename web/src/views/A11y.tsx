import { useEffect, useMemo, useState } from "react";
import { RULES, SEVERITY_COLOR, TRIAGE_LABEL, densityFor, useA11y, type A11yIssue, type RuleId, type Severity, type TriageStatus } from "../a11y";
import A11yIssueTable, { statusOf } from "../components/A11yIssueTable";
import { Stat, Thumb } from "../components/common";
import { Icon } from "../components/Icon";
import { notesStatus, useNotes, type RunTriage } from "../notes";
import { href, screenHref } from "../router";
import { runFile, useText } from "../api";
import { keys, read, useStored, write } from "../storage";
import type { AppMapData, Screen } from "../types";
import { screenMap } from "../util";

const SEVERITIES: Severity[] = ["error", "warning", "info"];
type StatusFilter = "all" | "unreviewed" | TriageStatus;

export default function A11y({ run, map, view }: { run: string; map: AppMapData; view?: string }) {
  const { issues, done, total } = useA11y(run, map);
  const notes = useNotes(run);
  const byId = useMemo(() => screenMap(map), [map]);
  const density = densityFor(map);
  const report = useReportUrl(run);
  const [f, setF] = useStored(keys.a11yPrefs, {
    severities: SEVERITIES as Severity[],
    rule: null as RuleId | null,
    status: "all" as StatusFilter,
  });

  const st = (i: A11yIssue) => statusOf(notes.a11y, i);
  const shown = issues.filter(
    (i) =>
      f.severities.includes(i.severity) &&
      (!f.rule || i.rule === f.rule) &&
      (f.status === "all" ? st(i) !== "false_positive" : f.status === "unreviewed" ? st(i) === "open" : st(i) === f.status),
  );
  const groups = new Map<string, A11yIssue[]>();
  for (const i of shown) groups.set(i.screen, [...(groups.get(i.screen) ?? []), i]);

  const count = (pred: (i: A11yIssue) => boolean) => issues.filter(pred).length;
  const reviewed = count((i) => st(i) !== "open");
  const ruleCounts = (Object.keys(RULES) as RuleId[]).map((r) => [r, count((i) => i.rule === r)] as const).filter(([, n]) => n > 0);

  if (view === "report" && report) return <ReportView run={run} url={report} />;

  return (
    <div className="page">
      <div className="row wrap" style={{ marginBottom: 16, gap: 12 }}>
        <div className="grow">
          {report && <A11yNav run={run} view="findings" />}
          <span className="kicker">Accessibility · {total} screens checked</span>
          <h1>Can everyone use this app?</h1>
          <p className="lede">
            Automated checks on every mapped screen, modelled on Android Accessibility Scanner. Triage each finding; decisions are
            saved with the run.{report && " Findings you mark Needs fix are included in the WCAG 2.2 report."}
          </p>
        </div>
        {report && (
          <a className="btn primary" href={href("r", run, "a11y", "report")}>
            <Icon name="a11y" size={14} /> View WCAG 2.2 report
          </a>
        )}
        <button className="btn" onClick={() => download(`${run.replace(/\//g, "_")}-a11y.md`, toMarkdown(map, issues, notes.a11y, byId), "text/markdown")} disabled={!issues.length}>
          Export Markdown
        </button>
        <button className="btn" onClick={() => download(`${run.replace(/\//g, "_")}-a11y.csv`, toCsv(issues, notes.a11y, byId), "text/csv")} disabled={!issues.length}>
          Export CSV
        </button>
      </div>

      {done < total && (
        <div className="panel panel-pad small" role="status" style={{ marginBottom: 16 }}>
          Checking screens… {done} of {total}
          <div className="stack" style={{ marginTop: 8 }}>
            <div style={{ width: `${(100 * done) / Math.max(1, total)}%`, background: "var(--accent)" }} />
          </div>
        </div>
      )}

      <div className="stats">
        <Stat value={<span style={{ color: SEVERITY_COLOR.error }}>{count((i) => i.severity === "error")}</span>} label="errors" />
        <Stat value={<span style={{ color: SEVERITY_COLOR.warning }}>{count((i) => i.severity === "warning")}</span>} label="warnings" />
        <Stat value={count((i) => i.severity === "info")} label="suggestions" />
        <Stat value={`${reviewed}/${issues.length}`} label="reviewed" />
        <Stat value={count((i) => st(i) === "confirmed")} label="need fix" />
        <Stat value={count((i) => st(i) === "false_positive")} label="false positives" />
      </div>

      <div className="section">
        <h3>Rules</h3>
        <div className="rule-grid">
          {ruleCounts.map(([r, n]) => (
            <button
              key={r}
              className={`panel rule-card ${f.rule === r ? "on" : ""}`}
              onClick={() => setF((p) => ({ ...p, rule: p.rule === r ? null : r }))}
              aria-pressed={f.rule === r}
            >
              <span className="row" style={{ gap: 6 }}>
                <i className="dot" style={{ background: SEVERITY_COLOR[RULES[r].severity] }} aria-hidden />
                <b className="grow">{RULES[r].title}</b>
                <span className="mono">{n}</span>
              </span>
              <span className="small muted">{RULES[r].why}</span>
              <span className="small">
                <b>Fix:</b> {RULES[r].fix}
              </span>
            </button>
          ))}
          {done === total && !issues.length && <div className="panel panel-pad muted">No issues found on {total} screens.</div>}
        </div>
      </div>

      <div className="row wrap section" style={{ gap: 8 }}>
        {SEVERITIES.map((s) => (
          <button
            key={s}
            className={`chip ${f.severities.includes(s) ? "on" : ""}`}
            aria-pressed={f.severities.includes(s)}
            onClick={() =>
              setF((p) => ({ ...p, severities: p.severities.includes(s) ? p.severities.filter((x) => x !== s) : [...p.severities, s] }))
            }
          >
            <i className="dot" style={{ background: SEVERITY_COLOR[s] }} aria-hidden /> {s}
          </button>
        ))}
        <label className="check" style={{ marginLeft: 8 }}>
          Show
          <select value={f.status} onChange={(e) => setF((p) => ({ ...p, status: e.target.value as StatusFilter }))}>
            <option value="all">All except false positives</option>
            <option value="unreviewed">Not reviewed</option>
            {(Object.keys(TRIAGE_LABEL) as TriageStatus[])
              .filter((s) => s !== "open")
              .map((s) => (
                <option key={s} value={s}>
                  {TRIAGE_LABEL[s]}
                </option>
              ))}
          </select>
        </label>
        {f.rule && (
          <button className="chip on" onClick={() => setF((p) => ({ ...p, rule: null }))}>
            {RULES[f.rule].title} ✕
          </button>
        )}
        <div className="grow" />
        <span className="small faint" aria-live="polite">
          {notesStatus(notes.mode, notes.saving, run)}
        </span>
      </div>

      <div className="col section" style={{ gap: 16, marginTop: 12 }}>
        {[...groups.entries()].map(([sid, list]) => {
          const s = byId.get(sid);
          return (
            <div key={sid} className="panel">
              <div className="row" style={{ padding: 12, gap: 12, borderBottom: "1px solid var(--border)" }}>
                <Thumb run={run} screen={s} className="a11y-thumb" />
                <div className="grow">
                  <a href={screenHref(run, sid)} onClick={openOnA11yTab}>
                    <span className="sid">{sid}</span> <b>{s?.title}</b>
                  </a>
                  <div className="small muted">{list.length} finding(s)</div>
                </div>
                <a className="btn" href={screenHref(run, sid)} onClick={openOnA11yTab}>
                  Open with overlays →
                </a>
              </div>
              <A11yIssueTable issues={list} triage={notes.a11y} onTriage={notes.triage} />
            </div>
          );
        })}
        {issues.length > 0 && groups.size === 0 && <div className="panel empty">Nothing matches these filters.</div>}
      </div>

      <p className="small faint section">
        Touch-target sizes use {density.scale.toFixed(2)} px per dp
        {density.exact ? " (from the device's density)." : " — estimated from screen width; the run doesn't record the device density."}{" "}
        Contrast is estimated from screenshot pixels, and text size isn't known, so 3–4.5:1 is flagged as a warning. Automated checks
        catch only part of what matters; also try the app with TalkBack. <a href={href("how")}>How AppScreenMap works</a>
      </p>
    </div>
  );
}

// Opening a screen from here should land on its Accessibility tab.
const openOnA11yTab = () => write(keys.detailPrefs, { ...read<Record<string, unknown>>(keys.detailPrefs, {}), tab: "a11y" });

function download(name: string, text: string, type: string) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  Object.assign(document.createElement("a"), { href: url, download: name }).click();
  URL.revokeObjectURL(url);
}

function toMarkdown(map: AppMapData, issues: A11yIssue[], triage: RunTriage, byId: Map<string, Screen>): string {
  const app = map.run.app;
  const live = issues.filter((i) => statusOf(triage, i) !== "false_positive");
  const lines = [
    `# Accessibility review — ${app.label ?? app.package} ${app.version ?? ""}`.trim(),
    "",
    `Run \`${map.run.id}\` · ${live.length} findings (${issues.length - live.length} marked false positive) · generated by AppScreenMap`,
    "",
  ];
  const bySid = new Map<string, A11yIssue[]>();
  for (const i of live) bySid.set(i.screen, [...(bySid.get(i.screen) ?? []), i]);
  for (const [sid, list] of bySid) {
    lines.push(`## ${sid} · ${byId.get(sid)?.title ?? ""}`, "", "| Severity | Issue | Element | Detail | Review | Note |", "|---|---|---|---|---|---|");
    for (const i of list) {
      const t = triage[i.key];
      const cell = (s: string) => s.replace(/\|/g, "\\|").replace(/\n/g, " ");
      lines.push(
        `| ${i.severity} | ${RULES[i.rule].title} | ${cell(i.label)}${i.rid ? ` \`${i.rid.replace(/^.*?:id\//, "id/")}\`` : ""} | ${cell(i.detail)} | ${TRIAGE_LABEL[t?.status ?? "open"]} | ${cell(t?.note ?? "")} |`,
      );
    }
    lines.push("");
  }
  return lines.join("\n");
}

function toCsv(issues: A11yIssue[], triage: RunTriage, byId: Map<string, Screen>): string {
  const q = (s: string) => `"${s.replace(/"/g, '""')}"`;
  const rows = [["screen", "screen_title", "severity", "rule", "element", "resource_id", "detail", "review", "note", "bounds"].join(",")];
  for (const i of issues) {
    const t = triage[i.key];
    rows.push(
      [i.screen, byId.get(i.screen)?.title ?? "", i.severity, i.rule, i.label, i.rid, i.detail, t?.status ?? "open", t?.note ?? "", i.bounds.join(" ")]
        .map((v) => q(String(v)))
        .join(","),
    );
  }
  return rows.join("\n") + "\n";
}

/** The crawler's WCAG report (`appscreenmap a11y <run> --report`), if this run has one. */
function useReportUrl(run: string): string | null {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    const u = runFile(run, "a11y-report.html");
    let alive = true;
    fetch(u, { method: "HEAD", cache: "no-store" })
      .then((r) => alive && setUrl(r.ok ? u : null))
      .catch(() => alive && setUrl(null));
    return () => {
      alive = false;
    };
  }, [run]);
  return url;
}

function A11yNav({ run, view }: { run: string; view: "findings" | "report" }) {
  return (
    <nav className="seg a11y-nav" aria-label="Accessibility views">
      <a className={view === "findings" ? "on" : ""} aria-current={view === "findings" ? "page" : undefined} href={href("r", run, "a11y")}>
        Findings and triage
      </a>
      <a className={view === "report" ? "on" : ""} aria-current={view === "report" ? "page" : undefined} href={href("r", run, "a11y", "report")}>
        WCAG 2.2 report
      </a>
    </nav>
  );
}

/**
 * The crawler's self-contained WCAG report, shown inside the viewer. It's generated HTML containing text from the
 * app under test, so it renders in a sandboxed frame with scripts off. A <base target="_blank"> makes its many
 * links to w3.org open in a new tab instead of replacing the report.
 */
function ReportView({ run, url }: { run: string; url: string }) {
  const { data: html, error } = useText(url);
  const doc = useMemo(
    () => (html ? html.replace(/<head[^>]*>/i, (m) => `${m}<base target="_blank">`) : ""),
    [html],
  );
  const file = `${run.replace(/\//g, "_")}-a11y-report.html`;
  return (
    <div className="report-view">
      <div className="row wrap report-bar">
        <A11yNav run={run} view="report" />
        <div className="grow" />
        <a className="btn" href={url} target="_blank" rel="noreferrer" title="Open the standalone file in a new tab">
          Open in new tab
        </a>
        <a className="btn primary" href={url} download={file}>
          <Icon name="file" size={14} /> Download HTML
        </a>
      </div>
      {error ? (
        <div className="error">Couldn't load the report: {error}</div>
      ) : !html ? (
        <div className="empty">Loading report…</div>
      ) : (
        <iframe
          className="report-frame"
          title="WCAG 2.2 accessibility report"
          srcDoc={doc}
          sandbox="allow-popups allow-popups-to-escape-sandbox"
        />
      )}
    </div>
  );
}
