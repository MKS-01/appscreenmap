import { useEffect, useRef, useState } from "react";

// The activity log, read from `appscreenmap serve` (packages/core/.../activity.py, engine/cli/serve.py):
//   GET /api/activity/live                what is running now, and what finished in the last few seconds
//   GET /api/logs/sessions?q=&source=…    command runs that match, newest first
//   GET /api/logs/session?id=&from=       one command run's lines
// The Vite dev server has no such endpoints: the hooks then report `supported: false` and the UI stays hidden.

export const SOURCES = ["agent", "cli", "mcp", "ci"] as const;
export type Source = (typeof SOURCES)[number];
export type Level = "info" | "warn" | "error";
export type SessionStatus = "running" | "done" | "failed" | "interrupted";

export const SOURCE_LABEL: Record<string, string> = { agent: "AI agent", cli: "Terminal", mcp: "MCP", ci: "CI" };

export interface Session {
  id: string;
  cmd: string;
  source: string;
  run: string | null;
  pid: number;
  start: string;
  end: string | null;
  exit: number | null;
  command: string;
  lines: number;
  warnings: number;
  errors: number;
  last: string;
  last_t: string;
  status: SessionStatus;
  recent: boolean;
  matches?: number;
  snippet?: string;
}

export interface LogEvent {
  t: string;
  cmd: string;
  run: string | null;
  source: string;
  level: Level;
  msg: string;
  kind?: "start" | "end";
  match?: boolean;
}

export interface Live {
  has_logs: boolean;
  running: Session[];
  recent: Session[];
}

export interface SessionQuery {
  q?: string;
  source?: string;
  cmd?: string;
  run?: string;
  level?: Level | "";
  status?: SessionStatus | "";
}

const qs = (o: Record<string, string | number | undefined | null>) =>
  new URLSearchParams(Object.entries(o).filter(([, v]) => v !== undefined && v !== null && v !== "") as [string, string][]).toString();

async function getJson<T>(url: string): Promise<T | null> {
  const r = await fetch(url, { cache: "no-store" });
  if (r.status === 404) return null;
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  const type = r.headers.get("content-type") ?? "";
  return type.includes("json") ? ((await r.json()) as T) : null; // a static host answers with index.html
}

/** Seconds between two ISO times (end defaults to now). */
export function elapsed(start: string, end?: string | null): number {
  const a = Date.parse(start);
  const b = end ? Date.parse(end) : Date.now();
  return Number.isNaN(a) || Number.isNaN(b) ? 0 : Math.max(0, (b - a) / 1000);
}

/** "12:04:31" in local time. */
export const clock = (iso: string) => {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
};

/** What is running now. Polls every `ms`; `supported` is false when the server has no activity endpoints. */
export function useLive(ms = 2000): { live: Live | null; supported: boolean } {
  const [state, setState] = useState<{ live: Live | null; supported: boolean }>({ live: null, supported: true });
  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const tick = async () => {
      try {
        const live = await getJson<Live>("/api/activity/live");
        if (!alive) return;
        if (live === null) return setState({ live: null, supported: false }); // no endpoint here: stop asking
        setState({ live, supported: true });
      } catch {
        // the server restarting: try again
      }
      if (alive) timer = setTimeout(tick, document.hidden ? ms * 4 : ms);
    };
    tick();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [ms]);
  return state;
}

/** Command runs that match `query`, newest first. Refreshes every `ms` so a running one keeps its numbers current. */
export function useSessions(query: SessionQuery, ms = 4000): { sessions: Session[] | null; total: number; error: string | null } {
  const [state, setState] = useState<{ sessions: Session[] | null; total: number; error: string | null }>({ sessions: null, total: 0, error: null });
  const key = qs({ ...query, limit: 200 });
  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const tick = async () => {
      try {
        const res = await getJson<{ sessions: Session[]; total: number }>(`/api/logs/sessions?${key}`);
        if (!alive) return;
        if (res === null) return setState({ sessions: null, total: 0, error: "This view needs the dashboard server: run `appscreenmap serve`." });
        setState({ sessions: res.sessions, total: res.total, error: null });
      } catch (e) {
        if (alive) setState((s) => ({ ...s, error: String((e as Error).message ?? e) }));
      }
      if (alive) timer = setTimeout(tick, ms);
    };
    const debounce = setTimeout(tick, 150); // typing in the search box
    return () => {
      alive = false;
      clearTimeout(debounce);
      clearTimeout(timer);
    };
  }, [key, ms]);
  return state;
}

/** One command run's lines; while it runs, new lines are fetched every `ms` and appended. */
export function useSessionLines(id: string | null, follow: boolean, highlight: SessionQuery = {}, ms = 1000) {
  const [events, setEvents] = useState<LogEvent[]>([]);
  const [session, setSession] = useState<Session | null>(null);
  const next = useRef(0);
  const hl = qs({ q: highlight.q, level: highlight.level });
  useEffect(() => {
    setEvents([]);
    setSession(null);
    next.current = 0;
    if (!id) return;
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const tick = async () => {
      try {
        const res = await getJson<{ session: Session; events: LogEvent[]; next: number }>(`/api/logs/session?${qs({ id, from: next.current })}&${hl}`);
        if (!alive || !res) return;
        next.current = res.next;
        setSession(res.session);
        if (res.events.length) setEvents((ev) => [...ev, ...res.events]);
        if (follow && res.session.status === "running") timer = setTimeout(tick, ms);
      } catch {
        if (alive && follow) timer = setTimeout(tick, ms * 2);
      }
    };
    tick();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [id, follow, hl, ms]);
  return { events, session };
}
