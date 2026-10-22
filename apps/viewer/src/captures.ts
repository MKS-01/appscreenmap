import { useEffect, useMemo, useState } from "react";
import { runFile, usePolled } from "./api";
import type { AppMapData } from "./types";

/**
 * What a run recorded beyond the map (docs/MAP_SCHEMA.md: network.jsonl, logs.jsonl, sessions/). The summary comes
 * from `appscreenmap serve` (`GET /api/captures`); on a static host there is none, and every entry point hides.
 */

export interface NetRow {
  event: "connect" | "connect_failed" | "request";
  source?: string;
  mode?: string;
  t: number;
  t_end?: number;
  method?: string;
  scheme?: string;
  host: string;
  port?: number;
  path?: string;
  query_keys?: string[];
  status?: number;
  content_type?: string;
  bytes_in?: number;
  bytes_out?: number;
  http_version?: string;
  timing?: Partial<Record<Phase, number>>;
  error?: string;
  screen?: string | null;
  screen_title?: string;
  step?: number;
  scenario?: string;
}

export interface LogRow {
  t: number;
  level: "verbose" | "debug" | "info" | "warn" | "error" | "fatal";
  tag: string;
  message: string;
  screen?: string | null;
  step?: number;
  scenario?: string;
}

export const PHASES = ["connect", "tls", "send", "wait", "receive"] as const;
export type Phase = (typeof PHASES)[number];
export const PHASE_LABEL: Record<Phase, string> = {
  connect: "Connect",
  tls: "TLS",
  send: "Send",
  wait: "Waiting (TTFB)",
  receive: "Download",
};

export interface CaptureSummary {
  network: { log: string; events: number; hosts: { host: string }[]; cleartext_hosts: string[] } | null;
  logs: { log: string; lines: number } | null;
}

export interface SessionInfo extends CaptureSummary {
  id: string;
  kind: "manual";
  status: "recording" | "done" | "failed" | "starting";
  started_at?: string;
  finished_at?: string | null;
  error?: string;
  screens?: string[];
  path: string;
  stoppable: boolean;
}

export interface Captures extends CaptureSummary {
  run: string;
  sessions: SessionInfo[];
}

/** Where a row came from: a crawl scenario, or a manual session. Rows from different origins are never interleaved. */
export interface Origin {
  key: string;
  label: string;
  kind: "crawl" | "session";
  live: boolean;
}

/** null until loaded, and for good when the dashboard server isn't there (static host): no captures UI then. */
export function useCaptures(run: string, reload = 0): { data: Captures | null; available: boolean | null } {
  const [state, setState] = useState<{ data: Captures | null; available: boolean | null }>({ data: null, available: null });
  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const tick = async () => {
      try {
        const r = await fetch(`/api/captures?run=${encodeURIComponent(run)}`, { cache: "no-store" });
        if (!alive) return;
        if (!r.ok || !(r.headers.get("content-type") ?? "").includes("json")) return setState({ data: null, available: false });
        const data = (await r.json()) as Captures;
        if (!alive) return;
        setState({ data, available: true });
        if (data.sessions.some((s) => s.status === "recording")) timer = setTimeout(tick, 2000);
      } catch {
        if (alive) setState({ data: null, available: false });
      }
    };
    tick();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [run, reload]);
  return state;
}

/** A tunnel the proxy couldn't open is logged twice (connect, then connect_failed): keep one row, the failure. */
function oneRowPerTunnel<T>(rows: T[]): T[] {
  const failed = new Set(
    rows.flatMap((r) => {
      const n = r as unknown as NetRow;
      return n.event === "connect_failed" ? [`${n.host}:${n.port}:${n.t}`] : [];
    }),
  );
  return rows.filter((r) => {
    const n = r as unknown as NetRow;
    return !(n.event === "connect" && failed.has(`${n.host}:${n.port}:${n.t}`));
  });
}

const parseRows = <T,>(text: string): T[] => oneRowPerTunnel(parseLines<T>(text));

const parseLines = <T,>(text: string): T[] =>
  text.split("\n").flatMap((l) => {
    if (!l.trim()) return [];
    try {
      const o = JSON.parse(l);
      return o && o.asm === 1 ? [o as T] : []; // other lines aren't ours; a half-written last line is skipped
    } catch {
      return [];
    }
  });

/** A capture file's rows; empty when the file isn't there. Polled while `live`. */
export function useRows<T>(url: string | null, live = false): T[] {
  const { data } = usePolled<T[]>(url, parseRows, live ? 2000 : 0, () => live);
  return data ?? [];
}

export const hasCaptures = (c: CaptureSummary | null | undefined) => !!(c?.network || c?.logs);

/** The crawl's rows (every scenario of a canvas) plus one session's, each tagged with its origin. */
export function useRunRows(run: string, map: AppMapData, caps: Captures | null) {
  const net = useRows<NetRow>(caps?.network ? runFile(run, caps.network.log) : null, map.run.status === "running");
  const logs = useRows<LogRow>(caps?.logs ? runFile(run, caps.logs.log) : null, map.run.status === "running");
  const scenarios = map.run.scenarios ?? [];
  const origin = (r: { scenario?: string }): Origin => {
    const sc = scenarios.find((s) => s.id === r.scenario);
    return {
      key: `crawl:${r.scenario ?? ""}`,
      label: sc ? `${sc.id}${sc.label ? ` · ${sc.label}` : ""}` : "Crawl",
      kind: "crawl",
      live: map.run.status === "running",
    };
  };
  return useMemo(
    () => ({ net: net.map((r) => ({ ...r, origin: origin(r) })), logs: logs.map((r) => ({ ...r, origin: origin(r) })) }),
    [net, logs, scenarios],
  );
}

export const sessionOrigin = (s: SessionInfo): Origin => ({
  key: `session:${s.id}`,
  label: `Manual session · ${sessionWhen(s)}`,
  kind: "session",
  live: s.status === "recording",
});

export function useSessionRows(run: string, s: SessionInfo | null) {
  const live = s?.status === "recording";
  const net = useRows<NetRow>(s?.network ? runFile(run, `${s.path}/${s.network.log}`) : null, live);
  const logs = useRows<LogRow>(s?.logs ? runFile(run, `${s.path}/${s.logs.log}`) : null, live);
  return useMemo(() => {
    if (!s) return { net: [], logs: [] };
    const o = sessionOrigin(s);
    return { net: net.map((r) => ({ ...r, origin: o })), logs: logs.map((r) => ({ ...r, origin: o })) };
  }, [net, logs, s?.id, s?.status]);
}

export type Tagged<T> = T & { origin: Origin };

export const sessionWhen = (s: SessionInfo) =>
  s.started_at
    ? new Date(s.started_at).toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })
    : s.id;

export const isFailed = (r: NetRow) => r.event === "connect_failed" || (r.event === "request" && !!r.error);
export const isCleartext = (r: NetRow) => r.event === "request" && r.scheme === "http";
export const durationMs = (r: NetRow) => (r.t_end != null ? Math.round((r.t_end - r.t) * 1000) : null);

export function fmtBytes(n: number | undefined) {
  if (n == null) return "—";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(n < 10240 ? 1 : 0)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

export interface HostSum {
  host: string;
  rows: number;
  failed: number;
  cleartext: number;
  screens: number;
}

export function hostsOf(rows: NetRow[]): HostSum[] {
  const m = new Map<string, HostSum & { s: Set<string> }>();
  for (const r of rows) {
    const h = m.get(r.host) ?? { host: r.host, rows: 0, failed: 0, cleartext: 0, screens: 0, s: new Set<string>() };
    h.rows += 1;
    h.failed += isFailed(r) ? 1 : 0;
    h.cleartext += isCleartext(r) ? 1 : 0;
    if (r.screen) h.s.add(r.screen);
    m.set(r.host, h);
  }
  return [...m.values()]
    .map(({ s, ...h }) => ({ ...h, screens: s.size }))
    .sort((a, b) => b.rows - a.rows || a.host.localeCompare(b.host));
}

/** Rows grouped by origin, in the order they came. */
export function byOrigin<T extends { origin: Origin }>(rows: T[]): [Origin, T[]][] {
  const m = new Map<string, [Origin, T[]]>();
  for (const r of rows) {
    const g = m.get(r.origin.key) ?? [r.origin, []];
    g[1].push(r);
    m.set(r.origin.key, g);
  }
  return [...m.values()];
}

/** Start or stop a manual session through `serve`. Throws with the server's reason. */
export async function startSession(run: string, network: boolean): Promise<SessionInfo> {
  const r = await fetch("/api/sessions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ run, network }),
  });
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(body.error ?? `${r.status} ${r.statusText}`);
  return body as SessionInfo;
}

export async function stopSession(id: string): Promise<void> {
  const r = await fetch(`/api/sessions/${encodeURIComponent(id)}/stop`, { method: "POST", headers: { "Content-Type": "application/json" } });
  if (!r.ok) throw new Error(r.status === 404 ? "This session isn't recording from this dashboard any more." : `${r.status} ${r.statusText}`);
}

/** Every manual session's rows, tagged; re-read while one is recording. */
export function useAllSessionRows(run: string, sessions: SessionInfo[]) {
  const [rows, setRows] = useState<{ net: Tagged<NetRow>[]; logs: Tagged<LogRow>[] }>({ net: [], logs: [] });
  const live = sessions.some((s) => s.status === "recording");
  const sig = sessions.map((s) => `${s.id}:${s.status}`).join(",");
  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const read = async (url: string) => {
      try {
        const r = await fetch(url, { cache: "no-store" });
        return r.ok ? await r.text() : "";
      } catch {
        return "";
      }
    };
    const tick = async () => {
      const parts = await Promise.all(
        sessions.map(async (s) => {
          const o = sessionOrigin(s);
          const [n, l] = await Promise.all([
            s.network ? read(runFile(run, `${s.path}/${s.network.log}`)) : "",
            s.logs ? read(runFile(run, `${s.path}/${s.logs.log}`)) : "",
          ]);
          return {
            net: parseRows<NetRow>(n).map((r) => ({ ...r, origin: o })),
            logs: parseRows<LogRow>(l).map((r) => ({ ...r, origin: o })),
          };
        }),
      );
      if (!alive) return;
      setRows({ net: parts.flatMap((p) => p.net), logs: parts.flatMap((p) => p.logs) });
      if (live) timer = setTimeout(tick, 2000);
    };
    tick();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [run, sig]);
  return rows;
}
