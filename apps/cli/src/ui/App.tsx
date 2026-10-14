import React, { useEffect, useState } from "react";
import { Box, Text, useApp, useInput, useStdout } from "ink";
import { join, relative } from "node:path";
import { AGENT, CRAWL, runCommands, type Suggestion } from "../content";
import { openUrl, type Dashboard } from "../dashboard";
import { androidDevices, simulators, type AndroidDevice, type Simulator } from "../devices";
import { engineVersion, type Engine } from "../engine";
import { ago, readRuns, runUrl, type RunSummary } from "../runs";
import { copy, openTerminal } from "../system";
import { C } from "../theme";

export const MAP_SCHEMA = 1;
const TABS = ["Home", "Crawl", "Runs", "Agent"] as const;

// Half-block wordmark (plain Unicode, any mono font): "APPSCREEN" in text colour, "MAP" in blue.
const MARK: [string, string][] = [
  ["▄▀█ █▀█ █▀█ █▀ █▀▀ █▀█ █▀▀ █▀▀ █▄ █ ", "█▀▄▀█ ▄▀█ █▀█"],
  ["█▀█ █▀▀ █▀▀ ▄█ █▄▄ █▀▄ ██▄ ██▄ █ ▀█ ", "█ ▀ █ █▀█ █▀▀"],
];

export interface AppProps {
  version: string;
  engine: Engine;
  dashboard: Dashboard | null;
  dashboardError: string | null;
  opened: boolean;
  runsRoot: string;
  cwd: string;
}

type Tone = "good" | "warn" | "bad" | "faint";
interface Line {
  glyph: string;
  label: string;
  detail: string;
  tone: Tone;
}

function StatusRow({ glyph, label, detail, tone }: Line) {
  return (
    <Text wrap="truncate-end">
      <Text color={C[tone]}>{glyph}</Text> <Text color={C.text}>{label.padEnd(10)}</Text>
      <Text color={tone === "faint" ? C.faint : C.dim}>{detail}</Text>
    </Text>
  );
}

function SuggestionList({ items, sel }: { items: Suggestion[]; sel: number }) {
  const width = Math.max(...items.map((i) => i.cmd.length)) + 3;
  return (
    <Box flexDirection="column">
      {items.map((item, i) => (
        <Text key={item.cmd} wrap="truncate-end">
          <Text color={i === sel ? C.accent : C.faint}>{i === sel ? "› " : "  "}</Text>
          <Text color={i === sel ? C.accent : C.text}>{item.cmd.padEnd(width)}</Text>
          <Text color={C.dim}>{item.what}</Text>
        </Text>
      ))}
    </Box>
  );
}

const STATUS: Record<string, Tone> = { done: "good", running: "warn", stopped: "faint", failed: "bad" };

function RunRow({ run, selected }: { run: RunSummary; selected?: boolean }) {
  return (
    <Text wrap="truncate-end">
      <Text color={selected ? C.accent : C.faint}>{selected ? "› " : "  "}</Text>
      <Text color={C[STATUS[run.status] ?? "faint"]}>{run.status.padEnd(8)}</Text>
      <Text color={selected ? C.accent : C.text}>
        {run.app}
        {run.version ? ` ${run.version}` : ""}
      </Text>
      <Text color={C.dim}>
        {"  "}
        {run.platform === "ios" ? "iOS" : "Android"} · {run.screens} screens · {ago(run.startedAt)}
      </Text>
      <Text color={C.faint}>{"  "}{run.id}</Text>
    </Text>
  );
}

export function App({ version, engine, dashboard, dashboardError, opened, runsRoot, cwd }: AppProps) {
  const { exit } = useApp();
  const { stdout } = useStdout();
  const [tab, setTab] = useState(0);
  const [sel, setSel] = useState([0, 0, 0, 0]);
  const [flash, setFlash] = useState<{ text: string; tone: Tone } | null>(null);
  const [runs, setRuns] = useState<RunSummary[]>(() => readRuns(runsRoot));
  const [android, setAndroid] = useState<AndroidDevice[] | null | undefined>(undefined);
  const [sims, setSims] = useState<Simulator[] | null | undefined>(undefined);
  const [engineVer, setEngineVer] = useState<string | null>(null);

  const refresh = () => {
    setRuns(readRuns(runsRoot));
    androidDevices().then(setAndroid);
    simulators().then(setSims);
  };
  useEffect(() => {
    refresh();
    engineVersion(engine).then(setEngineVer);
    const timer = setInterval(() => setRuns(readRuns(runsRoot)), 3000); // a crawl in another tab shows up here
    return () => clearInterval(timer);
  }, []);

  const runsShown = relative(cwd, runsRoot).startsWith("..") ? runsRoot : relative(cwd, runsRoot) || ".";
  const runDir = (r: RunSummary) => join(runsShown, r.path);
  const lengths = [0, CRAWL.length, runs.length, AGENT.length];
  const current = sel[tab] ?? 0;
  const say = (text: string, tone: Tone = "good") => setFlash({ text, tone });
  const copyCmd = (cmd: string) =>
    copy(cmd) ? say(`copied: ${cmd}`) : say(`no clipboard tool here; run: ${cmd}`, "warn");

  const selectedCmd = (): string | null => {
    if (tab === 1) return CRAWL[current]?.cmd ?? null;
    if (tab === 3) return AGENT[current]?.cmd ?? null;
    if (tab === 2) {
      const run = runs[current];
      return run ? runCommands(runDir(run))[0]!.cmd : null;
    }
    return CRAWL[0]!.cmd;
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
      refresh();
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

      <Box flexDirection="column" marginTop={1}>
        {lines.map((l) => (
          <StatusRow key={l.label} {...l} />
        ))}
      </Box>

      <Box marginTop={1}>
        {TABS.map((name, i) => (
          <Text key={name} color={i === tab ? C.accent : C.dim} bold={i === tab}>
            {` ${i + 1} ${name} `}
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
              <Text color={C.faint}>{"\n"}3 Runs opens one in the dashboard · 4 Agent to hand the work to an agent</Text>
            </Box>
          ) : (
            <Box flexDirection="column">
              <Text color={C.dim}>No runs in {runsShown}/ yet. Start one here, or ask an agent (4 Agent):</Text>
              <SuggestionList items={CRAWL.slice(0, 2)} sel={-1} />
            </Box>
          ))}
        {tab === 1 && (
          <Box flexDirection="column">
            <Text color={C.dim}>Run a crawl in another terminal; it shows up under Runs as it records.</Text>
            <SuggestionList items={CRAWL} sel={current} />
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
        1–4 tab · ↑↓ select · c copy · ↵ {tab === 2 ? "open run" : "copy"} · o dashboard · t new terminal · r refresh · q quit
      </Text>
      {flash && <Text color={C[flash.tone]} wrap="truncate-end">{flash.text}</Text>}
    </Box>
  );
}
