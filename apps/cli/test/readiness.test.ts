import { describe, expect, test } from "bun:test";
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  a11yVerdict, crashVerdict, fromA11y, fromMap, fromPerf, fromSecurity, nextStep, perfVerdict, readReadiness,
  securityVerdict, type NextContext, type Readiness,
} from "../src/readiness";

const base: Readiness = {
  explored: { done: 80, total: 88 }, screens: 11, transitions: 36, crashes: 0,
  a11y: { open: 0, levelA: 0, levelAA: 0 }, perf: { slow: 0, needsWork: 0, coldMs: 640, timed: true },
  security: { score: 100, status: "info", errors: 0, warnings: 0 },
};

describe("readiness from a run's files", () => {
  test("map.json stats, a11y.json, perf.json and the security audit", () => {
    expect(fromMap({ stats: { screens: 11, transitions: 36, crashes: 1, elements: { done: 80, failed: 3, unreachable: 5 } } }))
      .toEqual({ explored: { done: 80, total: 88 }, screens: 11, transitions: 36, crashes: 1 });
    expect(fromA11y({ summary: { issues: 30, open: 25, by_level: { A: 20, AA: 10 } } })).toEqual({ open: 25, levelA: 20, levelAA: 10 });
    expect(fromPerf({ screens: [{ rating: "slow" }, { rating: "needs work" }, { rating: "ok" }], startup: { median_ms: 812 } }))
      .toEqual({ slow: 1, needsWork: 1, coldMs: 812, timed: true });
    expect(fromPerf({ screens: [], startup: { median_ms: null } })?.timed).toBe(false);
    expect(fromSecurity({ score: 76, status: "warn", findings: [{ severity: "warning" }, { severity: "error" }] }))
      .toEqual({ score: 76, status: "warn", errors: 1, warnings: 1 });
  });

  test("read from a run folder; audits not run are null", () => {
    const root = mkdtempSync(join(tmpdir(), "asm-runs-"));
    mkdirSync(join(root, "p", "r1"), { recursive: true });
    expect(readReadiness(root, { path: "p/r1" })).toBeNull();
    writeFileSync(join(root, "p", "r1", "map.json"), JSON.stringify({ stats: { screens: 3 } }));
    expect(readReadiness(root, { path: "p/r1" })).toMatchObject({ screens: 3, a11y: null, perf: null, security: null });
  });
});

describe("verdicts are words, from the numbers", () => {
  test("each row", () => {
    expect(crashVerdict({ ...base, crashes: 2 })).toBe("failing");
    expect(a11yVerdict(base)).toBe("ok");
    expect(a11yVerdict({ ...base, a11y: { open: 3, levelA: 1, levelAA: 2 } })).toBe("failing");
    expect(a11yVerdict({ ...base, a11y: { open: 3, levelA: 0, levelAA: 3 } })).toBe("warn");
    expect(a11yVerdict({ ...base, a11y: null })).toBe("not run");
    expect(perfVerdict({ ...base, perf: { slow: 1, needsWork: 0, coldMs: null, timed: true } })).toBe("warn");
    expect(perfVerdict({ ...base, perf: { slow: 0, needsWork: 0, coldMs: null, timed: false } })).toBeNull();
    expect(securityVerdict({ ...base, security: { score: 40, status: "fail", errors: 2, warnings: 0 } })).toBe("failing");
    expect(securityVerdict({ ...base, security: null })).toBe("not run");
  });
});

describe("the next step", () => {
  const ctx = (over: Partial<NextContext> = {}): NextContext => ({
    dashboardOk: true, devices: 1, crawling: false, inCheckout: true,
    latest: { status: "done", platform: "android", dir: "runs/p/r1" }, readiness: base, ...over,
  });
  const cmd = (over: Partial<NextContext>) => nextStep(ctx(over)).cmd;

  test("in priority order", () => {
    expect(cmd({ dashboardOk: false })).toBe("appscreenmap setup");
    expect(cmd({ crawling: true })).toBe("2 crawl");
    expect(cmd({ devices: 0 })).toBe("emulator -list-avds");
    expect(nextStep(ctx({ latest: null })).engine?.[0]).toBe("crawl"); // the Playground, ready to run
    expect(cmd({ latest: null, inCheckout: false })).toContain("path/to/app.apk");
    expect(cmd({ latest: { status: "failed", platform: "android", dir: "runs/p/r1" } })).toBe("appscreenmap report runs/p/r1");
    expect(cmd({ readiness: { ...base, crashes: 1 } })).toBe("appscreenmap report runs/p/r1");
    expect(cmd({ readiness: { ...base, a11y: null } })).toBe("appscreenmap a11y runs/p/r1 --report");
    expect(cmd({ readiness: { ...base, a11y: { open: 4, levelA: 1, levelAA: 3 } } })).toBe("/a11y-audit");
    expect(cmd({ readiness: { ...base, security: null } })).toBe("appscreenmap security runs/p/r1 --pull");
    expect(cmd({ readiness: { ...base, perf: { slow: 2, needsWork: 0, coldMs: null, timed: true } } })).toBe("appscreenmap perf runs/p/r1");
    expect(cmd({})).toContain("appscreenmap verify runs/p/r1");
  });
});
