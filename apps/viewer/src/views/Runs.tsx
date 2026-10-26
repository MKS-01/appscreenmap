import { useMemo, useState } from "react";
import { deleteRun, runFile, runKey, useIndex, useMap } from "../api";
import { CopyButton, ErrorBox, Loading, StatusBadge } from "../components/common";
import { Icon } from "../components/Icon";
import NewProject from "../components/NewProject";
import { href, screenHref } from "../router";
import { clearAll, usage } from "../storage";
import type { RunIndexRow } from "../types";
import { fmtDate, fmtDuration, plural, shotBox } from "../util";

const CRAWL_CMD = "appscreenmap crawl --apk app.apk";
const AGENT_PROMPT = "Map my app on the emulator and review the map";

interface AppGroup {
  key: string;
  latest: RunIndexRow;
  runs: RunIndexRow[];
}

/** "Android 17" / "iOS 27.0" for a run's device. */
const osLabel = (d: RunIndexRow["device"]) => (d.platform === "ios" ? `iOS ${d.os?.release ?? ""}`.trim() : `Android ${d.android ?? ""}`.trim());

export default function Runs() {
  const { data, error } = useIndex();
  const [gone, setGone] = useState<Set<string>>(new Set()); // deleted here; index.json catches up on its next read
  const [newOpen, setNewOpen] = useState(false);

  // One card per app (project folder, else package), newest run first.
  const apps = useMemo<AppGroup[]>(() => {
    const by = new Map<string, RunIndexRow[]>();
    for (const r of data?.runs ?? []) {
      if (gone.has(runKey(r))) continue;
      const k = r.project ?? r.app.package;
      by.set(k, [...(by.get(k) ?? []), r]);
    }
    return [...by.entries()]
      .map(([key, runs]) => {
        const sorted = [...runs].sort((a, b) => (b.started_at ?? "").localeCompare(a.started_at ?? ""));
        return { key, latest: sorted[0], runs: sorted };
      })
      .sort((a, b) => (b.latest.started_at ?? "").localeCompare(a.latest.started_at ?? ""));
  }, [data, gone]);

  if (error) return <div className="page"><ErrorBox error={error} /></div>;
  if (!data) return <Loading />;

  const runs = data.runs.filter((r) => !gone.has(runKey(r)));
  const total = (f: (r: RunIndexRow) => number) => runs.reduce((n, r) => n + (f(r) || 0), 0);
  const live = runs.filter((r) => r.status === "running").length;

  return (
    <div className="home">
      <section className="hero">
        <div className="hero-inner">
          <div className="hero-copy">
            {live > 0 && (
              <span className="badge running" style={{ alignSelf: "flex-start" }}>
                <span className="dot" /> {plural(live, "crawl")} running
              </span>
            )}
            <h1 className="hero-title">Every screen of your app, mapped.</h1>
            <p className="hero-sub">
              Your AI agent does the crawling. Ask it to map an app: it runs the crawler on an emulator, checks the result, tunes and
              re-crawls when something looks off, and leaves you a browsable map, test flows, visual diffs and an accessibility
              review.
            </p>
            <div className="row wrap" style={{ gap: 10 }}>
              <span className="hero-prompt">
                <Icon name="bot" size={15} />
                <span>{AGENT_PROMPT}</span>
              </span>
              <CopyButton text={AGENT_PROMPT} />
              <button className="btn primary" onClick={() => setNewOpen(true)} aria-expanded={newOpen}>
                <Icon name="plus" size={14} /> New project
              </button>
              <a className="btn" href="#/how">
                How it works →
              </a>
            </div>
            <div className="small muted">
              Prefer the terminal? <code>{CRAWL_CMD}</code>
            </div>
          </div>
          {runs.length > 0 && (
            <dl className="hero-stats">
              <HeroStat v={apps.length} l={apps.length === 1 ? "app" : "apps"} />
              <HeroStat v={runs.length} l={runs.length === 1 ? "run" : "runs"} />
              <HeroStat v={total((r) => r.screens)} l="screens mapped" />
              <HeroStat v={total((r) => r.transitions)} l="transitions" />
              <HeroStat v={total((r) => r.crashes)} l="crashes found" warn={total((r) => r.crashes) > 0} />
            </dl>
          )}
        </div>
      </section>

      <div className="page" style={{ paddingTop: 28 }}>
        {newOpen && <NewProject onClose={() => setNewOpen(false)} />}
        {runs.length === 0 ? (
          <GettingStarted big />
        ) : (
          <>
            <div className="row" style={{ marginBottom: 14 }}>
              <h2 className="grow">Your apps</h2>
              <span className="small muted">{plural(apps.length, "app")} · newest first</span>
            </div>
            <div className="col" style={{ gap: 18 }}>
              {apps.map((a) => (
                <AppCard key={a.key} group={a} onDeleted={(k) => setGone((g) => new Set([...g, k]))} />
              ))}
            </div>
            <GettingStarted />
          </>
        )}
        <StorageInfo />
      </div>
    </div>
  );
}

function HeroStat({ v, l, warn }: { v: number; l: string; warn?: boolean }) {
  return (
    <div className="hero-stat">
      <dt>{l}</dt>
      <dd style={warn ? { color: "var(--st-blocked)" } : undefined}>{v.toLocaleString()}</dd>
    </div>
  );
}

const LINKS: [string, string][] = [
  ["map", "Map"],
  ["screens", "Screens"],
  ["replay", "Crawl replay"],
  ["insights", "Insights"],
  ["a11y", "Accessibility"],
  ["compare", "Compare"],
];

function AppCard({ group, onDeleted }: { group: AppGroup; onDeleted: (key: string) => void }) {
  const r = group.latest;
  const key = runKey(r);
  const { data: map } = useMap(key);
  const shots = (map?.screens ?? []).filter((s) => s.kind === "app" && s.thumb).slice(0, 8);
  const coverage = map?.stats.activity_coverage;

  return (
    <article className="panel app-card">
      <div className="app-head">
        <div className="app-icon" aria-hidden>
          {(r.app.label ?? r.app.package).slice(0, 1).toUpperCase()}
        </div>
        <div className="grow" style={{ minWidth: 0 }}>
          <div className="row wrap" style={{ gap: 8 }}>
            <h2>
              <a className="app-name" href={href("r", key, "map")}>
                {r.app.label ?? r.app.package}
              </a>
            </h2>
            {r.app.version && <span className="chip">v{r.app.version}</span>}
            <StatusBadge status={r.status} />
            {r.stack?.summary && (
              <a className="chip stack-chip" href={href("r", key, "insights", "stack")} title="App stack">
                <Icon name="cpu" size={12} /> <span className="ellipsis">{r.stack.summary}</span>
              </a>
            )}
          </div>
          <div className="small muted ellipsis">
            <span className="mono">{r.app.package}</span> · {r.device.model ?? r.device.serial} · {osLabel(r.device)} ·{" "}
            <span title={fmtDate(r.started_at)}>{timeAgo(r.started_at)}</span>
          </div>
        </div>
        <a className="btn" href={href("r", key, "map")}>
          Open map →
        </a>
      </div>

      <div className="filmstrip" aria-label="Screens in the latest run">
        {shots.length > 0
          ? shots.map((s) => (
              <a key={s.id} className="film" href={screenHref(key, s.id)} title={`${s.id} · ${s.title}`} style={{ width: shotBox(s, 19000).w }}>
                <img src={runFile(key, s.thumb!)} alt={s.title} loading="lazy" style={{ aspectRatio: `${s.width || 1080} / ${s.height || 2400}` }} />
                <span className="ellipsis">{s.title}</span>
              </a>
            ))
          : r.thumb && (
              <span className="film">
                <img src={`/runs/${r.thumb}`} alt="" />
              </span>
            )}
        {map && map.stats.screens === 0 && r.status !== "running" && (
          <span className="film-empty small muted">
            No screens yet. Ask your agent to map {r.app.label ?? "the app"} on the emulator: the crawl lands on this canvas.
          </span>
        )}
        {map && map.stats.screens > shots.length && (
          <a className="film more" href={href("r", key, "screens")}>
            +{map.stats.screens - shots.length}
            <span>more</span>
          </a>
        )}
      </div>

      <div className="app-foot">
        <div className="app-metrics">
          {r.screens === 0 && !r.steps ? (
            <span className="small muted">Scanned, not crawled yet</span>
          ) : (
            <>
              <Metric v={r.screens} l="screens" />
              <Metric v={r.transitions} l="transitions" />
              <Metric v={r.crashes} l="crashes" warn={r.crashes > 0} />
              <Metric v={r.steps ?? 0} l="steps" />
              <Metric v={fmtDuration(r.elapsed_s)} l="crawl time" />
              {coverage != null && <Metric v={`${Math.round(coverage * 100)}%`} l="activity coverage" />}
            </>
          )}
        </div>
        <nav className="app-links" aria-label={`${r.app.label ?? r.app.package} views`}>
          {LINKS.map(([tab, label]) => (
            <a key={tab} href={href("r", key, tab)}>
              {label}
            </a>
          ))}
        </nav>
      </div>

      {group.runs.length > 1 && (
        <details className="history">
          <summary>
            {plural(group.runs.length - 1, "earlier run")}
          </summary>
          <div className="tbl-scroll">
            <table className="tbl history-tbl">
              <tbody>
                {group.runs.slice(1).map((o) => (
                  <EarlierRun key={runKey(o)} run={o} latest={key} onDeleted={onDeleted} />
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}
    </article>
  );
}

/** One earlier run: when, what it found, the diff command against the latest (truncated, copyable) and delete. */
function EarlierRun({ run: o, latest, onDeleted }: { run: RunIndexRow; latest: string; onDeleted: (key: string) => void }) {
  const k = runKey(o);
  const cmd = `appscreenmap diff runs/${k} runs/${latest}`;
  const [busy, setBusy] = useState(false);
  const remove = async () => {
    const when = o.started_at ? fmtDate(o.started_at) : o.id;
    if (!confirm(`Delete the run from ${when}?\n\nruns/${k} is removed from disk: map, screenshots, notes and comments. This can't be undone.`)) return;
    setBusy(true);
    try {
      await deleteRun(k);
      onDeleted(k);
    } catch (e) {
      alert(`Couldn't delete runs/${k}: ${e instanceof Error ? e.message : e}`);
      setBusy(false);
    }
  };
  return (
    <tr className="hover">
      <td className="history-when">
        <a href={href("r", k, "map")}>{o.started_at ? fmtDate(o.started_at) : "Undated run"}</a>
        <span className="mono faint ellipsis" title={`runs/${k}`}>
          {o.id}
        </span>
      </td>
      <td className="muted history-ver">v{o.app.version ?? "?"}</td>
      <td className="muted history-stats">
        {o.screens} screens · {o.transitions} transitions
        {o.crashes > 0 && <span style={{ color: "var(--st-blocked)" }}> · {plural(o.crashes, "crash")}</span>}
      </td>
      <td className="history-status">
        <StatusBadge status={o.status || "unknown"} />
      </td>
      <td className="history-cmd">
        <div className="row" style={{ gap: 6 }}>
          <code className="mono faint ellipsis grow" title={cmd}>
            {cmd}
          </code>
          <CopyButton text={cmd} label="Copy the diff command" iconOnly />
          <button
            className="btn icon-only btn-delete"
            onClick={remove}
            disabled={busy || o.status === "running"}
            aria-label={`Delete run ${o.id}`}
            title={o.status === "running" ? "Still running" : "Delete this run"}
          >
            <Icon name="trash" size={14} />
          </button>
        </div>
      </td>
    </tr>
  );
}

function Metric({ v, l, warn }: { v: React.ReactNode; l: string; warn?: boolean }) {
  return (
    <div className="metric">
      <b style={warn ? { color: "var(--st-blocked)" } : undefined}>{v}</b>
      <span>{l}</span>
    </div>
  );
}

// [title, description, what to copy, is it a prompt for the agent?]
const STEPS: [string, string, string, boolean][] = [
  ["Ask your agent", "In Claude Code, ask it to map the app. It checks the setup, crawls on the emulator and reviews the map.", "Map my app on the emulator and review the map", true],
  ["Watch it live", "Open the viewer. The map grows while the crawl runs.", "appscreenmap serve", false],
  ["Iterate", "Ask it to fix what looks wrong, audit accessibility, or compare a new build.", "Audit accessibility on the latest run at WCAG 2.2 AA", true],
];

function GettingStarted({ big }: { big?: boolean }) {
  return (
    <section className={`section ${big ? "" : "compact-start"}`}>
      <h3 style={{ marginBottom: 10 }}>{big ? "Map your first app" : "Map another app"}</h3>
      <div className="start-grid">
        {STEPS.map(([t, d, cmd, prompt], i) => (
          <div key={t} className="panel start-step">
            <span className="start-n">{i + 1}</span>
            <b>{t}</b>
            <span className="small muted">{d}</span>
            <div className="row" style={{ gap: 6, marginTop: "auto" }}>
              <code className={`grow ellipsis start-cmd ${prompt ? "is-prompt" : ""}`} title={prompt ? "Prompt for your agent" : "Terminal command"}>
                {prompt && <Icon name="bot" size={13} />} {cmd}
              </code>
              <CopyButton text={cmd} />
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function StorageInfo() {
  const [bytes, setBytes] = useState(usage);
  return (
    <div className="storage-note small muted section">
      <span className="grow">
        Crawl data, stars, notes and review decisions are files in each run folder. View preferences and map layouts stay in this
        browser ({(bytes / 1024).toFixed(1)} KB).
      </span>
      <button
        className="btn"
        disabled={bytes === 0}
        onClick={() => {
          if (!confirm("Reset view preferences and map layouts in this browser? Notes saved to disk are kept.")) return;
          clearAll();
          setBytes(usage());
        }}
      >
        Reset browser preferences
      </button>
    </div>
  );
}

function timeAgo(iso: string | null | undefined): string {
  if (!iso) return "—";
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  if (s < 86400 * 30) return `${Math.floor(s / 86400)} d ago`;
  return fmtDate(iso);
}
