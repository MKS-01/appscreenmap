import { describe, expect, test } from "bun:test";
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type { RunSummary } from "../src/runs";
import { budgetUsed, duration, parseProgress, parseTrace, readProgress, runEvents, tail } from "../src/watch";

const MAP = JSON.stringify({
  run: {
    id: "playground-v1-1", status: "running", steps: 42, elapsed_s: 190,
    app: { label: "Playground", version: "1.0" }, device: { name: "Pixel 8 (emulator)" },
    config: { max_steps: 200, max_minutes: 30 },
  },
  stats: { screens: 12, transitions: 30, crashes: 1 },
  screens: [{ id: "s001", title: "Home" }, { id: "s004", title: "Settings" }],
});
const TRACE = [
  '{"step": 41, "screen": "s001", "label": "Settings", "to": "s004", "effect": "new_screen"}',
  '{"step": 42, "screen": "s004", "label": "Dark theme", "to": "s004", "effect": "same_screen"}',
  '{"step": 43, "screen": "s00',
];

describe("live progress", () => {
  test("trace lines, skipping one still being written", () => {
    expect(parseTrace(TRACE).map((t) => t.step)).toEqual([41, 42]);
  });

  test("map.json + trace → progress, newest step first, with screen titles", () => {
    const p = parseProgress(MAP, parseTrace(TRACE));
    expect(p).toMatchObject({
      runId: "playground-v1-1", status: "running", app: "Playground 1.0", device: "Pixel 8 (emulator)",
      steps: 42, maxSteps: 200, elapsedS: 190, maxMinutes: 30, screens: 12, transitions: 30, crashes: 1,
    });
    expect(p.recent[0]).toMatchObject({ step: 42, screenTitle: "Settings", effect: "same_screen" });
    expect(p.recent[1]).toMatchObject({ step: 41, screenTitle: "Home", toTitle: "Settings", effect: "new_screen" });
    expect(budgetUsed(p)).toBeCloseTo(0.21); // steps (42/200) are ahead of time (190 s of 30 min)
  });

  test("read from a run folder; null until map.json exists", () => {
    const root = mkdtempSync(join(tmpdir(), "asm-runs-"));
    const run = { path: "playground/playground-v1-1" };
    expect(readProgress(root, run)).toBeNull();
    mkdirSync(join(root, run.path), { recursive: true });
    writeFileSync(join(root, run.path, "map.json"), MAP);
    writeFileSync(join(root, run.path, "trace.jsonl"), TRACE.slice(0, 2).join("\n") + "\n");
    expect(readProgress(root, run)?.recent.length).toBe(2);
  });

  test("tail reads only the end, dropping a cut first line", () => {
    const file = join(mkdtempSync(join(tmpdir(), "asm-")), "log.txt");
    writeFileSync(file, Array.from({ length: 100 }, (_, i) => `line ${i}`).join("\n") + "\n");
    expect(tail(file, 3)).toEqual(["line 97", "line 98", "line 99"]);
    expect(tail(file, 50, 40).every((l) => /^line \d+$/.test(l))).toBe(true);
    expect(tail(join(tmpdir(), "no-such-file"), 3)).toEqual([]);
  });

  test("durations", () => {
    expect([duration(45), duration(190), duration(3720)]).toEqual(["45s", "3m 10s", "1h 02m"]);
  });
});

describe("run events", () => {
  const run = (id: string, status: string): RunSummary =>
    ({ id, status, path: id, project: "p", app: "App", platform: "android", screens: 3, transitions: 2 }) as RunSummary;

  test("a run appears, a running one finishes, nothing else", () => {
    const before = [run("a", "running"), run("b", "done")];
    const after = [run("c", "running"), run("a", "done"), run("b", "done"), run("d", "failed")];
    expect(runEvents(before, after).map((e) => `${e.kind}:${e.run.id}`)).toEqual([
      "started:c",
      "finished:a",
      "finished:d",
    ]);
    expect(runEvents(after, after)).toEqual([]);
  });
});
