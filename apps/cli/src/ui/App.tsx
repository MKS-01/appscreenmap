import React, { useEffect, useMemo, useRef, useState } from "react";
import { Box, Text, useApp, useInput, useStdout } from "ink";
import { existsSync } from "node:fs";
import { join, relative } from "node:path";
import { AGENT, crawlSuggestions, runCommands, runnable, type Suggestion } from "../content";
import { openUrl, type Dashboard } from "../dashboard";
import { androidDevices, simulators, type AndroidDevice, type Simulator } from "../devices";
import { engineVersion, type Engine } from "../engine";
import { launch, stop, type Launched } from "../launch";
import { nextStep, readReadiness, type Readiness } from "../readiness";
import { readRuns, runUrl, type RunSummary } from "../runs";
import { MAP_SCHEMA_VERSION } from "../schema";
import { copy, openTerminal } from "../system";
import { C } from "../theme";
import { readProgress, runEvents, tail, type Progress } from "../watch";
import { Field, LABEL_W, Live, LogTail, ReadinessPanel, RunRow, SuggestionList, statusTone, type Tone } from "./parts";

export const MAP_SCHEMA = MAP_SCHEMA_VERSION;
const TABS = ["home", "crawl", "runs", "agent"] as const;
const POLL_MS = 1000;

const stripAnsi = (s: string) => s.replace(/\x1b\[[0-9;?]*[A-Za-z]/g, "");

export interface AppProps {
  version: string;
  engine: Engine;
  dashboard: Dashboard | null;
  dashboardError: string | null;
  opened: boolean;
  runsRoot: string;
  cwd: string;
  updateNotice?: Promise<string | null>;
}

export function App({ version, engine, dashboard, dashboardError, opened, runsRoot, cwd, updateNotice }: AppProps) {
  const { exit } = useApp();
  const { stdout } = useStdout();
  const [tab, setTab] = useState(0);
  const [sel, setSel] = useState([0, 0, 0, 0]);
  const [flash, setFlash] = useState<{ text: string; tone: Tone } | null>(null);
  const [runs, setRuns] = useState<RunSummary[]>(() => readRuns(runsRoot));
  const [readiness, setReadiness] = useState<Readiness | null>(() => (runs[0] ? readReadiness(runsRoot, runs[0]) : null));
  const [android, setAndroid] = useState<AndroidDevice[] | null | undefined>(undefined);
  const [sims, setSims] = useState<Simulator[] | null | undefined>(undefined);
  const [engineVer, setEngineVer] = useState<string | null>(null);
  const [progress, setProgress] = useState<Progress | null>(null);
  const [launched, setLaunched] = useState<Launched | null>(null);
  const [launchedExit, setLaunchedExit] = useState<string | null>(null);
  const [logLines, setLogLines] = useState<string[]>([]);
  const [update, setUpdate] = useState<string | null>(null);
  const prevRuns = useRef(runs);

  const inCheckout = useMemo(() => existsSync(join(cwd, "samples", "playground-app", "apk", "playground-v1.apk")), [cwd]);
  const crawlItems = useMemo(() => crawlSuggestions(inCheckout), [inCheckout]);
  const say = (text: string, tone: Tone = "good") => setFlash({ text, tone });

  const refreshDevices = () => {
    androidDevices().then(setAndroid);
    simulators().then(setSims);
  };

  // Every second: new or finished runs (a crawl here, or an agent's in another terminal), the live crawl, and the
  // latest run's readiness (an audit run elsewhere shows up as soon as it writes its file).
  useEffect(() => {
    refreshDevices();
    engineVersion(engine).then(setEngineVer);
    updateNotice?.then(setUpdate);
    const tick = () => {
      const next = readRuns(runsRoot);
      for (const ev of runEvents(prevRuns.current, next)) {
        if (ev.kind === "started") say(`${ev.run.app} is being mapped: ${ev.run.id} (live on the crawl tab)`, "warn");
        else {
          say(`${ev.run.id} ${ev.run.status}: ${ev.run.screens} screens`, statusTone(ev.run.status));
          setProgress(readProgress(runsRoot, ev.run)); // keep the final numbers on screen
        }
      }
      prevRuns.current = next;
      setRuns(next);
      setReadiness(next[0] ? readReadiness(runsRoot, next[0]) : null);
      const live = next.find((r) => r.status === "running");
      if (live) setProgress(readProgress(runsRoot, live));
    };
    const timer = setInterval(tick, POLL_MS);
    return () => clearInterval(timer);
  }, []);

  // Output of a command started here, until it records a run (or for good, if it doesn't record one).
  useEffect(() => {
    if (!launched) return;
    const read = () => setLogLines(tail(launched.log, 8).map(stripAnsi));
    read();
    const timer = setInterval(read, POLL_MS);
    launched.proc.exited.then((code) => {
      read();
      setLaunchedExit(String(code));
    });
    return () => clearInterval(timer);
  }, [launched]);

  const runsShown = relative(cwd, runsRoot).startsWith("..") ? runsRoot : relative(cwd, runsRoot) || ".";
  const runDir = (r: RunSummary) => join(runsShown, r.path);
  const crawling = runs.some((r) => r.status === "running");
  const ready = (android ?? []).filter((d) => d.state === "device");
  const latest = runs[0] ?? null;
  const next = nextStep({
    dashboardOk: dashboard !== null,
    devices: ready.length + (sims?.length ?? 0),
    crawling,
    latest: latest ? { status: latest.status, platform: latest.platform, dir: runDir(latest) } : null,
    readiness,
    inCheckout,
  });
  const lengths = [0, crawlItems.length, runs.length, AGENT.length];
  const current = sel[tab] ?? 0;
  const launchedRunning = launched !== null && launchedExit === null;
  const copyCmd = (cmd: string) => (copy(cmd) ? say(`copied: ${cmd}`) : say(`no clipboard tool here; run: ${cmd}`, "warn"));

  const start = (item: Suggestion) => {
    if (!runnable(item)) return say("this one needs editing first: c copies it", "warn");
    if (launchedRunning) return say("a command started here is still running: s stops it", "warn");
    const started = launch(engine, item, runsRoot, cwd);
    if (!started) return;
    setLaunchedExit(null);
    setLogLines([]);
    setProgress(null);
    setLaunched(started);
    setTab(1);
    say(`started: ${item.cmd}`, "warn");
  };

  const selectedCmd = (): string | null => {
    if (tab === 0) return next.cmd;
    if (tab === 1) return crawlItems[current]?.cmd ?? null;
    if (tab === 3) return AGENT[current]?.cmd ?? null;
    const run = runs[current];
    return run ? runCommands(runDir(run))[0]!.cmd : null;
  };

  useInput((input, key) => {
    if (input === "q" || key.escape) return exit();
    const digit = Number(input);
    if (digit >= 1 && digit <= TABS.length) return setTab(digit - 1);
    if (key.rightArrow || key.tab) return setTab((t) => (t + 1) % TABS.length);
    if (key.leftArrow) return setTab((t) => (t + TABS.length - 1) % TABS.length);
    if (key.upArrow || key.downArrow) {
      const n = lengths[tab] ?? 0;
      if (!n) return;
      return setSel((s) => s.map((v, i) => (i === tab ? (v + (key.downArrow ? 1 : n - 1)) % n : v)));
    }
    if (input === "c") {
      const cmd = selectedCmd();
      return cmd ? copyCmd(cmd) : undefined;
    }
    if (input === "x") {
      if (tab === 0) return next.cmd === "2 crawl" ? setTab(1) : start(next);
      if (tab === 1) return start(crawlItems[current]!);
      return;
    }
    if (input === "s" && tab === 1) {
      if (!launchedRunning) return say("nothing started here is running (a crawl from another terminal stops there)", "faint");
      stop(launched!);
      return say("stopping: the crawl saves what it has and records the run as stopped", "warn");
    }
    if (key.return) {
      const run = tab === 2 ? runs[current] : tab === 0 ? latest : null;
      if (run) {
        if (!dashboard) return say("the dashboard isn't running", "warn");
        openUrl(runUrl(dashboard.url, run));
        return say(`opened ${run.id} in the dashboard`);
      }
      const cmd = selectedCmd();
      return cmd ? copyCmd(cmd) : undefined;
    }
    if (input === "o") {
      if (!dashboard) return say("the dashboard isn't running", "warn");
      return openUrl(dashboard.url) ? say(`opened ${dashboard.url}`) : say(`open ${dashboard.url} in a browser`, "warn");
    }
    if (input === "t") {
      if (openTerminal(cwd)) return say(`opened a new terminal window in ${cwd}`);
      return copy(`cd ${cwd}`) ? say(`open a new terminal tab and paste: cd ${cwd}`, "warn") : say(`open a new terminal tab in ${cwd}`, "warn");
    }
    if (input === "r") {
      setRuns(readRuns(runsRoot));
      refreshDevices();
      return say("refreshed", "faint");
    }
  });

  const width = Math.max(60, Math.min(stdout.columns || 80, 110) - 2);
  const key = (k: string) => <Text color={C.accent}>{k}</Text>;

  const keys: Record<number, React.ReactNode> = {
    0: <>{key("c")} copy · {key("x")} run · {key("↵")} open latest</>,
    1: <>{key("x")} run · {key("s")} stop · {key("c")} copy</>,
    2: <>{key("↵")} open · {key("c")} copy</>,
    3: <>{key("t")} terminal · {key("c")} copy</>,
  };

  return (
    <Box flexDirection="column" paddingX={1}>
      <Text bold>
        <Text color={C.text}>APPSCREEN </Text>
        <Text color={C.accent}>MAP</Text>
      </Text>
      <Text color={C.faint}>
        map every screen of a mobile app · cli {version} · engine {engineVer ?? "…"} · map schema {MAP_SCHEMA}
      </Text>
      {update && (
        <Text color={C.dim}>
          {update}: <Text color={C.accent}>appscreenmap update</Text>
        </Text>
      )}

      <Box flexDirection="column" marginTop={1}>
        <Field label="dashboard">
          {dashboard ? (
            <>
              <Text color={C.text}>{dashboard.url}</Text>
              <Text color={C.faint}>
                {"   "}
                {dashboard.origin === "attached" ? "already running · " : opened ? "opened in your browser · " : ""}
              </Text>
              {key("o")}
              <Text color={C.faint}> opens</Text>
            </>
          ) : dashboardError ? (
            <Text color={C.bad}>{dashboardError.split("\n")[0]}</Text>
          ) : (
            <Text color={C.faint}>starting</Text>
          )}
        </Field>
        <Field label="android">
          {android === undefined ? (
            <Text color={C.faint}>checking</Text>
          ) : android === null ? (
            <Text color={C.faint}>adb not found: install Android platform-tools</Text>
          ) : ready.length ? (
            <Text color={C.text}>{ready.map((d) => [d.serial, d.model].filter(Boolean).join(" · ")).join(",  ")}</Text>
          ) : android.length ? (
            <Text color={C.warn}>
              {android[0]!.serial} is {android[0]!.state}: accept the prompt on the device
            </Text>
          ) : (
            <Text color={C.faint}>no device: start an emulator</Text>
          )}
        </Field>
        {sims !== null && (
          <Field label="ios">
            {sims === undefined ? (
              <Text color={C.faint}>checking</Text>
            ) : sims.length ? (
              <Text color={C.text}>{sims.map((s) => `${s.name} · ${s.runtime}`).join(",  ")}</Text>
            ) : (
              <Text color={C.faint}>no simulator booted</Text>
            )}
          </Field>
        )}
        <Field label="runs">
          <Text color={C.text}>{runsShown}/</Text>
          <Text color={C.dim}> · {runs.length ? `${runs.length} run${runs.length === 1 ? "" : "s"}` : "none yet"}</Text>
          {crawling && <Text color={C.warn}> · one mapping now</Text>}
        </Field>
      </Box>

      <Box flexDirection="column" marginTop={1} minHeight={9}>
        {tab === 0 && (
          <Box flexDirection="column">
            {latest ? <ReadinessPanel run={latest} r={readiness} width={width} /> : <Field label="LATEST"><Text color={C.faint}>no runs yet</Text></Field>}
            <Box marginTop={1}>
              <Field label="next">
                <Text color={C.accent}>{next.cmd}</Text>
                <Text color={C.dim}>   {next.what}</Text>
              </Field>
            </Box>
          </Box>
        )}
        {tab === 1 && (
          <Box flexDirection="column">
            {progress && (progress.status === "running" || progress.runId) ? (
              <Live p={progress} />
            ) : launched ? (
              <LogTail title={launched.label} lines={logLines} status={launchedExit} />
            ) : (
              <Field label="MAPPING">
                <Text color={C.faint}>nothing right now: x starts a crawl, and one from another terminal shows up here too</Text>
              </Field>
            )}
            {launched && progress && (
              <Text color={C.faint}>
                {" ".repeat(LABEL_W)}log: {relative(cwd, launched.log)}
              </Text>
            )}
            <Box marginTop={1}>
              <SuggestionList items={crawlItems} sel={current} canRun />
            </Box>
          </Box>
        )}
        {tab === 2 &&
          (runs.length ? (
            <Box flexDirection="column">
              {runs.slice(0, 10).map((r, i) => (
                <RunRow key={r.id} run={r} selected={i === current} />
              ))}
              {runs[current] && (
                <Box marginTop={1}>
                  <SuggestionList items={runCommands(runDir(runs[current]!))} sel={-1} />
                </Box>
              )}
            </Box>
          ) : (
            <Field label="RUNS">
              <Text color={C.faint}>none in {runsShown}/ yet</Text>
            </Field>
          ))}
        {tab === 3 && (
          <Box flexDirection="column">
            <Field label="AGENT">
              <Text color={C.dim}>start a session in a new terminal (</Text>
              {key("t")}
              <Text color={C.dim}>), then ask in plain language or use a skill:</Text>
            </Field>
            <Box marginTop={1}>
              <SuggestionList items={AGENT} sel={current} />
            </Box>
          </Box>
        )}
      </Box>

      <Text color={C.line}>{"─".repeat(width)}</Text>
      <Text wrap="truncate-end">
        {TABS.map((name, i) => (
          <Text key={name} color={i === tab ? C.accent : C.dim} bold={i === tab}>
            {name}
            {name === "crawl" && crawling ? <Text color={C.faint}> live</Text> : null}
            {"  "}
          </Text>
        ))}
        <Text color={C.faint}>
          {"   "}
          {key("←→")} {keys[tab]} · {key("q")} quit
        </Text>
      </Text>
      {flash && (
        <Text color={C[flash.tone]} wrap="truncate-end">
          {flash.text}
        </Text>
      )}
    </Box>
  );
}
