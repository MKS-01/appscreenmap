import { describe, expect, test } from "bun:test";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { applyClean, human, planClean, type CleanInput } from "../src/clean";

const DAY = 24 * 3600_000;
const now = Date.parse("2026-10-14T12:00:00Z");
const input = (over: Partial<CleanInput> = {}): CleanInput => ({
  viewers: [{ version: "0.1.0", path: "/h/viewer/0.1.0", bytes: 100 }, { version: "0.2.0", path: "/h/viewer/0.2.0", bytes: 100 }],
  currentViewer: "0.2.0",
  cache: [{ name: "wheels-0.1.0", path: "/h/cache/wheels-0.1.0", bytes: 50 }, { name: "update-check.json", path: "/h/cache/update-check.json", bytes: 1 }],
  logs: [
    { name: "old.log", path: "/r/.logs/old.log", bytes: 10, mtimeMs: now - 40 * DAY },
    { name: "new.log", path: "/r/.logs/new.log", bytes: 10, mtimeMs: now - 1 * DAY },
  ],
  runs: [
    { id: "old-done", status: "done", startedAt: new Date(now - 40 * DAY).toISOString(), path: "/r/p/old-done", bytes: 1000 },
    { id: "old-running", status: "running", startedAt: new Date(now - 40 * DAY).toISOString(), path: "/r/p/old-running", bytes: 1000 },
    { id: "recent", status: "done", startedAt: new Date(now - 2 * DAY).toISOString(), path: "/r/p/recent", bytes: 1000 },
  ],
  includeRuns: false,
  olderThanDays: 30,
  now,
  ...over,
});

describe("clean", () => {
  test("by default: old viewers, the cache and old logs; never the active viewer or the update check", () => {
    expect(planClean(input()).map((i) => i.label)).toEqual(["viewer 0.1.0", "cache/wheels-0.1.0", "log old.log"]);
  });

  test("--runs adds finished runs older than the cutoff, never a running one", () => {
    const runs = planClean(input({ includeRuns: true })).filter((i) => i.kind === "run");
    expect(runs.map((r) => r.runId)).toEqual(["old-done"]);
    expect(planClean(input({ includeRuns: true, olderThanDays: 1 })).filter((i) => i.kind === "run").map((r) => r.runId)).toEqual(["old-done", "recent"]);
  });

  test("removed runs leave runs/index.json; other entries stay", () => {
    const root = mkdtempSync(join(tmpdir(), "asm-runs-"));
    mkdirSync(join(root, "p", "old-done"), { recursive: true });
    writeFileSync(join(root, "index.json"), JSON.stringify({ runs: [{ id: "old-done" }, { id: "recent" }] }));
    applyClean([{ kind: "run", path: join(root, "p", "old-done"), label: "", bytes: 0, runId: "old-done" }], root);
    expect(existsSync(join(root, "p", "old-done"))).toBe(false);
    expect(JSON.parse(readFileSync(join(root, "index.json"), "utf8")).runs).toEqual([{ id: "recent" }]);
  });

  test("sizes", () => {
    expect([human(512), human(2048), human(5 * 1024 ** 2)]).toEqual(["512 B", "2 KB", "5.0 MB"]);
  });
});
