import { useEffect, useRef, useState } from "react";
import type { AppMapData, RunIndexRow, TraceRow } from "./types";

/**
 * Viewer routes and file URLs address a run by its folder under runs/ — `<project>/<run-id>` in the current
 * layout, or just `<run-id>` for legacy runs. index.json gives each row's `path`.
 */
export const runFile = (run: string, rel: string) => `/runs/${run}/${rel}`;
export const runKey = (r: RunIndexRow) => r.path ?? r.id;

async function getText(url: string): Promise<string> {
  const r = await fetch(url, { cache: "no-store" });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText} — ${url}`);
  return r.text();
}

export interface Loaded<T> {
  data: T | null;
  error: string | null;
}

/** Fetch a resource and keep refetching every `pollMs` while `keepPolling(data)` holds. */
export function usePolled<T>(
  url: string | null,
  parse: (text: string) => T,
  pollMs = 0,
  keepPolling: (d: T) => boolean = () => true,
): Loaded<T> {
  const [state, setState] = useState<Loaded<T>>({ data: null, error: null });
  const parseRef = useRef(parse);
  const keepRef = useRef(keepPolling);
  parseRef.current = parse;
  keepRef.current = keepPolling;

  useEffect(() => {
    if (!url) return;
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let lastText = "";
    let latest: T | null = null;
    setState({ data: null, error: null });
    const tick = async () => {
      try {
        const text = await getText(url);
        if (!alive) return;
        if (text !== lastText) {
          lastText = text;
          latest = parseRef.current(text);
          setState({ data: latest, error: null });
        }
        if (pollMs && latest && keepRef.current(latest)) timer = setTimeout(tick, pollMs);
      } catch (e) {
        if (!alive) return;
        // Reads of a live run can race a write; keep the last good data and retry.
        if (latest) timer = setTimeout(tick, Math.max(pollMs, 1000) * 2);
        else setState({ data: null, error: String((e as Error).message ?? e) });
      }
    };
    tick();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [url, pollMs]);

  return state;
}

const parseJson = <T,>(t: string) => JSON.parse(t) as T;
const isRunning = (m: AppMapData) => m.run.status === "running";

export const useIndex = () =>
  usePolled<{ runs: RunIndexRow[] }>("/runs/index.json", parseJson, 4000, (d) =>
    d.runs.some((r) => r.status === "running"),
  );

export const useMap = (run: string) => usePolled<AppMapData>(runFile(run, "map.json"), parseJson, 2000, isRunning);

export const parseTrace = (text: string): TraceRow[] =>
  text
    .split("\n")
    .filter((l) => l.trim())
    .flatMap((l) => {
      try {
        return [JSON.parse(l) as TraceRow];
      } catch {
        return []; // a partially written last line while the crawl is running
      }
    });

export function useText(url: string | null): Loaded<string> {
  return usePolled<string>(url, (t) => t);
}
