// The dashboard server: the engine's `serve` (viewer + runs/ + the notes endpoint), run in the background while the
// terminal home is open. One implementation of that contract, in the engine; this file only starts, finds and stops it.
import { existsSync, rmSync } from "node:fs";
import { createServer } from "node:net";
import type { Subprocess } from "bun";
import type { Engine } from "./engine";
import type { Home } from "./home";

export interface Dashboard {
  url: string;
  origin: "spawned" | "attached";
  proc: Subprocess | null;
}

export interface DashboardOptions {
  runs: string;
  host: string;
  port: number;
  viewer?: string | null; // built viewer folder for the engine's serve (APPSCREENMAP_WEB)
  home?: Home; // records the dashboard it starts, so others attach only when the runs folder matches
}

/** What a terminal home writes about the dashboard it started (home/dashboard.json). */
interface DashboardRecord {
  pid: number; // the engine's serve
  cliPid: number; // the terminal home that owns it
  url: string;
  runs: string;
}

const alive = (pid: number) => {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
};

/**
 * A dashboard left running by a terminal home that was killed (its owner is gone): stop it, so it doesn't keep
 * serving an old runs folder on the default port. Returns the record of a live, owned one.
 */
export function reapOrphan(home: Home): DashboardRecord | null {
  const rec = home.readJson<DashboardRecord>(home.dashboardFile);
  if (!rec) return null;
  if (!alive(rec.pid)) {
    rmSync(home.dashboardFile, { force: true });
    return null;
  }
  if (!alive(rec.cliPid)) {
    try {
      process.kill(rec.pid);
    } catch {}
    rmSync(home.dashboardFile, { force: true });
    return null;
  }
  return rec;
}

/** Is an AppScreenMap dashboard answering at `base`? */
export async function isDashboard(base: string, timeoutMs = 800): Promise<boolean> {
  try {
    const res = await fetch(`${base}/runs/index.json`, { signal: AbortSignal.timeout(timeoutMs) });
    if (!res.ok) return false;
    const body = (await res.json()) as { runs?: unknown };
    return Array.isArray(body.runs);
  } catch {
    return false;
  }
}

export function portFree(host: string, port: number): Promise<boolean> {
  return new Promise((resolve) => {
    const srv = createServer();
    srv.once("error", () => resolve(false));
    srv.listen(port, host, () => srv.close(() => resolve(true)));
  });
}

/**
 * Attach to a dashboard already running on `port`, or start the engine's `serve` on the first free port from there.
 * `onStatus` gets progress lines for the console before the terminal UI takes over.
 */
export async function startDashboard(
  engine: Engine,
  { runs, host, port, viewer, home }: DashboardOptions,
  onStatus: (line: string) => void = () => {},
): Promise<Dashboard> {
  const owned = home ? reapOrphan(home) : null;
  for (let p = port; p < port + 20; p++) {
    const url = `http://${host}:${p}/`;
    if (await isDashboard(url.slice(0, -1))) {
      // Another terminal home's dashboard on a different runs folder isn't ours to reuse: try the next port.
      if (owned && owned.url === url && owned.runs !== runs) continue;
      return { url, origin: "attached", proc: null };
    }
    if (!(await portFree(host, p))) continue;
    onStatus(`starting the dashboard on ${url} …`);
    const proc = Bun.spawn(
      [...engine.cmd, "serve", "--runs", runs, "--host", host, "--port", String(p), "--no-open"],
      { stdout: "ignore", stderr: "pipe", env: viewer ? { ...process.env, APPSCREENMAP_WEB: viewer } : process.env },
    );
    const deadline = Date.now() + 30_000;
    while (Date.now() < deadline) {
      if (proc.exitCode !== null) {
        const err = (await new Response(proc.stderr).text()).trim();
        throw new Error(err.split("\n").slice(-3).join("\n") || `the dashboard exited (code ${proc.exitCode})`);
      }
      if (await isDashboard(url.slice(0, -1), 500)) {
        home?.writeJson(home.dashboardFile, { pid: proc.pid, cliPid: process.pid, url, runs } satisfies DashboardRecord);
        return { url, origin: "spawned", proc };
      }
      await Bun.sleep(200);
    }
    proc.kill();
    throw new Error("the dashboard did not start within 30 s");
  }
  throw new Error(`no free port between ${port} and ${port + 19}`);
}

/** Stop the dashboard if this CLI started it; leave one it attached to running. */
export function stopDashboard(d: Dashboard | null, home?: Home): void {
  if (d?.origin !== "spawned" || !d.proc) return;
  if (d.proc.exitCode === null) d.proc.kill();
  const rec = home?.readJson<DashboardRecord>(home.dashboardFile);
  if (home && rec?.pid === d.proc.pid && existsSync(home.dashboardFile)) rmSync(home.dashboardFile, { force: true });
}

/** Open a URL in the default browser. False when there's no opener (headless Linux, CI). */
export function openUrl(url: string): boolean {
  const opener = process.platform === "darwin" ? "open" : Bun.which("xdg-open") ? "xdg-open" : null;
  if (!opener) return false;
  Bun.spawn([opener, url], { stdout: "ignore", stderr: "ignore" });
  return true;
}
