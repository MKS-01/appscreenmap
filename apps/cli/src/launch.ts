// Commands started from the terminal home (`x`): run in the background with their output in runs/.logs/ (the engine's
// run scanner skips dot folders), so the terminal UI keeps drawing. The live panel follows the run the crawl records.
import { closeSync, mkdirSync, openSync } from "node:fs";
import { join } from "node:path";
import type { Subprocess } from "bun";
import type { Suggestion } from "./content";
import type { Engine } from "./engine";

export interface Launched {
  label: string;
  log: string;
  proc: Subprocess;
}

const started = new Set<Launched>();

/** The command line for a runnable suggestion; crawls write into the runs folder the terminal home watches. */
export function commandFor(engine: Engine, s: Suggestion, runsRoot: string): string[] | null {
  if (s.engine) {
    const args = s.engine[0] === "crawl" && !s.engine.includes("--out") ? [...s.engine, "--out", runsRoot] : s.engine;
    return [...engine.cmd, ...args];
  }
  return s.shell ? ["/bin/sh", "-c", s.shell] : null;
}

export function launch(engine: Engine, s: Suggestion, runsRoot: string, cwd: string): Launched | null {
  const cmd = commandFor(engine, s, runsRoot);
  if (!cmd) return null;
  const logs = join(runsRoot, ".logs");
  mkdirSync(logs, { recursive: true });
  const stamp = new Date().toISOString().replace(/[-:]/g, "").replace(/\..*/, "").replace("T", "-");
  const log = join(logs, `${s.engine?.[0] ?? "command"}-${stamp}.log`);
  const fd = openSync(log, "a");
  const proc = Bun.spawn(cmd, { cwd, env: { ...process.env, APPSCREENMAP_SOURCE: "cli", ...s.env }, stdin: "ignore", stdout: fd, stderr: fd });
  closeSync(fd); // the child keeps its own copy
  const item = { label: s.cmd, log, proc };
  started.add(item);
  proc.exited.then(() => started.delete(item));
  return item;
}

/** Ctrl-C for a command started here: a crawl saves what it has and records the run as `stopped`. */
export function stop(item: Launched): void {
  if (item.proc.exitCode === null) item.proc.kill("SIGINT");
}

/** On quit: stop everything this terminal home started and wait briefly for it to save. */
export async function stopAll(timeoutMs = 5000): Promise<void> {
  const running = [...started].filter((s) => s.proc.exitCode === null);
  running.forEach(stop);
  await Promise.race([Promise.all(running.map((s) => s.proc.exited)), Bun.sleep(timeoutMs)]);
}
