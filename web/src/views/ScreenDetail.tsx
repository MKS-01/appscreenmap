import { useMemo, useState } from "react";
import { runFile, useText } from "../api";
import { CopyButton, ScreenLink, Thumb } from "../components/common";
import { go, href, screenHref } from "../router";
import type { AppMapData, Screen, UIElement } from "../types";
import { RULES, SEVERITY_COLOR, useA11y, type Severity } from "../a11y";
import A11yIssueTable from "../components/A11yIssueTable";
import { notesStatus, useNotes } from "../notes";
import { keys, useStored } from "../storage";
import { STATUS_HELP, STATUSES, screenMap, shortActivity, statusColor } from "../util";

const SEVERITIES: Severity[] = ["error", "warning", "info"];

type Tab = "elements" | "a11y" | "transitions" | "path" | "maestro" | "xml";

export default function ScreenDetail({ run, map, sid }: { run: string; map: AppMapData; sid: string }) {
  const byId = useMemo(() => screenMap(map), [map]);
  const screen = byId.get(sid);
  const [prefs, setPrefs] = useStored(keys.detailPrefs, { tab: "elements" as Tab, belowFold: false });
  const setTab = (tab: Tab) => setPrefs((p) => ({ ...p, tab }));
  const setBelowFold = (belowFold: boolean) => setPrefs((p) => ({ ...p, belowFold }));
  const [hover, setHover] = useState<string | null>(null);
  const notes = useNotes(run);
  const a11y = useA11y(run, map, sid);

  if (!screen) return <div className="page empty">Screen {sid} isn't in this run.</div>;

  const appScreens = map.screens.filter((s) => s.kind === "app");
  const idx = appScreens.findIndex((s) => s.id === screen.id);
  const prev = appScreens[idx - 1];
  const next = appScreens[idx + 1];
  const into = map.transitions.filter((t) => t.to === screen.id);
  const out = map.transitions.filter((t) => t.from === screen.id);

  const note = notes.notes[screen.id];
  const { belowFold } = prefs;
  const tabs: [Tab, string][] = [
    ["elements", `Elements (${screen.elements.length})`],
    ...(screen.kind === "app"
      ? ([["a11y", `Accessibility (${a11y.done < a11y.total ? "…" : a11y.issues.length})`]] as [Tab, string][])
      : []),
    ["transitions", `Transitions (${into.length + out.length})`],
    ["path", "Path from launch"],
    ...(screen.kind === "app" ? ([["maestro", "Maestro flow"]] as [Tab, string][]) : []),
    ...(screen.hierarchy ? ([["xml", "Hierarchy XML"]] as [Tab, string][]) : []),
  ];
  const tab: Tab = tabs.some(([id]) => id === prefs.tab) ? prefs.tab : "elements";

  const elementBoxes: Box[] = screen.elements
    .filter((e) => e.bounds[2] > e.bounds[0] && e.bounds[3] > e.bounds[1] && (belowFold || e.scroll_depth === 0))
    .map((e) => {
      const target = e.target && e.target !== screen.id ? byId.get(e.target) : undefined;
      return {
        key: e.id,
        bounds: e.bounds,
        color: statusColor(e.status),
        label: target ? `${e.label} → ${target.title}` : e.label,
        tip: `${e.label} · ${e.kind} · ${e.status}${target ? ` → ${target.title}` : ""}`,
        dashed: e.scroll_depth > 0,
        onActivate: target ? () => go(screenHref(run, target.id)) : undefined,
      };
    });
  const issueBoxes: Box[] = a11y.issues
    .filter((i) => (notes.a11y[i.key] as { status?: string } | undefined)?.status !== "false_positive")
    .map((i) => ({
      key: i.key,
      bounds: i.bounds,
      color: SEVERITY_COLOR[i.severity],
      label: `${RULES[i.rule].title}: ${i.label}`,
      tip: `${i.severity} · ${RULES[i.rule].title} · ${i.label} · ${i.detail}`,
    }));

  return (
    <div className="page">
      <div className="row wrap detail-head" style={{ marginBottom: 20, gap: 12 }}>
        <div className="grow">
          <div className="row" style={{ gap: 10 }}>
            <span className="sid" style={{ fontSize: 13 }}>
              {screen.id}
            </span>
            <h1>{screen.title}</h1>
            {screen.kind === "app" && (
              <button
                className={`star-btn ${note?.star ? "on" : ""}`}
                onClick={() => notes.update(screen.id, { star: !note?.star })}
                aria-pressed={!!note?.star}
                aria-label={note?.star ? "Unstar screen" : "Star screen"}
                title={note?.star ? "Unstar" : "Star this screen"}
              >
                {note?.star ? "★" : "☆"}
              </button>
            )}
          </div>
          <div className="row wrap small muted" style={{ gap: 12, marginTop: 4 }}>
            <span title={screen.activity ?? ""}>{shortActivity(screen.activity)}</span>
            <span>depth {screen.depth}</span>
            <span>visited {screen.visits}×</span>
            <span>found at step {screen.first_step}</span>
            {screen.patterns.map((p) => (
              <span key={p} className="chip">
                {p}
              </span>
            ))}
          </div>
        </div>
        <a className="btn" href={href("r", run, "map") + `?focus=${encodeURIComponent(screen.id)}`}>
          Show on map
        </a>
        <button className="btn" disabled={!prev} onClick={() => prev && go(screenHref(run, prev.id))}>
          ← Prev
        </button>
        <button className="btn" disabled={!next} onClick={() => next && go(screenHref(run, next.id))}>
          Next →
        </button>
      </div>

      <div className="detail">
        <div className="shot-wrap col" style={{ gap: 10 }}>
          <Shot run={run} screen={screen} boxes={tab === "a11y" ? issueBoxes : elementBoxes} hover={hover} setHover={setHover} />
          {tab === "a11y" ? (
            <div className="legend">
              {SEVERITIES.filter((sv) => a11y.issues.some((i) => i.severity === sv)).map((sv) => (
                <span key={sv}>
                  <i className="dot" style={{ background: SEVERITY_COLOR[sv] }} /> {sv}
                </span>
              ))}
              {a11y.done < a11y.total && <span>checking…</span>}
            </div>
          ) : (
            <div className="legend">
              {STATUSES.filter((st) => screen.elements.some((e) => e.status === st)).map((st) => (
                <span key={st} title={STATUS_HELP[st]}>
                  <i className="dot" style={{ background: statusColor(st) }} /> {st}
                </span>
              ))}
            </div>
          )}
          {tab !== "a11y" && screen.elements.some((e) => e.scroll_depth > 0) && (
            <label className="check">
              <input type="checkbox" checked={belowFold} onChange={(e) => setBelowFold(e.target.checked)} /> Show elements found
              after scrolling
            </label>
          )}
          <div className="small faint">
            {tab === "a11y" ? "Boxes mark each finding; hover one to find it in the list." : "Click a box to jump to the screen it leads to."}
          </div>
          {screen.kind === "app" && (
            <div className="panel panel-pad col" style={{ gap: 6, marginTop: 6 }}>
              <label htmlFor="screen-note">
                <h3>Notes</h3>
              </label>
              <textarea
                id="screen-note"
                className="note-input"
                rows={4}
                placeholder="Anything worth remembering about this screen…"
                value={note?.note ?? ""}
                onChange={(e) => notes.update(screen.id, { note: e.target.value })}
                disabled={notes.mode === "loading"}
              />
              <span className="small faint" aria-live="polite">
                {notesStatus(notes.mode, notes.saving, run)}
              </span>
            </div>
          )}
        </div>

        <div className="panel" style={{ minWidth: 0 }}>
          <nav className="tabs" style={{ padding: "0 8px", borderRadius: "10px 10px 0 0" }}>
            {tabs.map(([id, label]) => (
              <a
                key={id}
                href="#"
                className={`tab ${tab === id ? "active" : ""}`}
                onClick={(e) => {
                  e.preventDefault();
                  setTab(id);
                }}
              >
                {label}
              </a>
            ))}
          </nav>
          <div style={{ padding: ["elements", "transitions", "a11y"].includes(tab) ? 0 : 16, overflow: "auto" }}>
            {tab === "elements" && <ElementTable run={run} screen={screen} byId={byId} hover={hover} setHover={setHover} />}
            {tab === "a11y" &&
              (a11y.done < a11y.total ? (
                <div className="empty">Checking this screen…</div>
              ) : (
                <A11yIssueTable issues={a11y.issues} triage={notes.a11y} onTriage={notes.triage} hover={hover} setHover={setHover} />
              ))}
            {tab === "transitions" && (
              <div className="col" style={{ gap: 0 }}>
                <TransitionTable title="Leads to" run={run} rows={out.map((t) => ({ ...t, other: byId.get(t.to) }))} />
                <TransitionTable title="Reached from" run={run} rows={into.map((t) => ({ ...t, other: byId.get(t.from) }))} />
              </div>
            )}
            {tab === "path" && <PathView run={run} screen={screen} byId={byId} />}
            {tab === "maestro" && <MaestroView run={run} screen={screen} />}
            {tab === "xml" && screen.hierarchy && <XmlView url={runFile(run, screen.hierarchy)} />}
          </div>
        </div>
      </div>
    </div>
  );
}

interface Box {
  key: string;
  bounds: [number, number, number, number];
  color: string;
  label: string;
  tip: string;
  dashed?: boolean;
  onActivate?: () => void;
}

function Shot({
  run,
  screen,
  boxes,
  hover,
  setHover,
}: {
  run: string;
  screen: Screen;
  boxes: Box[];
  hover: string | null;
  setHover: (id: string | null) => void;
}) {
  const W = screen.width || 1080;
  const H = screen.height || 2400;
  return (
    <div className="shot" style={{ "--ar": W / H } as React.CSSProperties}>
      {screen.screenshot ? <img src={runFile(run, screen.screenshot)} alt={screen.title} /> : <div style={{ aspectRatio: `${W}/${H}` }} />}
      {boxes.map((b) => {
        const [x1, y1, x2, y2] = b.bounds;
        return (
          <div
            key={b.key}
            className={`ov ${hover === b.key ? "hl" : ""}`}
            style={
              {
                "--c": b.color,
                left: `${(100 * x1) / W}%`,
                top: `${(100 * y1) / H}%`,
                width: `${(100 * (x2 - x1)) / W}%`,
                height: `${(100 * (y2 - y1)) / H}%`,
                borderStyle: b.dashed ? "dashed" : "solid",
                cursor: b.onActivate ? "pointer" : "default",
              } as React.CSSProperties
            }
            role={b.onActivate ? "button" : undefined}
            tabIndex={b.onActivate ? 0 : undefined}
            aria-label={b.tip}
            onMouseEnter={() => setHover(b.key)}
            onMouseLeave={() => setHover(null)}
            onFocus={() => setHover(b.key)}
            onBlur={() => setHover(null)}
            onClick={b.onActivate}
            onKeyDown={(e) => {
              if (b.onActivate && (e.key === "Enter" || e.key === " ")) {
                e.preventDefault();
                b.onActivate();
              }
            }}
            title={b.tip}
          >
            {hover === b.key && <span className="ov-tip">{b.label}</span>}
          </div>
        );
      })}
    </div>
  );
}

function ElementTable({
  run,
  screen,
  byId,
  hover,
  setHover,
}: {
  run: string;
  screen: Screen;
  byId: Map<string, Screen>;
  hover: string | null;
  setHover: (id: string | null) => void;
}) {
  if (!screen.elements.length) return <div className="empty">No actionable elements on this screen.</div>;
  return (
    <table className="tbl">
      <thead>
        <tr>
          <th>Element</th>
          <th>Kind</th>
          <th>Status</th>
          <th>Result</th>
        </tr>
      </thead>
      <tbody>
        {screen.elements.map((e) => (
          <tr key={e.id} className={`hover ${hover === e.id ? "sel" : ""}`} onMouseEnter={() => setHover(e.id)} onMouseLeave={() => setHover(null)}>
            <td style={{ maxWidth: 280 }}>
              <div className="ellipsis" title={e.label}>
                {e.label || <span className="faint">(no label)</span>}
              </div>
              <div className="mono faint ellipsis" style={{ fontSize: 11 }} title={selectorText(e)}>
                {selectorText(e)}
              </div>
            </td>
            <td className="muted">
              {e.kind}
              {e.scroll_depth > 0 && <div className="small faint">after {e.scroll_depth} scroll(s)</div>}
            </td>
            <td title={e.note ?? STATUS_HELP[e.status]}>
              <span className="row" style={{ gap: 6 }}>
                <i className="dot" style={{ background: statusColor(e.status) }} />
                {e.status}
              </span>
              {e.note && <div className="small faint">{e.note}</div>}
            </td>
            <td>
              {e.effect && <span className={`effect ${e.effect}`}>{e.effect.replace("_", " ")}</span>}
              {e.target && e.target !== screen.id && (
                <div className="small" style={{ marginTop: 2 }}>
                  → <ScreenLink run={run} screen={byId.get(e.target)} />
                </div>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

const selectorText = (e: UIElement) => (e.rid ? e.rid.replace(/^.*?:id\//, "id/") : e.text ? `text "${e.text}"` : e.desc ? `desc "${e.desc}"` : e.class.replace(/^.*\./, ""));

function TransitionTable({ title, run, rows }: { title: string; run: string; rows: { id: string; label: string; kind: string; count: number; step: number; other?: Screen }[] }) {
  return (
    <div>
      <h3 style={{ padding: "14px 12px 6px" }}>
        {title} ({rows.length})
      </h3>
      {rows.length === 0 ? (
        <div className="small muted" style={{ padding: "0 12px 12px" }}>
          none
        </div>
      ) : (
        <table className="tbl">
          <thead>
            <tr>
              <th>Action</th>
              <th>Screen</th>
              <th>Times</th>
              <th>First at step</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((t) => (
              <tr key={t.id}>
                <td>
                  {t.label} <span className="faint small">({t.kind})</span>
                </td>
                <td>
                  <ScreenLink run={run} screen={t.other} />
                </td>
                <td>{t.count}</td>
                <td className="mono">{t.step}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function PathView({ run, screen, byId }: { run: string; screen: Screen; byId: Map<string, Screen> }) {
  if (!screen.reach_path.length)
    return <div className="muted">This is the launch screen — the app opens here, so there's no path to walk.</div>;
  return (
    <div className="col" style={{ gap: 16 }}>
      <div className="muted small">
        The shortest route the crawler knows from a fresh launch. It replays this route (after force-stopping the app) whenever it
        needs to come back here, and the Maestro flow follows the same steps.
      </div>
      <div className="path">
        {screen.reach_path.map((st, i) => {
          const s = byId.get(st.screen);
          const fills = s?.autofill ?? [];
          return (
            <span key={i} style={{ display: "contents" }}>
              <a className="path-node" href={s ? screenHref(run, s.id) : undefined}>
                <Thumb run={run} screen={s} />
                <span className="ellipsis" style={{ maxWidth: 92 }}>
                  {s?.title ?? st.screen}
                </span>
              </a>
              <span className="path-arrow">
                <span className="a">→</span>
                {fills.length > 0 && <span className="faint">fill {fills.length} field(s), then</span>}
                <span>
                  {st.action === "back" ? "press" : st.scroll_depth ? "scroll to & tap" : "tap"} <b>{st.label}</b>
                </span>
              </span>
            </span>
          );
        })}
        <span className="path-node cur">
          <Thumb run={run} screen={screen} />
          <b className="ellipsis" style={{ maxWidth: 92 }}>
            {screen.title}
          </b>
        </span>
      </div>
      {screen.autofill.length > 0 && (
        <div>
          <h3 style={{ marginBottom: 6 }}>Autofilled on arrival</h3>
          <table className="tbl">
            <tbody>
              {screen.autofill.map((f) => (
                <tr key={f.key}>
                  <td>{f.label}</td>
                  <td className="mono">{f.value}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function MaestroView({ run, screen }: { run: string; screen: Screen }) {
  const rel = `flows/${screen.id}.yaml`;
  const { data, error } = useText(runFile(run, rel));
  const cmd = `maestro test runs/${run}/${rel}`;
  if (error)
    return screen.origin === "unknown" ? (
      <div className="muted">
        No flow: the crawl never recorded a path to this screen, so there's no way to replay it from launch.
      </div>
    ) : (
      <div className="muted">
        No flow file yet. Run <code>appscreenmap export runs/{run}</code> to generate it.
      </div>
    );
  return (
    <div className="col" style={{ gap: 12 }}>
      <div className="muted small">
        A <a href="https://maestro.mobile.dev" target="_blank" rel="noreferrer">Maestro</a> flow that launches the app, walks the
        path above, and asserts it reached <b>{screen.title}</b>. Use it as a smoke test or as the starting point for a real test.
      </div>
      <div className="row">
        <code className="grow ellipsis" style={{ padding: "6px 10px", background: "var(--panel-2)", borderRadius: 6 }}>
          {cmd}
        </code>
        <CopyButton text={cmd} label="Copy command" />
        {data && <CopyButton text={data} label="Copy YAML" />}
      </div>
      <pre className="code">{data ?? "Loading…"}</pre>
    </div>
  );
}

function prettyXml(xml: string): string {
  let depth = 0;
  return xml
    .replace(/>\s*</g, ">\n<")
    .split("\n")
    .map((line) => {
      if (/^<\//.test(line)) depth = Math.max(0, depth - 1);
      const out = "  ".repeat(depth) + line;
      if (/^<[^!?/][^>]*[^/]>$/.test(line) && !/<\/[^>]+>$/.test(line)) depth++;
      return out;
    })
    .join("\n");
}

function XmlView({ url }: { url: string }) {
  const { data, error } = useText(url);
  const pretty = useMemo(() => (data ? prettyXml(data) : ""), [data]);
  if (error) return <div className="error">{error}</div>;
  return (
    <div className="col" style={{ gap: 10 }}>
      <div className="row">
        <span className="muted small grow">The raw uiautomator dump this screen was identified from.</span>
        <a className="btn" href={url} target="_blank" rel="noreferrer">
          Open raw
        </a>
      </div>
      <pre className="code" style={{ maxHeight: 640 }}>
        {data ? pretty : "Loading…"}
      </pre>
    </div>
  );
}
