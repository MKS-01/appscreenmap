import { Fragment, useMemo, useState } from "react";
import {
  byOrigin,
  durationMs,
  fmtBytes,
  hostsOf,
  isCleartext,
  isFailed,
  PHASE_LABEL,
  PHASES,
  type LogRow,
  type NetRow,
  type Tagged,
} from "../captures";
import { href, screenHref } from "../router";
import type { Screen } from "../types";
import { Stat } from "./common";

/** Shared by the screen page's Network / Logs tabs, the run's Network · Logs view and Crawl replay (variant A). */

const offset = (t: number, t0: number) => `+${(t - t0).toFixed(2)} s`;

export function NetStats({ rows }: { rows: NetRow[] }) {
  const requests = rows.filter((r) => r.event === "request").length;
  const hosts = new Set(rows.map((r) => r.host));
  const failed = rows.filter(isFailed).length;
  const clear = rows.filter(isCleartext).length;
  const slowest = Math.max(0, ...rows.map((r) => durationMs(r) ?? 0));
  // Observe mode sees HTTPS as tunnels (host only); only plain http:// is read in full.
  const tunnels = rows.length - requests;
  return (
    <div className="stats net-stats">
      <Stat value={rows.length} label={tunnels && requests ? `calls · ${requests} read in full` : tunnels ? "calls · HTTPS, host only" : "requests"} />
      <Stat value={hosts.size} label="hosts" />
      <Stat value={<span className={clear ? "tone-warn" : undefined}>{clear}</span>} label="plain http://" />
      <Stat value={<span className={failed ? "tone-bad" : undefined}>{failed}</span>} label="failed" />
      <Stat value={slowest ? `${slowest} ms` : "—"} label="slowest request" />
    </div>
  );
}

export function NetNote() {
  return (
    <p className="small faint net-note">
      Timings are measured at the proxy, not on the device. Bodies, header values and query values are never stored. The proxy only sees apps
      that use the system proxy, so an empty list means nothing was seen, not that nothing was sent.
    </p>
  );
}

function StatusCell({ r }: { r: NetRow }) {
  if (isFailed(r))
    return (
      <span className="net-status bad" title={r.error ?? "the proxy couldn't reach this host"}>
        FAILED
      </span>
    );
  if (r.event === "connect") return <span className="net-status faint">TLS</span>;
  return <span className={`net-status ${isCleartext(r) ? "warn" : ""}`}>{r.status ?? "—"}</span>;
}

function RequestCell({ r }: { r: NetRow }) {
  if (r.event !== "request")
    return (
      <>
        <span className="net-method">CONNECT</span> {r.host}
        <span className="net-flag">{r.event === "connect_failed" ? "HOST ONLY · UNREACHABLE" : "HOST ONLY"}</span>
      </>
    );
  return (
    <>
      <span className="net-method">{r.method}</span> {isCleartext(r) && <span className="tone-warn">http://</span>}
      {r.host}
      <span className="dim">{r.path}</span>
      {isCleartext(r) && <span className="net-flag tone-warn">● CLEARTEXT</span>}
    </>
  );
}

/** Proportional bar: the phases when the proxy recorded them, else one segment for the whole request. */
function TimeBar({ r, max }: { r: NetRow; max: number }) {
  const ms = durationMs(r);
  if (ms == null) return <span className="faint">—</span>;
  const width = max ? Math.max(2, (100 * ms) / max) : 0;
  const t = r.timing ?? {};
  const parts = PHASES.filter((p) => t[p] != null && t[p]! > 0);
  const total = parts.reduce((a, p) => a + t[p]!, 0);
  return (
    <div className="net-time">
      <div className="net-bar" aria-hidden style={{ width: `${width}%` }}>
        {parts.length ? parts.map((p) => <span key={p} className={`ph-${p}`} style={{ flex: t[p]! / total }} />) : <span className="ph-all" />}
      </div>
      <span className="mono small">{ms} ms</span>
    </div>
  );
}

function RowDetail({ r }: { r: NetRow }) {
  const ms = durationMs(r);
  const t = r.timing ?? {};
  const phases = PHASES.filter((p) => t[p] != null);
  const max = Math.max(1, ...phases.map((p) => t[p]!));
  return (
    <div className="net-detail">
      {phases.length > 0 && (
        <div className="col" style={{ gap: 8 }}>
          <span className="kicker-plain">
            {r.method} {r.path} · where the {ms} ms went
          </span>
          <dl className="net-phases">
            {phases.map((p) => (
              <Fragment key={p}>
                <dt>{PHASE_LABEL[p]}</dt>
                <dd className="mono">{t[p]} ms</dd>
                <dd>
                  <span className={`net-phase-bar ph-${p}`} style={{ width: `${(100 * t[p]!) / max}%` }} />
                </dd>
              </Fragment>
            ))}
          </dl>
        </div>
      )}
      <dl className="net-facts">
        {r.event === "request" && (
          <>
            <dt>Query keys</dt>
            <dd className="mono">{r.query_keys?.length ? r.query_keys.join(", ") : "none"}</dd>
            {r.content_type && (
              <>
                <dt>Content type</dt>
                <dd className="mono">{r.content_type}</dd>
              </>
            )}
            {r.http_version && (
              <>
                <dt>Protocol</dt>
                <dd className="mono">{r.http_version}</dd>
              </>
            )}
          </>
        )}
        <dt>Host</dt>
        <dd className="mono">
          {r.host}
          {r.port ? `:${r.port}` : ""}
        </dd>
        {r.error && (
          <>
            <dt>Error</dt>
            <dd className="mono tone-bad">{r.error}</dd>
          </>
        )}
        <dt>Source</dt>
        <dd className="mono">
          {r.source ?? "proxy"} · {r.mode ?? "observe"}
        </dd>
        <dt>Body</dt>
        <dd className="dim">not stored, by design</dd>
      </dl>
    </div>
  );
}

/** STATUS · REQUEST · SIZE · TIME (+ SCREEN and STEP outside a screen page), grouped by origin. */
export function NetTable({
  run,
  rows,
  byId,
  showScreen,
  empty = "Nothing seen on this screen.",
}: {
  run: string;
  rows: Tagged<NetRow>[];
  byId?: Map<string, Screen>;
  showScreen?: boolean;
  empty?: string;
}) {
  const [host, setHost] = useState<string | null>(null);
  const [sel, setSel] = useState<string | null>(null);
  const shown = host ? rows.filter((r) => r.host === host) : rows;
  const max = Math.max(0, ...shown.map((r) => durationMs(r) ?? 0));
  const groups = byOrigin(shown);
  const cols = showScreen ? 6 : 4;
  if (!rows.length) return <div className="empty">{empty}</div>;
  return (
    <div className="col" style={{ gap: 14 }}>
      <div className="tbl-scroll net-table">
        <table className="tbl">
          <thead>
            <tr>
              <th scope="col">Status</th>
              <th scope="col">Request</th>
              {showScreen && <th scope="col">Screen</th>}
              {showScreen && <th scope="col">Step</th>}
              <th scope="col">Size</th>
              <th scope="col" style={{ width: 220 }}>
                Time
              </th>
            </tr>
          </thead>
          <tbody>
            {groups.map(([o, rs]) => {
              const t0 = rs[0]?.t ?? 0;
              return (
                <Fragment key={o.key}>
                  {groups.length > 1 && (
                    <tr className="net-group">
                      <td colSpan={cols}>
                        {o.label}
                        {o.live && <span className="net-live"> · recording</span>}
                      </td>
                    </tr>
                  )}
                  {rs.map((r, k) => {
                    const key = `${o.key}:${k}:${r.t}`;
                    const screen = r.screen ? byId?.get(r.screen) : undefined;
                    return (
                      <Fragment key={key}>
                        <tr className={`hover ${sel === key ? "sel" : ""}`}>
                          <td>
                            <StatusCell r={r} />
                          </td>
                          <td className="net-req">
                            <button type="button" className="net-row-btn" aria-expanded={sel === key} onClick={() => setSel(sel === key ? null : key)}>
                              <RequestCell r={r} />
                            </button>
                            <span className="faint mono small net-t" title="since the first row of this list">
                              {offset(r.t, t0)}
                            </span>
                          </td>
                          {showScreen && (
                            <td className="small">
                              {screen ? (
                                <a href={`${screenHref(run, screen.id)}?tab=network`}>
                                  <span className="sid">{screen.id}</span> {screen.title}
                                </a>
                              ) : (
                                <span className="faint">{r.screen === null ? "outside the app" : "—"}</span>
                              )}
                            </td>
                          )}
                          {showScreen && (
                            <td className="mono small">
                              {r.step != null && o.kind === "crawl" ? <a href={`${href("r", run, "replay")}?step=${r.step}`}>{r.step}</a> : <span className="faint">—</span>}
                            </td>
                          )}
                          <td className="mono small dim">{r.event === "request" ? fmtBytes(r.bytes_in) : "—"}</td>
                          <td>
                            <TimeBar r={r} max={max} />
                          </td>
                        </tr>
                        {sel === key && (
                          <tr className="net-detail-row">
                            <td colSpan={cols}>
                              <RowDetail r={r} />
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    );
                  })}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
      <HostStrip rows={rows} host={host} onHost={setHost} />
    </div>
  );
}

export function HostStrip({ rows, host, onHost }: { rows: NetRow[]; host: string | null; onHost: (h: string | null) => void }) {
  const hosts = useMemo(() => hostsOf(rows), [rows]);
  if (!hosts.length) return null;
  return (
    <section className="col" style={{ gap: 8 }} aria-label="Hosts">
      <span className="kicker-plain">Hosts {host ? "· filtering by one" : "· click one to filter"}</span>
      <div className="row wrap" style={{ gap: 8 }}>
        {hosts.map((h) => (
          <button key={h.host} type="button" className={`host-chip ${host === h.host ? "on" : ""}`} aria-pressed={host === h.host} onClick={() => onHost(host === h.host ? null : h.host)}>
            {h.host}
            <span className="mono">
              {h.cleartext ? <span className="tone-warn">HTTP · </span> : null}
              {h.failed ? <span className="tone-bad">{h.failed} FAILED · </span> : null}
              {h.screens ? `${h.screens} ${h.screens === 1 ? "screen" : "screens"}` : `${h.rows} ${h.rows === 1 ? "row" : "rows"}`}
            </span>
          </button>
        ))}
      </div>
    </section>
  );
}

const LEVEL: Record<LogRow["level"], string> = { verbose: "VERB", debug: "DEBUG", info: "INFO", warn: "WARN", error: "ERROR", fatal: "FATAL" };

/** The app's own log lines, grouped by origin, times relative to each group's first line. */
export function AppLogList({ rows, byId, run, showScreen, empty = "No app log lines on this screen." }: { rows: Tagged<LogRow>[]; byId?: Map<string, Screen>; run: string; showScreen?: boolean; empty?: string }) {
  const [q, setQ] = useState("");
  const [minLevel, setMinLevel] = useState<"all" | "warn">("all");
  const words = q.trim().toLowerCase();
  const shown = rows.filter((r) => (minLevel === "all" || ["warn", "error", "fatal"].includes(r.level)) && (!words || `${r.tag} ${r.message}`.toLowerCase().includes(words)));
  if (!rows.length) return <div className="empty">{empty}</div>;
  const groups = byOrigin(shown);
  return (
    <div className="col" style={{ gap: 10 }}>
      <div className="row wrap" style={{ gap: 8 }}>
        <input type="search" className="grow" placeholder="Find in the log: tag or text" aria-label="Find in the app log" value={q} onChange={(e) => setQ(e.target.value)} />
        <div className="seg" role="group" aria-label="Level">
          <button aria-pressed={minLevel === "all"} onClick={() => setMinLevel("all")}>
            All
          </button>
          <button aria-pressed={minLevel === "warn"} onClick={() => setMinLevel("warn")}>
            Warnings and errors
          </button>
        </div>
      </div>
      <div className="app-log">
        {shown.length === 0 && <div className="log-empty">No line matches.</div>}
        {groups.map(([o, rs]) => (
          <Fragment key={o.key}>
            {groups.length > 1 && <div className="app-log-group">{o.label}</div>}
            {rs.map((r, k) => {
              const screen = r.screen ? byId?.get(r.screen) : undefined;
              const tone = r.level === "warn" ? "warn" : r.level === "error" || r.level === "fatal" ? "error" : "";
              return (
                <div key={k} className={`log-line app-log-line ${tone}`}>
                  <span className="log-t">{offset(r.t, rs[0].t)}</span>
                  <span className="log-lvl app-log-lvl">{LEVEL[r.level] ?? r.level}</span>
                  <span className="app-log-tag ellipsis" title={r.tag}>
                    {r.tag}
                  </span>
                  <span className="log-msg">
                    {r.message}
                    {showScreen && screen && (
                      <a className="app-log-screen" href={screenHref(run, screen.id)}>
                        {screen.id}
                      </a>
                    )}
                  </span>
                </div>
              );
            })}
          </Fragment>
        ))}
      </div>
      <p className="small faint">Lines are masked before they're written: a token-shaped value shows as its kind and fingerprint, never the value.</p>
    </div>
  );
}
