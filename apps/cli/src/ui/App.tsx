import React, { useEffect, useMemo, useRef, useState } from "react";
import { Box, Text, useApp, useInput, useStdout } from "ink";
import { existsSync } from "node:fs";
import { join, relative } from "node:path";
import { AGENT, crawlSuggestions, runCommands, runnable } from "../content";
import { openUrl, type Dashboard } from "../dashboard";
import { androidDevices, simulators, type AndroidDevice, type Simulator } from "../devices";
import { engineVersion, type Engine } from "../engine";
import { launch, stop, type Launched } from "../launch";
import { readRuns, runUrl, type RunSummary } from "../runs";
import { copy, openTerminal } from "../system";
import { C } from "../theme";
import { readProgress, runEvents, tail, type Progress } from "../watch";
import { Live, LogTail, RunRow, StatusRow, SuggestionList, statusTone, type Line, type Tone } from "./parts";

import { MAP_SCHEMA_VERSION } from "../schema";

export const MAP_SCHEMA = MAP_SCHEMA_VERSION;
const TABS = ["Home", "Crawl", "Runs", "Agent"] as const;
const POLL_MS = 1000;

// Half-block wordmark (plain Unicode, any mono font): "APPSCREEN" in text colour, "MAP" in blue.
const MARK: [string, string][] = [
  ["▄▀█ █▀█ █▀█ █▀ █▀▀ █▀█ █▀▀ █▀▀ █▄ █ ", "█▀▄▀█ ▄▀█ █▀█"],
  ["█▀█ █▀▀ █▀▀ ▄█ █▄▄ █▀▄ ██▄ ██▄ █ ▀█ ", "█ ▀ █ █▀█ █▀▀"],
];

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
  const [android, setAndroid] = useState<AndroidDevice[] | null | undefined>(undefined);
  const [sims, setSims] = useState<Simulator[] | null | undefined>(undefined);
  const [engineVer, setEngineVer] = useState<string | null>(null);
  const [progress, setProgress] = useState<Progress | null>(null);
  const [launched, setLaunched] = useState<Launched | null>(null);
  const [launchedExit, setLaunchedExit] = useState<string | null>(null);
  const [logLines, setLogLines] = useState<string[]>([]);
  const [update, setUpdate] = useState<string | null>(null);
  const prevRuns = useRef(runs);

  const crawlItems = useMemo(
    () => crawlSuggestions(existsSync(join(cwd, "samples", "playground-app", "apk", "playground-v1.apk"))),
    [cwd],
  );
  const say = (text: string, tone: Tone = "good") => setFlash({ text, tone });

  const refreshDevices = () => {
    androidDevices().then(setAndroid);
    simulators().then(setSims);
  };

  // Every second: new or finished runs (a crawl here, or an agent's in another terminal), and the live crawl.
  useEffect(() => {
    refreshDevices();
    engineVersion(engine).then(setEngineVer);
    updateNotice?.then(setUpdate);
    const tick = () => {
      const next = readRuns(runsRoot);
      for (const ev of runEvents(prevRuns.current, next)) {
        if (ev.kind === "started") say(`● ${ev.run.app} is being mapped: ${ev.run.id} (2 Crawl shows it live)`, "warn");
        else {
          say(`${ev.run.status === "done" ? "✔" : "○"} ${ev.run.id} ${ev.run.status}: ${ev.run.screens} screens`, statusTone(ev.run.status));
          setProgress(readProgress(runsRoot, ev.run)); // keep the final numbers on screen
        }
      }
      prevRuns.current = next;
      setRuns(next);
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
  const lengths = [0, crawlItems.length, runs.length, AGENT.length];
  const current = sel[tab] ?? 0;
  const launchedRunning = launched !== null && launchedExit === null;
  const copyCmd = (cmd: string) =>
    copy(cmd) ? say(`copied: ${cmd}`) : say(`no clipboard tool here; run: ${cmd}`, "warn");

  const selectedCmd = (): string | null => {
    if (tab === 1) return crawlItems[current]?.cmd ?? null;
    if (tab === 3) return AGENT[current]?.cmd ?? null;
    if (tab === 2) {
      const run = runs[current];
      return run ? runCommands(runDir(run))[0]!.cmd : null;
    }
    return crawlItems[0]!.cmd;
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
    if (input === "x" && tab === 1) {
      const item = crawlItems[current]!;
      if (!runnable(item)) return say("this one needs editing first: c copies it", "warn");
      if (launchedRunning) return say("a command started here is still running: s stops it", "warn");
      const started = launch(engine, item, runsRoot, cwd);
      if (!started) return;
      setLaunchedExit(null);
      setLogLines([]);
      setProgress(null);
      setLaunched(started);
      return say(`started: ${item.cmd}`, "warn");
    }
    if (input === "s" && tab === 1) {
      if (!launchedRunning) return say("nothing started here is running (a crawl from another terminal stops there)", "faint");
      stop(launched!);
      return say("stopping: the crawl saves what it has and records the run as stopped", "warn");
    }
    if (key.return) {
      if (tab === 2 && runs[current]) {
        if (!dashboard) return say("the dashboard isn't running", "warn");
        openUrl(runUrl(dashboard.url, runs[current]!));
        return say(`opened ${runs[current]!.id} in the dashboard`);
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
      return copy(`cd ${cwd}`)
        ? say(`open a new terminal tab and paste: cd ${cwd}`, "warn")
        : say(`open a new terminal tab in ${cwd}`, "warn");
    }
    if (input === "r") {
      setRuns(readRuns(runsRoot));
      refreshDevices();
      return say("refreshed", "faint");
    }
  });

  const width = Math.max(40, Math.min(stdout.columns || 80, 120) - 2);
  const ready = (android ?? []).filter((d) => d.state === "device");
  const lines: Line[] = [
    dashboard
      ? {
          glyph: "●",
          label: "Dashboard",
          detail: `${dashboard.url}   ${dashboard.origin === "attached" ? "already running" : opened ? "opened in your browser" : "press o to open"}`,
          tone: "good",
        }
      : dashboardError
        ? { glyph: "✘", label: "Dashboard", detail: dashboardError.split("\n")[0]!, tone: "bad" }
        : { glyph: "○", label: "Dashboard", detail: "starting…", tone: "faint" },
    android === undefined
      ? { glyph: "○", label: "Android", detail: "checking…", tone: "faint" }
      : android === null
        ? { glyph: "○", label: "Android", detail: "adb not found: install Android platform-tools", tone: "faint" }
        : ready.length
          ? { glyph: "●", label: "Android", detail: ready.map((d) => [d.serial, d.model].filter(Boolean).join(" · ")).join(",  "), tone: "good" }
          : android.length
            ? { glyph: "!", label: "Android", detail: `${android[0]!.serial} is ${android[0]!.state}: accept the prompt on the device`, tone: "warn" }
            : { glyph: "○", label: "Android", detail: "no device: start an emulator", tone: "faint" },
  ];
  if (sims !== null) {
    lines.push(
      sims === undefined
        ? { glyph: "○", label: "iOS", detail: "checking…", tone: "faint" }
        : sims.length
          ? { glyph: "●", label: "iOS", detail: sims.map((s) => `${s.name} · ${s.runtime}`).join(",  "), tone: "good" }
          : { glyph: "○", label: "iOS", detail: 'no simulator booted: xcrun simctl boot "iPhone 17"', tone: "faint" },
    );
  }

  const keys =
    tab === 1
      ? "x run here · s stop · c copy · ↑↓ select · o dashboard · q quit"
      : `1–4 tab · ↑↓ select · c copy · ↵ ${tab === 2 ? "open run" : "copy"} · o dashboard · t new terminal · r refresh · q quit`;

  return (
    <Box flexDirection="column" paddingX={1}>
      <Box flexDirection="column">
        {MARK.map(([a, b], i) => (
          <Text key={i}>
            <Text color={C.text}>{a}</Text>
            <Text color={C.accent}>{b}</Text>
          </Text>
        ))}
      </Box>
      <Text color={C.faint}>
        map every screen of a mobile app · cli {version} · engine {engineVer ?? "…"} · map schema {MAP_SCHEMA}
      </Text>
      {update && (
        <Text color={C.dim}>
          {update} → <Text color={C.accent}>appscreenmap update</Text>
        </Text>
      )}

      <Box flexDirection="column" marginTop={1}>
        {lines.map((l) => (
          <StatusRow key={l.label} {...l} />
        ))}
      </Box>

      <Box marginTop={1}>
        {TABS.map((name, i) => (
          <Text key={name} color={i === tab ? C.accent : C.dim} bold={i === tab}>
            {` ${i + 1} ${name}${name === "Crawl" && runs.some((r) => r.status === "running") ? " ●" : ""} `}
          </Text>
        ))}
      </Box>
      <Text color={C.line}>{"─".repeat(width)}</Text>

      <Box flexDirection="column" minHeight={8}>
        {tab === 0 &&
          (runs.length ? (
            <Box flexDirection="column">
              <Text color={C.dim}>Recent runs ({runsShown}/)</Text>
              {runs.slice(0, 5).map((r) => (
                <RunRow key={r.id} run={r} />
              ))}
              <Text color={C.faint}>{"\n"}2 Crawl to map an app · 3 Runs opens one in the dashboard · 4 Agent to hand the work to an agent</Text>
            </Box>
          ) : (
            <Box flexDirection="column">
              <Text color={C.dim}>No runs in {runsShown}/ yet. Start one in 2 Crawl, or ask an agent (4 Agent):</Text>
              <SuggestionList items={crawlItems.slice(0, 2)} sel={-1} />
            </Box>
          ))}
        {tab === 1 && (
          <Box flexDirection="column">
            {progress && (progress.status === "running" || progress.runId) ? (
              <Live p={progress} />
            ) : launched ? (
              <LogTail title={launched.label} lines={logLines} status={launchedExit} />
            ) : (
              <Text color={C.dim}>No crawl running. Start one with x, or in another terminal: it shows up here live.</Text>
            )}
            {launched && progress && <Text color={C.faint}>log: {relative(cwd, launched.log)}</Text>}
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
                <Box flexDirection="column" marginTop={1}>
                  <SuggestionList items={runCommands(runDir(runs[current]!))} sel={-1} />
                </Box>
              )}
            </Box>
          ) : (
            <Text color={C.dim}>No runs in {runsShown}/ yet.</Text>
          ))}
        {tab === 3 && (
          <Box flexDirection="column">
            <Text color={C.dim}>Start an agent session in a new terminal (t), then:</Text>
            <SuggestionList items={AGENT} sel={current} />
          </Box>
        )}
      </Box>

      <Text color={C.line}>{"─".repeat(width)}</Text>
      <Text color={C.faint} wrap="truncate-end">
        {keys}
      </Text>
      {flash && (
        <Text color={C[flash.tone]} wrap="truncate-end">
          {flash.text}
        </Text>
      )}
    </Box>
  );
}
