import { runFile } from "../api";
import { ScreenLink, Stat } from "../components/common";
import type { AppMapData } from "../types";
import { STATUS_HELP, STATUSES, fmtDuration, screenMap, shortActivity, statusColor } from "../util";

export default function Insights({ run, map }: { run: string; map: AppMapData }) {
  const byId = screenMap(map);
  const app = map.screens.filter((s) => s.kind === "app");
  const st = map.stats;
  const totalEls = Object.values(st.elements).reduce((a, b) => a + (b ?? 0), 0);
  const pending = st.elements.pending ?? 0;

  // Dead ends: the only way out is back. Hubs: reachable from many screens.
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
  const hubs = [...app].sort((a, b) => (inBy.get(b.id)?.size ?? 0) - (inBy.get(a.id)?.size ?? 0)).slice(0, 5);
  const blocked = app.flatMap((s) => s.elements.filter((e) => e.status === "blocked").map((e) => ({ s, e })));
  const unexplored = app
    .map((s) => ({ s, n: s.elements.filter((e) => e.status === "pending").length }))
    .filter((x) => x.n > 0)
    .sort((a, b) => b.n - a.n);
  const problems = app.flatMap((s) => s.elements.filter((e) => e.status === "failed" || e.status === "unreachable").map((e) => ({ s, e })));

  const depthHist = new Map<number, number>();
  for (const s of app) depthHist.set(s.depth, (depthHist.get(s.depth) ?? 0) + 1);
  const maxDepthCount = Math.max(1, ...depthHist.values());

  const declared = map.run.app.activities ?? [];
  const visited = new Set(st.activities_visited);
  const crashes = map.events.filter((e) => e.type === "crash");
  const budgetHit = (map.run.steps ?? 0) >= Number(map.run.config.max_steps ?? Infinity);

  return (
    <div className="page">
      <h1 style={{ marginBottom: 16 }}>Insights</h1>
      <div className="stats">
        <Stat value={st.screens} label="screens" />
        <Stat value={st.transitions} label="transitions" />
        <Stat value={st.external} label="external apps" />
        <Stat value={st.max_depth} label="max depth" />
        <Stat value={map.run.steps ?? "—"} label="steps" />
        <Stat value={fmtDuration(map.run.elapsed_s)} label="crawl time" />
        <Stat
          value={<span style={{ color: crashes.length ? "var(--st-blocked)" : undefined }}>{crashes.length}</span>}
          label="crashes"
        />
        <Stat
          value={st.activity_coverage != null ? `${Math.round(st.activity_coverage * 100)}%` : "—"}
          label="activity coverage"
          title={st.activity_coverage == null ? "Needs aapt2 to read declared activities from the APK" : undefined}
        />
      </div>

      {pending > 0 && (
        <div className="panel panel-pad section" style={{ borderLeft: "3px solid var(--st-pending)" }}>
          <b>{pending} actions were found but never tried.</b>{" "}
          <span className="muted">
            {budgetHit
              ? `The crawl stopped at its ${map.run.config.max_steps}-step budget. Re-run with a higher --max-steps to go deeper.`
              : "The crawl ended before it could try them (time budget, or the screens became unreachable)."}
          </span>
        </div>
      )}

      <div className="section">
        <h3>Element outcomes</h3>
        <div className="panel panel-pad col" style={{ gap: 12 }}>
          <div className="stack">
            {STATUSES.filter((s) => st.elements[s]).map((s) => (
              <div key={s} style={{ width: `${(100 * (st.elements[s] ?? 0)) / Math.max(1, totalEls)}%`, background: statusColor(s) }} title={`${s}: ${st.elements[s]}`} />
            ))}
          </div>
          <div className="legend">
            {STATUSES.filter((s) => st.elements[s]).map((s) => (
              <span key={s} title={STATUS_HELP[s]}>
                <i className="dot" style={{ background: statusColor(s) }} /> {st.elements[s]} {s} <span className="faint">— {STATUS_HELP[s]}</span>
              </span>
            ))}
          </div>
        </div>
      </div>

      <div className="grid2 section">
        <div>
          <h3>Screens by depth (taps from launch)</h3>
          <div className="panel panel-pad col" style={{ gap: 8 }}>
            {[...depthHist.entries()]
              .sort((a, b) => a[0] - b[0])
              .map(([d, n]) => (
                <div key={d} className="hbar">
                  <span className="muted">depth {d}</span>
                  <div className="track">
                    <div className="fill" style={{ width: `${(100 * n) / maxDepthCount}%` }} />
                  </div>
                  <span className="mono">{n}</span>
                </div>
              ))}
          </div>
        </div>
        <div>
          <h3>Hubs (most entry points)</h3>
          <div className="panel">
            <table className="tbl">
              <tbody>
                {hubs.map((s) => (
                  <tr key={s.id}>
                    <td>
                      <ScreenLink run={run} screen={s} />
                    </td>
                    <td className="muted small">reached from {inBy.get(s.id)?.size ?? 0} screens</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div className="grid2 section">
        <List title="Dead ends (only way out is back)" empty="No dead ends.">
          {deadEnds.map((s) => (
            <tr key={s.id}>
              <td>
                <ScreenLink run={run} screen={s} />
              </td>
              <td className="muted small">{s.patterns.join(", ")}</td>
            </tr>
          ))}
        </List>
        <List title="Blocked actions (never tapped for safety)" empty="Nothing matched blocked_text.">
          {blocked.map(({ s, e }) => (
            <tr key={e.id}>
              <td>{e.label}</td>
              <td className="small">
                on <ScreenLink run={run} screen={s} />
              </td>
            </tr>
          ))}
        </List>
        <List title="Untried actions by screen" empty="Everything found was tried.">
          {unexplored.map(({ s, n }) => (
            <tr key={s.id}>
              <td>
                <ScreenLink run={run} screen={s} />
              </td>
              <td className="mono">{n}</td>
            </tr>
          ))}
        </List>
        <List title="Failed / unreachable" empty="None.">
          {problems.map(({ s, e }) => (
            <tr key={e.id}>
              <td>
                {e.label} <span className="faint small">({e.status})</span>
              </td>
              <td className="small">
                on <ScreenLink run={run} screen={s} />
              </td>
            </tr>
          ))}
        </List>
      </div>

      <div className="grid2 section">
        <List title={`Activities (${visited.size} visited${declared.length ? ` of ${declared.length} declared` : ""})`} empty="—">
          {(declared.length ? declared : [...visited]).map((a) => (
            <tr key={a}>
              <td className="mono small ellipsis" style={{ maxWidth: 360 }} title={a}>
                {shortActivity(a)}
              </td>
              <td>{visited.has(a) ? <span style={{ color: "var(--st-done)" }}>visited</span> : <span className="faint">not reached</span>}</td>
            </tr>
          ))}
        </List>
        <List title={`Run events (${map.events.length})`} empty="No events.">
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
        </List>
      </div>
    </div>
  );
}

function List({ title, empty, children }: { title: string; empty: string; children: React.ReactNode[] }) {
  return (
    <div>
      <h3 style={{ marginBottom: 10 }}>{title}</h3>
      <div className="panel" style={{ maxHeight: 320, overflow: "auto" }}>
        {children.length ? (
          <table className="tbl">
            <tbody>{children}</tbody>
          </table>
        ) : (
          <div className="small muted" style={{ padding: 12 }}>
            {empty}
          </div>
        )}
      </div>
    </div>
  );
}
