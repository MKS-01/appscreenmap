// Presentational pieces of the terminal home. Colours follow the design system: blue (accent) only for what you can
// act on, status colours always next to a word or glyph.
import React from "react";
import { Box, Text } from "ink";
import { runnable, type Suggestion } from "../content";
import { ago, type RunSummary } from "../runs";
import { C } from "../theme";
import { budgetUsed, duration, type Progress } from "../watch";

export type Tone = "good" | "warn" | "bad" | "faint" | "dim";

export interface Line {
  glyph: string;
  label: string;
  detail: string;
  tone: Tone;
}

export function StatusRow({ glyph, label, detail, tone }: Line) {
  return (
    <Text wrap="truncate-end">
      <Text color={C[tone]}>{glyph}</Text> <Text color={C.text}>{label.padEnd(10)}</Text>
      <Text color={tone === "faint" ? C.faint : C.dim}>{detail}</Text>
    </Text>
  );
}

export function SuggestionList({ items, sel, canRun = false }: { items: Suggestion[]; sel: number; canRun?: boolean }) {
  const width = Math.min(60, Math.max(...items.map((i) => i.cmd.length))) + 3;
  return (
    <Box flexDirection="column">
      {items.map((item, i) => {
        const cmd = item.cmd.length > 60 ? `${item.cmd.slice(0, 59)}…` : item.cmd;
        return (
          <Text key={item.cmd} wrap="truncate-end">
            <Text color={i === sel ? C.accent : C.faint}>{i === sel ? "› " : "  "}</Text>
            <Text color={i === sel ? C.accent : C.text}>{cmd.padEnd(width)}</Text>
            <Text color={C.dim}>{item.what}</Text>
            {canRun && runnable(item) && <Text color={C.faint}>  x runs it</Text>}
          </Text>
        );
      })}
    </Box>
  );
}

const STATUS: Record<string, Tone> = { done: "good", running: "warn", stopped: "faint", failed: "bad" };
export const statusTone = (status: string): Tone => STATUS[status] ?? "faint";

export function RunRow({ run, selected }: { run: RunSummary; selected?: boolean }) {
  return (
    <Text wrap="truncate-end">
      <Text color={selected ? C.accent : C.faint}>{selected ? "› " : "  "}</Text>
      <Text color={C[statusTone(run.status)]}>{run.status.padEnd(8)}</Text>
      <Text color={selected ? C.accent : C.text}>
        {run.app}
        {run.version ? ` ${run.version}` : ""}
      </Text>
      <Text color={C.dim}>
        {"  "}
        {run.platform === "ios" ? "iOS" : "Android"} · {run.screens} screens · {ago(run.startedAt)}
      </Text>
      <Text color={C.faint}>
        {"  "}
        {run.id}
      </Text>
    </Text>
  );
}

const EFFECT: Record<string, [glyph: string, word: string, tone: Tone]> = {
  new_screen: ["★", "new screen", "good"],
  known_screen: ["→", "", "dim"],
  same_screen: ["·", "same screen", "faint"],
  left_app: ["↗", "left the app", "warn"],
  crash: ["✘", "crash", "bad"],
  not_found: ["?", "element gone", "warn"],
};

/** Live progress of a crawl: budget bar, counts, the latest steps. */
export function Live({ p }: { p: Progress }) {
  const used = budgetUsed(p);
  const barWidth = 30;
  const filled = Math.round(used * barWidth);
  const running = p.status === "running";
  return (
    <Box flexDirection="column">
      <Text wrap="truncate-end">
        <Text color={C[statusTone(p.status)]}>{running ? "●" : p.status === "done" ? "✔" : "○"} </Text>
        <Text color={C.text}>
          {running ? "Mapping" : `${p.status[0]!.toUpperCase()}${p.status.slice(1)}:`} {p.app}
        </Text>
        <Text color={C.dim}>{p.device ? ` on ${p.device}` : ""}</Text>
        <Text color={C.faint}>
          {"  "}
          {p.runId}
        </Text>
      </Text>
      <Text>
        <Text color={C.text}>{"█".repeat(filled)}</Text>
        <Text color={C.line}>{"░".repeat(barWidth - filled)}</Text>
        <Text color={C.dim}>
          {" "}
          step {p.steps}
          {p.maxSteps ? `/${p.maxSteps}` : ""} · {duration(p.elapsedS)}
          {p.maxMinutes ? ` of ${p.maxMinutes}m` : ""}
        </Text>
      </Text>
      <Text color={C.dim}>
        {p.screens} screens · {p.transitions} transitions ·{" "}
        <Text color={p.crashes ? C.bad : C.dim}>{p.crashes} crashes</Text>
        {!running && p.stopReason ? <Text color={C.faint}> · {p.stopReason}</Text> : null}
      </Text>
      <Box flexDirection="column" marginTop={1}>
        {p.recent.map((s) => {
          const [glyph, word, tone] = EFFECT[s.effect] ?? ["·", s.effect, "faint"];
          return (
            <Text key={s.step} wrap="truncate-end">
              <Text color={C.faint}>{String(s.step).padStart(4)}  </Text>
              <Text color={C.dim}>{s.screenTitle ?? s.screen} › </Text>
              <Text color={C.text}>{s.label}</Text>
              <Text color={C[tone]}>
                {"  "}
                {glyph} {s.to && s.effect !== "same_screen" ? (s.toTitle ?? s.to) : ""}
                {word ? `${s.to && s.effect !== "same_screen" ? " · " : ""}${word}` : ""}
              </Text>
            </Text>
          );
        })}
      </Box>
    </Box>
  );
}

/** The last lines a command started here printed (for commands that don't record a run, or before one appears). */
export function LogTail({ title, lines, status }: { title: string; lines: string[]; status: string | null }) {
  return (
    <Box flexDirection="column">
      <Text wrap="truncate-end">
        <Text color={status === null ? C.warn : status === "0" ? C.good : C.bad}>
          {status === null ? "● running" : status === "0" ? "✔ finished" : `✘ exited ${status}`}
        </Text>
        <Text color={C.dim}>  {title}</Text>
      </Text>
      {lines.map((l, i) => (
        <Text key={i} color={C.dim} wrap="truncate-end">
          {"  "}
          {l}
        </Text>
      ))}
    </Box>
  );
}
