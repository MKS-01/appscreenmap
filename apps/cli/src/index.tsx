// `appscreenmap`: the terminal home (`start`, the default) and the front door to the engine. Every other command is
// handed to the Python engine unchanged, so `appscreenmap crawl …` works the same as before.
import React from "react";
import { render } from "ink";
import { resolve } from "node:path";
import { version } from "../package.json";
import { openUrl, startDashboard, stopDashboard, type Dashboard } from "./dashboard";
import { ENGINE_MISSING, engineVersion, findEngine, runEngine, shareViewer, viewerDir, type Engine } from "./engine";
import { cmdClean, cmdPaths, cmdSetup, cmdUpdate, installedState, viewerLabel } from "./commands";
import { stopAll } from "./launch";
import { Home } from "./home";
import { latestManifest, planIsEmpty, planUpdate, releaseUrl, updateCheckEnabled } from "./release";
import { App, MAP_SCHEMA } from "./ui/App";

const HELP = `appscreenmap ${version}: map every screen of a mobile app

  appscreenmap [start]      terminal home, with the dashboard open in your browser
      --runs DIR            runs folder (default ./runs)
      --port N --host H     dashboard address (default 127.0.0.1:8765; the next free port if taken)
      --no-open             don't open the browser
  appscreenmap setup        install or repair everything: uv, the engine, the dashboard (asks before installing uv)
      --yes                 don't ask
  appscreenmap update       install the newest release's cli, engine and dashboard
      --check               only say what's newer          cli | engine | viewer   only that part
  appscreenmap paths        where AppScreenMap keeps things (home folder, dashboard, runs, engine)
  appscreenmap clean        remove old dashboard versions, the download cache and old logs (asks first)
      --runs                also finished runs older than --older-than days (default 30)
      --dry-run  --yes  --runs-dir DIR
  appscreenmap version      CLI, engine, dashboard and map schema versions
  appscreenmap logs         follow what every command is doing, whoever started it (you, an agent, MCP, CI)
      --source agent  --cmd crawl  --level warn  --run ID  --no-follow  --json
  appscreenmap <command>    doctor, crawl, export, diff, verify, report, perf, a11y, security, store, merge, serve, mcp:
                            run by the engine (\`appscreenmap <command> --help\` for its options)
`;

const dim = (s: string) => `\x1b[2m${s}\x1b[0m`;

interface StartFlags {
  runs: string;
  host: string;
  port: number;
  open: boolean;
}

function parseStart(args: string[]): StartFlags | string {
  const flags: StartFlags = { runs: "runs", host: "127.0.0.1", port: 8765, open: true };
  for (let i = 0; i < args.length; i++) {
    const a = args[i]!;
    const next = () => args[++i] ?? "";
    if (a === "--runs") flags.runs = next();
    else if (a === "--host") flags.host = next();
    else if (a === "--port") flags.port = Number(next());
    else if (a === "--no-open") flags.open = false;
    else return `unknown option for start: ${a}\n\n${HELP}`;
  }
  if (!Number.isInteger(flags.port) || flags.port <= 0) return `--port needs a number\n\n${HELP}`;
  return flags;
}

/** A one-line notice when a newer release is out (checked at most daily; never installs anything by itself). */
async function updateNotice(engine: Engine, home: Home): Promise<string | null> {
  if (!updateCheckEnabled(home) || engine.source === "checkout") return null; // a checkout updates with git pull
  const m = await latestManifest(home, releaseUrl(process.env, home.config()));
  if (!m) return null;
  const plan = planUpdate(await installedState(version, engine, home), m, MAP_SCHEMA);
  if (planIsEmpty(plan)) return null;
  const parts = (["cli", "engine", "viewer"] as const).flatMap((k) => (plan[k] ? [`${k === "viewer" ? "dashboard" : k} ${plan[k]!.to}`] : []));
  return `update available: ${parts.join(", ")}`;
}

async function start(engine: Engine, flags: StartFlags): Promise<number> {
  const runsRoot = resolve(flags.runs);
  const home = new Home();
  const viewer = viewerDir(home.currentViewerDir());
  if (!process.stdout.isTTY || !process.stdin.isTTY) {
    // No terminal to draw in (piped, CI): just serve the dashboard.
    const args = ["serve", "--runs", runsRoot, "--host", flags.host, "--port", String(flags.port)];
    return runEngine(engine, flags.open ? args : [...args, "--no-open"]);
  }
  let dashboard: Dashboard | null = null;
  let dashboardError: string | null = null;
  try {
    dashboard = await startDashboard(
      engine,
      { runs: runsRoot, host: flags.host, port: flags.port, viewer: viewer?.dir ?? null, home },
      (l) => console.log(dim(l)),
    );
  } catch (e) {
    dashboardError = e instanceof Error ? e.message : String(e);
    if (!viewer) dashboardError = "the dashboard isn't installed: appscreenmap setup";
  }
  const opened = Boolean(dashboard && flags.open && dashboard.origin === "spawned" && openUrl(dashboard.url));
  const stop = () => stopDashboard(dashboard, home);
  process.on("exit", stop);
  process.on("SIGTERM", () => process.exit(0));

  console.clear();
  const ink = render(
    <App
      version={version}
      engine={engine}
      dashboard={dashboard}
      dashboardError={dashboardError}
      opened={opened}
      runsRoot={runsRoot}
      cwd={process.cwd()}
      updateNotice={updateNotice(engine, home).catch(() => null)}
    />,
  );
  // On resize the old frame re-wraps and ink erases the wrong lines: start each repaint from a blank screen.
  process.stdout.prependListener("resize", () => {
    ink.clear();
    process.stdout.write("\x1b[2J\x1b[3J\x1b[H");
  });
  await ink.waitUntilExit();
  await stopAll(); // a crawl started here saves and records its run as stopped
  stop();
  return 0;
}

async function main(argv: string[]): Promise<number> {
  const [cmd, ...rest] = argv;
  if (cmd === "help" || cmd === "--help" || cmd === "-h") {
    console.log(HELP);
    return 0;
  }
  shareViewer(new Home().currentViewerDir());
  const flag = (name: string) => rest.includes(name);
  const option = (name: string, fallback: string) => {
    const i = rest.indexOf(name);
    return i >= 0 && rest[i + 1] ? rest[i + 1]! : fallback;
  };
  if (cmd === "setup") return cmdSetup({ yes: flag("--yes") });
  if (cmd === "update") {
    const only = rest.find((a) => a === "cli" || a === "engine" || a === "viewer") as "cli" | "engine" | "viewer" | undefined;
    return cmdUpdate(version, MAP_SCHEMA, { check: flag("--check"), only: only ?? null });
  }
  if (cmd === "paths") return cmdPaths(option("--runs", "runs"));
  if (cmd === "clean") {
    const days = Number(option("--older-than", "30"));
    if (!Number.isFinite(days) || days < 0) return console.error("--older-than needs a number of days"), 2;
    return cmdClean({ runs: option("--runs-dir", "runs"), includeRuns: flag("--runs"), olderThanDays: days, dryRun: flag("--dry-run"), yes: flag("--yes") });
  }
  const engine = findEngine();
  if (cmd === "version" || cmd === "--version" || cmd === "-V") {
    const ev = engine ? await engineVersion(engine) : null;
    console.log(
      `appscreenmap ${version}\n  engine      ${ev ?? "not installed: appscreenmap setup"}\n  dashboard   ${viewerLabel()}\n  map schema  ${MAP_SCHEMA}`,
    );
    return 0;
  }
  if (!engine) {
    console.error(ENGINE_MISSING);
    return 1;
  }
  if (cmd === undefined || cmd === "start" || cmd.startsWith("--")) {
    const flags = parseStart(cmd === "start" ? rest : argv);
    if (typeof flags === "string") {
      console.error(flags);
      return 2;
    }
    return start(engine, flags);
  }
  return runEngine(engine, argv);
}

process.exit(await main(process.argv.slice(2)));
