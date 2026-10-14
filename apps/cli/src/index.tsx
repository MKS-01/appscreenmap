// `appscreenmap`: the terminal home (`start`, the default) and the front door to the engine. Every other command is
// handed to the Python engine unchanged, so `appscreenmap crawl …` works the same as before.
import React from "react";
import { render } from "ink";
import { resolve } from "node:path";
import { version } from "../package.json";
import { openUrl, startDashboard, stopDashboard, type Dashboard } from "./dashboard";
import { ENGINE_MISSING, engineVersion, findEngine, runEngine, type Engine } from "./engine";
import { App, MAP_SCHEMA } from "./ui/App";

const HELP = `appscreenmap ${version}: map every screen of a mobile app

  appscreenmap [start]      terminal home, with the dashboard open in your browser
      --runs DIR            runs folder (default ./runs)
      --port N --host H     dashboard address (default 127.0.0.1:8765; the next free port if taken)
      --no-open             don't open the browser
  appscreenmap version      CLI, engine and map schema versions
  appscreenmap <command>    doctor, crawl, export, diff, verify, report, perf, a11y, security, serve, mcp:
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

async function start(engine: Engine, flags: StartFlags): Promise<number> {
  const runsRoot = resolve(flags.runs);
  if (!process.stdout.isTTY || !process.stdin.isTTY) {
    // No terminal to draw in (piped, CI): just serve the dashboard.
    const args = ["serve", "--runs", runsRoot, "--host", flags.host, "--port", String(flags.port)];
    return runEngine(engine, flags.open ? args : [...args, "--no-open"]);
  }
  let dashboard: Dashboard | null = null;
  let dashboardError: string | null = null;
  try {
    dashboard = await startDashboard(engine, { runs: runsRoot, host: flags.host, port: flags.port }, (l) =>
      console.log(dim(l)),
    );
  } catch (e) {
    dashboardError = e instanceof Error ? e.message : String(e);
  }
  const opened = Boolean(dashboard && flags.open && dashboard.origin === "spawned" && openUrl(dashboard.url));
  const stop = () => stopDashboard(dashboard);
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
    />,
  );
  // On resize the old frame re-wraps and ink erases the wrong lines: start each repaint from a blank screen.
  process.stdout.prependListener("resize", () => {
    ink.clear();
    process.stdout.write("\x1b[2J\x1b[3J\x1b[H");
  });
  await ink.waitUntilExit();
  stop();
  return 0;
}

async function main(argv: string[]): Promise<number> {
  const [cmd, ...rest] = argv;
  if (cmd === "help" || cmd === "--help" || cmd === "-h") {
    console.log(HELP);
    return 0;
  }
  const engine = findEngine();
  if (cmd === "version" || cmd === "--version" || cmd === "-V") {
    const ev = engine ? await engineVersion(engine) : null;
    console.log(`appscreenmap ${version}\n  engine      ${ev ?? "not found"}\n  map schema  ${MAP_SCHEMA}`);
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
