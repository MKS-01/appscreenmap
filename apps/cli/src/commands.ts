// `setup`, `update`, `paths`, `clean`: plain console commands (no terminal UI).
import { existsSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join, relative, resolve } from "node:path";
import { applyClean, cleanInput, human, planClean } from "./clean";
import { checkoutRoot, engineVersion, findEngine, runEngine, shareViewer, viewerDir, type Engine } from "./engine";
import { Home } from "./home";
import { confirm, out } from "./out";
import {
  DEFAULT_RELEASE_URL,
  fetchManifest,
  installCli,
  installEngine,
  installViewer,
  planIsEmpty,
  planUpdate,
  releaseUrl,
  type Installed,
  type Manifest,
} from "./release";
import { readRuns } from "./runs";

/** True for the compiled binary (it can replace itself); false when run from source with `bun run`. */
export const isCompiled = () => import.meta.dir.startsWith("/$bunfs");

const tilde = (p: string) => (p.startsWith(homedir()) ? `~${p.slice(homedir().length)}` : p);

/** Run a command in this terminal; true when it exits 0. */
async function run(cmd: string[], cwd?: string): Promise<boolean> {
  return (await Bun.spawn(cmd, { cwd, stdio: ["inherit", "inherit", "inherit"] }).exited) === 0;
}

function uvPath(): string | null {
  return Bun.which("uv") ?? [join(homedir(), ".local", "bin", "uv"), join(homedir(), ".cargo", "bin", "uv")].find(existsSync) ?? null;
}

async function ensureUv(yes: boolean): Promise<string | null> {
  const uv = uvPath();
  if (uv) {
    out.ok(`uv ${(Bun.spawnSync([uv, "--version"]).stdout.toString().trim().split(" ")[1] ?? "")}`.trim());
    return uv;
  }
  const brew = Bun.which("brew");
  const how = brew ? "brew install uv" : "curl -LsSf https://astral.sh/uv/install.sh | sh";
  out.warn(`uv (Astral's Python package manager) is needed to install and run the engine`);
  if (!(await confirm(`Install it now with \`${how}\`?`, yes))) {
    out.skip(`not installed; run ${out.cmd(how)}, then ${out.cmd("appscreenmap setup")} again`);
    return null;
  }
  const done = brew ? await run([brew, "install", "uv"]) : await run(["/bin/sh", "-c", how]);
  const now = done ? uvPath() : null;
  now ? out.ok(`uv installed (${tilde(now)})`) : out.bad("uv didn't install; see the output above");
  return now;
}

async function manifestOrExplain(base: string): Promise<Manifest | null> {
  try {
    return await fetchManifest(base);
  } catch (e) {
    if (base === DEFAULT_RELEASE_URL) {
      out.bad("No AppScreenMap release is published yet.");
      out.dim(`    From a source checkout: ${out.cmd("make setup")} (or ${out.cmd("appscreenmap setup")} inside it).`);
    } else out.bad(`No release at ${base}: ${e instanceof Error ? e.message : e}`);
    return null;
  }
}

// ── setup ────────────────────────────────────────────────────────────────────

export async function cmdSetup({ yes }: { yes: boolean }): Promise<number> {
  out.title("AppScreenMap setup");
  const home = new Home();
  const root = checkoutRoot();
  let failed = false;

  if (root) {
    out.dim(`  source checkout: ${tilde(root)}`);
    const uv = await ensureUv(yes);
    if (!uv) return 1;
    out.step("uv sync (the Python workspace)");
    if (!(await run([uv, "sync"], root))) failed = true;
    const bun = Bun.which("bun");
    if (!bun) {
      out.bad(`bun not found: ${out.cmd("brew install oven-sh/bun/bun")} (it builds the dashboard)`);
      failed = true;
    } else {
      out.step("bun install (the TypeScript workspace)");
      if (!(await run([bun, "install"], root))) failed = true;
      if (existsSync(join(root, "apps", "viewer", "dist", "index.html"))) out.ok("dashboard built (apps/viewer/dist)");
      else {
        out.step("building the dashboard (apps/viewer)");
        (await run([bun, "run", "build"], join(root, "apps", "viewer"))) ? out.ok("dashboard built") : (failed = true);
      }
    }
  } else {
    const base = releaseUrl(process.env, home.config());
    out.dim(`  release: ${base}`);
    const uv = await ensureUv(yes);
    if (!uv) return 1;
    const m = await manifestOrExplain(base);
    if (!m) return 1;
    const engine = findEngine();
    const have = engine ? await engineVersion(engine) : null;
    if (engine && have === m.engine.version) out.ok(`engine ${have}`);
    else {
      out.step(`installing engine ${m.engine.version} (uv tool) …`);
      (await installEngine(home, base, m, uv)) === 0 ? out.ok(`engine ${m.engine.version}`) : ((failed = true), out.bad("engine install failed"));
    }
    if (home.currentViewer() === m.viewer.version && home.currentViewerDir()) out.ok(`dashboard ${m.viewer.version}`);
    else {
      try {
        out.step(`installing dashboard ${m.viewer.version} …`);
        await installViewer(home, base, m);
        out.ok(`dashboard ${m.viewer.version} (${tilde(home.currentViewerDir() ?? "")})`);
      } catch (e) {
        failed = true;
        out.bad(`dashboard: ${e instanceof Error ? e.message : e}`);
      }
    }
  }

  const engine = findEngine();
  shareViewer(home.currentViewerDir()); // the dashboard just installed, for doctor below
  if (engine) {
    out.dim("\n  Devices and tools (appscreenmap doctor):");
    await runEngine(engine, ["doctor"]); // missing devices or optional tools aren't a setup failure
  } else failed = true;
  console.log(failed ? "" : `\nReady. Run ${out.cmd("appscreenmap")} for the terminal home and the dashboard.`);
  return failed ? 1 : 0;
}

// ── update ───────────────────────────────────────────────────────────────────

type Part = "cli" | "engine" | "viewer";

export async function installedState(version: string, engine: Engine | null, home: Home): Promise<Installed> {
  const viewer = viewerDir(home.currentViewerDir());
  return {
    cli: version,
    cliCompiled: isCompiled(),
    engine: engine ? await engineVersion(engine) : null,
    engineSource: engine?.source ?? null,
    viewer: viewer?.source === "home" ? home.currentViewer() : null,
    viewerSource: viewer?.source ?? null,
  };
}

export async function cmdUpdate(version: string, mapSchema: number, { check, only }: { check: boolean; only: Part | null }): Promise<number> {
  const home = new Home();
  const engine = findEngine();
  if (!isCompiled() && engine?.source === "checkout") {
    console.log(`Running from a source checkout: update it with ${out.cmd("git pull && make setup")}.`);
    return 0;
  }
  const base = releaseUrl(process.env, home.config());
  const m = await manifestOrExplain(base);
  if (!m) return 1;
  const installed = await installedState(version, engine, home);
  const plan = planUpdate(installed, m, mapSchema);
  if (only) for (const p of ["cli", "engine", "viewer"] as Part[]) if (p !== only) delete plan[p];

  out.title(`AppScreenMap ${m.version} is the latest release`);
  const row = (part: Part, label: string, have: string | null) => {
    const step = plan[part];
    if (step) out.warn(`${label.padEnd(9)} ${have ?? "not installed"} → ${step.to}`);
    else out.ok(`${label.padEnd(9)} ${have ?? (part === "viewer" && installed.viewerSource === "checkout" ? "source checkout" : "—")}`);
  };
  row("cli", "cli", installed.cli);
  row("engine", "engine", installed.engine);
  row("viewer", "dashboard", installed.viewer);
  for (const note of plan.notes) out.skip(note);
  if (planIsEmpty(plan)) {
    console.log("\nUp to date.");
    return 0;
  }
  if (check) {
    console.log(`\nRun ${out.cmd("appscreenmap update")} to install.`);
    return 0;
  }

  let failed = false;
  if (plan.engine) {
    const uv = uvPath();
    if (!uv) {
      out.bad(`uv not found: ${out.cmd("appscreenmap setup")} installs it`);
      failed = true;
    } else if ((await installEngine(home, base, m, uv)) !== 0) failed = true;
    else out.ok(`engine ${m.engine.version}`);
  }
  if (plan.viewer) {
    try {
      await installViewer(home, base, m);
      out.ok(`dashboard ${m.viewer.version} (restart the terminal home to serve it)`);
    } catch (e) {
      failed = true;
      out.bad(`dashboard: ${e instanceof Error ? e.message : e}`);
    }
  }
  if (plan.cli) {
    try {
      await installCli(base, m); // last: it replaces this binary
      out.ok(`cli ${m.cli.version}`);
    } catch (e) {
      failed = true;
      out.bad(`cli: ${e instanceof Error ? e.message : e}`);
    }
  }
  return failed ? 1 : 0;
}

// ── paths ────────────────────────────────────────────────────────────────────

export async function cmdPaths(runs: string): Promise<number> {
  const home = new Home();
  const engine = findEngine();
  const viewer = viewerDir(home.currentViewerDir());
  const runsRoot = resolve(runs);
  const show = (k: string, v: string) => console.log(`  ${k.padEnd(10)} ${v}`);
  out.title("AppScreenMap paths");
  show("home", tilde(home.dir));
  show("config", tilde(home.configFile));
  show("dashboard", viewer ? `${tilde(viewer.dir)}${viewer.source === "home" ? ` (viewer ${home.currentViewer()})` : " (source checkout)"}` : "not installed: appscreenmap setup");
  show("cache", tilde(home.cacheDir));
  show("runs", relative(process.cwd(), runsRoot) || ".");
  show("logs", relative(process.cwd(), join(runsRoot, ".logs")));
  show("engine", engine ? `${engine.cmd.map(tilde).join(" ")} (${engine.source})` : "not installed: appscreenmap setup");
  show("cli", isCompiled() ? tilde(process.execPath) : "running from source (bun run)");
  show("release", releaseUrl(process.env, home.config()));
  return 0;
}

// ── clean ────────────────────────────────────────────────────────────────────

export async function cmdClean(o: { runs: string; includeRuns: boolean; olderThanDays: number; dryRun: boolean; yes: boolean }): Promise<number> {
  const home = new Home();
  const runsRoot = resolve(o.runs);
  const items = planClean(cleanInput(home, runsRoot, readRuns(runsRoot), o.includeRuns, o.olderThanDays));
  out.title(`AppScreenMap clean${o.dryRun ? " (dry run)" : ""}`);
  if (!items.length) {
    console.log(`  Nothing to remove.${o.includeRuns ? "" : ` (Old runs are kept unless you pass ${out.cmd("--runs")}.)`}`);
    return 0;
  }
  for (const i of items) console.log(`  ${i.label.padEnd(56)} ${human(i.bytes).padStart(8)}`);
  const total = items.reduce((n, i) => n + i.bytes, 0);
  console.log(`  ${"total".padEnd(56)} ${human(total).padStart(8)}`);
  if (o.dryRun) return 0;
  const runCount = items.filter((i) => i.kind === "run").length;
  const question = `Remove ${items.length} item(s)${runCount ? `, including ${runCount} run(s) and their screenshots` : ""}?`;
  if (!(await confirm(question, o.yes))) {
    console.log(process.stdin.isTTY ? "  Kept everything." : `  Kept everything (pass ${out.cmd("--yes")} to remove without asking).`);
    return 0;
  }
  applyClean(items, runsRoot);
  out.ok(`removed ${items.length} item(s), ${human(total)}`);
  return 0;
}

/** For `version`: the viewer the dashboard would serve. */
export function viewerLabel(home = new Home()): string {
  const v = viewerDir(home.currentViewerDir());
  if (!v) return "not installed";
  if (v.source === "home") return home.currentViewer() ?? "installed";
  try {
    return `${JSON.parse(readFileSync(join(v.dir, "..", "package.json"), "utf8")).version} (source checkout)`;
  } catch {
    return "source checkout";
  }
}
