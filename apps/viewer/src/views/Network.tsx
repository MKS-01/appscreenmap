import { useMemo, useState } from "react";
import {
  hasCaptures,
  sessionWhen,
  startSession,
  stopSession,
  useRunRows,
  useSessionRows,
  type Captures,
  type SessionInfo,
} from "../captures";
import { AppLogList, NetNote, NetStats, NetTable } from "../components/NetLog";
import { StatusBadge } from "../components/common";
import { platformOf } from "../a11y";
import { href, useRoute, go } from "../router";
import type { AppMapData } from "../types";
import { screenMap } from "../util";

/**
 * Network · Logs for a run. Two ways in: Replay (what each crawl step called) and Debug (a person uses the app while
 * AppScreenMap records, started and stopped from here through `serve`).
 */
export default function Network({ run, map, caps, reload }: { run: string; map: AppMapData; caps: Captures; reload: () => void }) {
  const route = useRoute();
  const mode = route.arg === "debug" ? "debug" : "replay";
  const crawled = hasCaptures(caps);
  return (
    <div className="page" style={{ maxWidth: 1320 }}>
      <div className="row wrap" style={{ marginBottom: 18, gap: 12, alignItems: "flex-end" }}>
        <div className="grow" style={{ minWidth: "min(100%, 320px)" }}>
          <span className="kicker">Network · Logs</span>
          <h1>What the app called, screen by screen</h1>
          <p className="lede">
            {mode === "replay"
              ? "Every request and log line the crawl recorded, on the screen that was showing. Step through Crawl replay to see each screen's calls as it opens."
              : "Use the app by hand while AppScreenMap records its log and traffic. Nothing is tapped for you; each line lands on the screen you were on."}
          </p>
        </div>
        <div className="seg" role="tablist" aria-label="Mode">
          <button role="tab" aria-selected={mode === "replay"} aria-pressed={mode === "replay"} onClick={() => go(href("r", run, "network"))}>
            Replay
          </button>
          <button role="tab" aria-selected={mode === "debug"} aria-pressed={mode === "debug"} onClick={() => go(href("r", run, "network", "debug"))}>
            Debug
          </button>
        </div>
      </div>
      {mode === "replay" ? (
        crawled ? (
          <ReplayMode run={run} map={map} caps={caps} />
        ) : (
          <div className="panel empty">
            No crawl of this app recorded its network or log yet. Crawl with <code className="mono">--network</code>, or record by hand under{" "}
            <a href={href("r", run, "network", "debug")}>Debug</a>.
          </div>
        )
      ) : (
        <DebugMode run={run} map={map} caps={caps} reload={reload} />
      )}
    </div>
  );
}

function ReplayMode({ run, map, caps }: { run: string; map: AppMapData; caps: Captures }) {
  const byId = useMemo(() => screenMap(map), [map]);
  const { net, logs } = useRunRows(run, map, caps);
  const scenarios = (map.run.scenarios ?? []).filter((s) => net.some((r) => r.scenario === s.id) || logs.some((r) => r.scenario === s.id));
  const [sc, setSc] = useState<string | null>(null);
  const pick = sc && scenarios.some((s) => s.id === sc) ? sc : null;
  const n = pick ? net.filter((r) => r.scenario === pick) : net;
  const l = pick ? logs.filter((r) => r.scenario === pick) : logs;
  const attributed = n.some((r) => r.screen);
  return (
    <div className="col" style={{ gap: 20 }}>
      {scenarios.length > 1 && (
        <div className="row wrap" style={{ gap: 8 }} role="group" aria-label="Scenario">
          <button type="button" className={`chip pick ${!pick ? "on" : ""}`} aria-pressed={!pick} onClick={() => setSc(null)}>
            All scenarios
          </button>
          {scenarios.map((s) => (
            <button key={s.id} type="button" className={`chip pick ${pick === s.id ? "on" : ""}`} aria-pressed={pick === s.id} onClick={() => setSc(s.id)}>
              {s.id}
              {s.label ? ` · ${s.label}` : ""}
            </button>
          ))}
        </div>
      )}
      <NetStats rows={n} />
      {!attributed && n.length > 0 && (
        <p className="small faint">These rows were recorded before AppScreenMap tied requests to screens, so they show without a screen or step.</p>
      )}
      <section className="col" style={{ gap: 10 }}>
        <h2>Requests</h2>
        <NetTable run={run} rows={n} byId={byId} showScreen empty="Nothing seen. The proxy only sees apps that use the system proxy." />
        <NetNote />
      </section>
      <section className="col" style={{ gap: 10 }}>
        <h2>App log</h2>
        <AppLogList run={run} rows={l} byId={byId} showScreen empty="No app log lines recorded." />
      </section>
    </div>
  );
}

function DebugMode({ run, map, caps, reload }: { run: string; map: AppMapData; caps: Captures; reload: () => void }) {
  const byId = useMemo(() => screenMap(map), [map]);
  const [network, setNetwork] = useState(true);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [pickId, setPickId] = useState<string | null>(null);
  const recording = caps.sessions.find((s) => s.status === "recording");
  const current = caps.sessions.find((s) => s.id === pickId) ?? recording ?? caps.sessions[0] ?? null;
  const { net, logs } = useSessionRows(run, current);
  const isAndroid = platformOf(map) === "android";

  const start = async () => {
    setBusy(true);
    setErr(null);
    try {
      const s = await startSession(run, network);
      setPickId(s.id);
      reload();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const stop = async (s: SessionInfo) => {
    setBusy(true);
    setErr(null);
    try {
      await stopSession(s.id);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
      reload();
    }
  };

  return (
    <div className="col" style={{ gap: 20 }}>
      <section className="panel panel-pad debug-bar">
        {recording ? (
          <>
            <div className="col grow" style={{ gap: 4 }}>
              <div className="row" style={{ gap: 10 }}>
                <StatusBadge status="running" />
                <b>Recording since {sessionWhen(recording)}</b>
              </div>
              <span className="small dim">
                Use the app on the emulator. {recording.network ? "The emulator's proxy points at AppScreenMap until you stop. " : ""}
                {recording.stoppable ? "" : "Started from the terminal: stop it there with Ctrl-C."}
              </span>
            </div>
            {recording.stoppable && (
              <button className="btn primary" disabled={busy} onClick={() => stop(recording)}>
                {busy ? "Stopping…" : "Stop"}
              </button>
            )}
          </>
        ) : (
          <>
            <div className="col grow" style={{ gap: 4 }}>
              <b>Debug by hand</b>
              <span className="small dim">
                {isAndroid
                  ? "Records the app's own log, and with network on, every host it calls. Network changes the emulator's proxy setting until you stop."
                  : "Manual sessions work on Android for now; iOS simulators are planned."}
              </span>
            </div>
            <label className="check">
              <input type="checkbox" checked={network} onChange={(e) => setNetwork(e.target.checked)} disabled={!isAndroid} /> Network
            </label>
            <button className="btn primary" disabled={busy || !isAndroid} onClick={start}>
              {busy ? "Starting…" : "Start debugging"}
            </button>
          </>
        )}
        {err && (
          <div className="error small" role="alert" style={{ flexBasis: "100%", padding: 0 }}>
            {err}
          </div>
        )}
      </section>

      {caps.sessions.length > 0 ? (
        <>
          <section className="col" style={{ gap: 8 }}>
            <h2>Sessions</h2>
            <div className="tbl-scroll panel">
              <table className="tbl">
                <thead>
                  <tr>
                    <th scope="col">Started</th>
                    <th scope="col">Status</th>
                    <th scope="col">Screens</th>
                    <th scope="col">Log lines</th>
                    <th scope="col">Hosts</th>
                  </tr>
                </thead>
                <tbody>
                  {caps.sessions.map((s) => (
                    <tr key={s.id} className={`hover ${current?.id === s.id ? "sel" : ""}`}>
                      <td>
                        <button type="button" className="net-row-btn" aria-pressed={current?.id === s.id} onClick={() => setPickId(s.id)}>
                          {sessionWhen(s)}
                        </button>
                      </td>
                      <td>
                        <StatusBadge status={s.status === "recording" ? "running" : s.status} />
                      </td>
                      <td className="mono small">{s.screens?.length ?? 0}</td>
                      <td className="mono small">{s.logs?.lines ?? "—"}</td>
                      <td className="mono small">{s.network ? s.network.hosts.length : "off"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
          {current && (
            <>
              {current.error && <div className="error small">{current.error}</div>}
              {current.network && <NetStats rows={net} />}
              <section className="col" style={{ gap: 10 }}>
                <h2>Requests</h2>
                {current.network ? (
                  <>
                    <NetTable run={run} rows={net} byId={byId} showScreen empty={current.status === "recording" ? "Nothing seen yet. Open a screen that loads something." : "Nothing seen in this session."} />
                    <NetNote />
                  </>
                ) : (
                  <div className="empty">Network was off for this session.</div>
                )}
              </section>
              <section className="col" style={{ gap: 10 }}>
                <h2>App log</h2>
                <AppLogList run={run} rows={logs} byId={byId} showScreen empty={current.status === "recording" ? "No lines yet." : "No app log lines in this session."} />
              </section>
            </>
          )}
        </>
      ) : (
        <div className="empty">No manual sessions yet. Start one above, or run <code className="mono">appscreenmap watch</code> in a terminal.</div>
      )}
    </div>
  );
}
