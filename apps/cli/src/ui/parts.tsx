// Presentational pieces of the terminal home, in the design system's terms: a dim label column, plain values, status
// as an uppercase word (never a dot or glyph), blue only for what you can act on (keys, commands, the selection).
import React from "react";
import { Box, Text } from "ink";
import { runnable, type Suggestion } from "../content";
import { a11yVerdict, crashVerdict, perfVerdict, securityVerdict, type Readiness, type Verdict } from "../readiness";
import { ago, type RunSummary } from "../runs";
import { C } from "../theme";
import { budgetUsed, duration, type Progress } from "../watch";

export type Tone = "good" | "warn" | "bad" | "faint" | "dim";

export const LABEL_W = 11;
const BAR_W = 16;
const BAR_CH = "▆"; // lower 3/4 block: fill and track share it, so the bar has no seam

export function Label({ text }: { text: string }) {
  return <Text color={C.dim}>{text.padEnd(LABEL_W)}</Text>;
}

/** One label + value row; values truncate rather than wrap. */
export function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <Text wrap="truncate-end">
      <Label text={label} />
      {children}
    </Text>
  );
}

export function Bar({ pct, width = BAR_W }: { pct: number; width?: number }) {
  const filled = Math.round(Math.max(0, Math.min(1, pct)) * width);
  return (
    <Text>
      <Text color={C.text}>{BAR_CH.repeat(filled)}</Text>
      <Text color={C.line}>{BAR_CH.repeat(width - filled)}</Text>
    </Text>
  );
}

const VERDICT: Record<Verdict, [word: string, tone: Tone]> = {
  ok: ["OK", "good"],
  warn: ["WARN", "warn"],
  failing: ["FAILING", "bad"],
  "not run": ["NOT RUN", "faint"],
};

const STATUS: Record<string, Tone> = { done: "good", running: "warn", stopped: "faint", failed: "bad" };
export const statusTone = (status: string): Tone => STATUS[status] ?? "faint";

/** A value with its verdict word in a right-hand column. */
function Judged({ label, value, verdict, width }: { label: string; value: string; verdict: Verdict | null; width: number }) {
  const valueW = Math.max(20, width - LABEL_W - 9);
  const shown = value.length > valueW ? `${value.slice(0, valueW - 1)}…` : value;
  const [word, tone] = verdict ? VERDICT[verdict] : ["", "faint" as Tone];
  return (
    <Field label={label}>
      <Text color={verdict === "not run" ? C.faint : C.text}>{shown.padEnd(valueW)}</Text>
      <Text color={C[tone]} bold={verdict === "failing"}>
        {word.padStart(8)}
      </Text>
    </Field>
  );
}

/** The latest run as a ship-readiness summary. */
export function ReadinessPanel({ run, r, width }: { run: RunSummary; r: Readiness | null; width: number }) {
  const where = `${run.app}${run.version ? ` ${run.version}` : ""} · ${run.platform === "ios" ? "iOS" : "Android"} · `;
  return (
    <Box flexDirection="column">
      <Field label="LATEST">
        <Text color={C.text}>{where}</Text>
        <Text color={C[statusTone(run.status)]}>{run.status}</Text>
        <Text color={C.dim}> · {ago(run.startedAt)}</Text>
      </Field>
      {r && (
        <>
          <Field label="explored">
            <Bar pct={r.explored ? r.explored.done / r.explored.total : 0} />
            <Text color={C.dim}>
              {"  "}
              {r.screens} screens · {r.transitions} transitions
              {r.explored ? ` · ${r.explored.done}/${r.explored.total} elements` : ""}
            </Text>
          </Field>
          <Judged label="crashes" value={String(r.crashes)} verdict={crashVerdict(r)} width={width} />
          <Judged
            label="a11y"
            value={r.a11y ? `${r.a11y.open} open · ${r.a11y.levelA} level A · ${r.a11y.levelAA} AA` : "WCAG 2.2 checks not run"}
            verdict={a11yVerdict(r)}
            width={width}
          />
          <Judged
            label="perf"
            value={
              !r.perf
                ? "not summarised"
                : !r.perf.timed
                  ? "no load timings in this run"
                  : `${r.perf.slow} slow · ${r.perf.needsWork} needs work${r.perf.coldMs !== null ? ` · cold start ${r.perf.coldMs} ms` : ""}`
            }
            verdict={perfVerdict(r)}
            width={width}
          />
          <Judged
            label="security"
            value={r.security ? `score ${r.security.score} · ${r.security.errors} errors · ${r.security.warnings} warnings` : "no audit (Android builds)"}
            verdict={securityVerdict(r)}
            width={width}
          />
        </>
      )}
    </Box>
  );
}

export function SuggestionList({ items, sel, canRun = false }: { items: Suggestion[]; sel: number; canRun?: boolean }) {
  const width = Math.min(60, Math.max(...items.map((i) => i.cmd.length))) + 3;
  return (
    <Box flexDirection="column">
      {items.map((item, i) => {
        const cmd = item.cmd.length > 60 ? `${item.cmd.slice(0, 59)}…` : item.cmd;
        const selected = i === sel;
        return (
          <Text key={item.cmd} wrap="truncate-end">
            {"  "}
            <Text color={selected ? C.accent : C.text} bold={selected}>
              {cmd.padEnd(width)}
            </Text>
            <Text color={C.dim}>{item.what}</Text>
            {canRun && selected && runnable(item) && (
              <Text color={C.faint}>
                {"  "}
                <Text color={C.accent}>x</Text> runs it
              </Text>
            )}
          </Text>
        );
      })}
    </Box>
  );
}

export function RunRow({ run, selected }: { run: RunSummary; selected?: boolean }) {
  return (
    <Text wrap="truncate-end">
      {"  "}
      <Text color={C[statusTone(run.status)]}>{run.status.padEnd(9)}</Text>
      <Text color={selected ? C.accent : C.text} bold={selected}>
        {`${run.app}${run.version ? ` ${run.version}` : ""}`.padEnd(22)}
      </Text>
      <Text color={C.dim}>
        {run.platform === "ios" ? "iOS    " : "Android"} · {String(run.screens).padStart(3)} screens · {ago(run.startedAt).padEnd(9)}
      </Text>
      <Text color={C.faint}>{run.id}</Text>
    </Text>
  );
}

const EFFECT: Record<string, [word: string, tone: Tone]> = {
  new_screen: ["new screen", "good"],
  known_screen: ["known", "dim"],
  same_screen: ["same screen", "faint"],
  left_app: ["left the app", "warn"],
  crash: ["crash", "bad"],
  not_found: ["element gone", "warn"],
};

/** Live progress of a crawl: budget bar, counts, the latest steps. */
export function Live({ p }: { p: Progress }) {
  const running = p.status === "running";
  return (
    <Box flexDirection="column">
      <Field label={running ? "MAPPING" : "FINISHED"}>
        <Text color={C.text}>{p.app}</Text>
        <Text color={C.dim}>{p.device ? ` on ${p.device}` : ""} · </Text>
        <Text color={C[statusTone(p.status)]}>{p.status}</Text>
        <Text color={C.faint}> · {p.runId}</Text>
      </Field>
      <Field label="budget">
        <Bar pct={budgetUsed(p)} />
        <Text color={C.dim}>
          {"  "}
          step {p.steps}
          {p.maxSteps ? ` of ${p.maxSteps}` : ""} · {duration(p.elapsedS)}
          {p.maxMinutes ? ` of ${p.maxMinutes}m` : ""}
        </Text>
      </Field>
      <Field label="found">
        <Text color={C.text}>
          {p.screens} screens · {p.transitions} transitions ·{" "}
        </Text>
        <Text color={p.crashes ? C.bad : C.text}>{p.crashes} crashes</Text>
        {!running && p.stopReason ? <Text color={C.faint}> · {p.stopReason}</Text> : null}
      </Field>
      <Box flexDirection="column" marginTop={1}>
        {p.recent.map((s) => {
          const [word, tone] = EFFECT[s.effect] ?? [s.effect, "faint"];
          return (
            <Text key={s.step} wrap="truncate-end">
              <Text color={C.faint}>{String(s.step).padStart(5)}  </Text>
              <Text color={C.dim}>{(s.screenTitle ?? s.screen).slice(0, 14).padEnd(15)}</Text>
              <Text color={C.text}>{s.label.slice(0, 22).padEnd(23)}</Text>
              <Text color={C[tone]}>{word}</Text>
              {s.to && (s.effect === "new_screen" || s.effect === "known_screen") ? (
                <Text color={C.dim}> {s.toTitle ?? s.to}</Text>
              ) : null}
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
      <Field label={status === null ? "RUNNING" : status === "0" ? "FINISHED" : `EXITED ${status}`}>
        <Text color={C.dim}>{title}</Text>
      </Field>
      {lines.map((l, i) => (
        <Text key={i} color={C.dim} wrap="truncate-end">
          {" ".repeat(LABEL_W)}
          {l}
        </Text>
      ))}
    </Box>
  );
}
