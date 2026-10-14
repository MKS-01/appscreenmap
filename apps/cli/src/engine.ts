// The Python engine (apps/engine) does the crawling and analysis; this CLI finds it and hands commands over unchanged.
import { existsSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join } from "node:path";

export interface Engine {
  cmd: string[];
  source: "env" | "checkout" | "path";
}

// `make cli` bakes the checkout path in (--define), because a compiled binary can't see where its source lives.
const BAKED_ROOT = process.env.APPSCREENMAP_ROOT;

/** The monorepo root at or above `start` (a uv workspace with apps/engine), or null. */
export function findCheckout(start: string): string | null {
  let dir = start;
  for (let i = 0; i < 16; i++) {
    const pyproject = join(dir, "pyproject.toml");
    if (
      existsSync(pyproject) &&
      existsSync(join(dir, "apps", "engine", "pyproject.toml")) &&
      readFileSync(pyproject, "utf8").includes("[tool.uv.workspace]")
    ) {
      return dir;
    }
    const up = dirname(dir);
    if (up === dir) break;
    dir = up;
  }
  return null;
}

/** The checkout this CLI belongs to (its source folder, or the path `make cli` baked in), or null. */
export function checkoutRoot(here = import.meta.dir, baked = BAKED_ROOT): string | null {
  return findCheckout(here) ?? (baked ? findCheckout(baked) : null);
}

/**
 * Tell the engine (every command this CLI runs) where the dashboard installed in the home folder is, so `serve` and
 * `doctor` find it outside a source checkout. A checkout's own build is found by the engine itself.
 */
export function shareViewer(homeViewer: string | null, root = checkoutRoot()): void {
  const v = viewerDir(homeViewer, root);
  if (v?.source === "home" && !process.env.APPSCREENMAP_WEB) process.env.APPSCREENMAP_WEB = v.dir;
}

/** The built viewer to serve: the checkout's `apps/viewer/dist`, else the home folder's active version. */
export function viewerDir(homeViewer: string | null, root = checkoutRoot()): { dir: string; source: "checkout" | "home" } | null {
  const dist = root ? join(root, "apps", "viewer", "dist") : null;
  if (dist && existsSync(join(dist, "index.html"))) return { dir: dist, source: "checkout" };
  return homeViewer ? { dir: homeViewer, source: "home" } : null;
}

interface FindOptions {
  env?: Record<string, string | undefined>;
  here?: string;
  baked?: string;
  which?: (bin: string) => string | null;
  toolBin?: string; // where `uv tool install` puts commands (UV_TOOL_BIN_DIR, default ~/.local/bin), not always on PATH
}

/**
 * Where the engine is, in order: $APPSCREENMAP_ENGINE, this CLI's own checkout (via uv), `appscreenmap-engine` on
 * PATH, then uv's tool folder (where `appscreenmap setup` installs it).
 */
export function findEngine({
  env = process.env,
  here = import.meta.dir,
  baked = BAKED_ROOT,
  which = Bun.which,
  toolBin = env.UV_TOOL_BIN_DIR || join(env.HOME || homedir(), ".local", "bin"),
}: FindOptions = {}): Engine | null {
  if (env.APPSCREENMAP_ENGINE) {
    return { cmd: env.APPSCREENMAP_ENGINE.split(/\s+/).filter(Boolean), source: "env" };
  }
  const root = checkoutRoot(here, baked);
  if (root && which("uv")) {
    return { cmd: ["uv", "run", "--quiet", "--project", root, "appscreenmap-engine"], source: "checkout" };
  }
  const bin = which("appscreenmap-engine") ?? (existsSync(join(toolBin, "appscreenmap-engine")) ? join(toolBin, "appscreenmap-engine") : null);
  return bin ? { cmd: [bin], source: "path" } : null;
}

export const ENGINE_MISSING = [
  "The AppScreenMap engine isn't installed.",
  "  install it:              appscreenmap setup",
  "  from a source checkout:  make setup",
  "  or point at one:         APPSCREENMAP_ENGINE='uv run --project <checkout> appscreenmap-engine'",
].join("\n");

/** Run an engine command in this terminal and return its exit code. */
export async function runEngine(engine: Engine, args: string[]): Promise<number> {
  const proc = Bun.spawn([...engine.cmd, ...args], { stdio: ["inherit", "inherit", "inherit"], env: { ...process.env } });
  // Ctrl-C reaches the engine as well (same process group): let it save and stop, then the caller exits with its
  // code. Every caller exits right after, so the no-op handler is never removed.
  process.on("SIGINT", () => {});
  return proc.exited;
}

/** The engine's version ("0.1.0"), or null if it can't be read. */
export async function engineVersion(engine: Engine): Promise<string | null> {
  try {
    const proc = Bun.spawn([...engine.cmd, "--version"], { stdout: "pipe", stderr: "ignore" });
    const out = await new Response(proc.stdout).text();
    await proc.exited;
    return out.match(/(\d+\.\d+\.\d+\S*)/)?.[1] ?? null;
  } catch {
    return null;
  }
}
