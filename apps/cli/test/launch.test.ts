import { describe, expect, test } from "bun:test";
import { existsSync, mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { crawlSuggestions, runnable } from "../src/content";
import type { Engine } from "../src/engine";
import { commandFor, launch, stop, stopAll } from "../src/launch";

const fake: Engine = { cmd: ["bun", `${import.meta.dir}/fake-engine.ts`], source: "env" };

describe("commands started from the terminal home", () => {
  test("crawls write into the watched runs folder; placeholders aren't runnable", () => {
    const [playground, apk] = crawlSuggestions(true);
    expect(commandFor(fake, playground!, "/r")).toEqual([...fake.cmd, ...playground!.engine!, "--out", "/r"]);
    expect(playground!.env).toEqual({ APP_PASSWORD: "playground-demo" });
    expect(runnable(apk!)).toBe(false);
    expect(commandFor(fake, apk!, "/r")).toBeNull();
    expect(crawlSuggestions(false).some((s) => s.cmd.includes("playground"))).toBe(false);
  });

  test("runs in the background with output in runs/.logs, and stops like Ctrl-C", async () => {
    const runs = mkdtempSync(join(tmpdir(), "asm-runs-"));
    const item = launch(fake, { cmd: "crawl", what: "", engine: ["crawl", "--clear-data"] }, runs, runs)!;
    expect(item.log.startsWith(join(runs, ".logs"))).toBe(true);
    await Bun.sleep(400);
    expect(readFileSync(item.log, "utf8")).toContain(`mapping (--clear-data --out ${runs})`);
    stop(item);
    expect(await item.proc.exited).toBe(0);
    expect(readFileSync(item.log, "utf8")).toContain("stopped: saving what we have");
  });

  test("quitting stops everything still running", async () => {
    const runs = mkdtempSync(join(tmpdir(), "asm-runs-"));
    const item = launch(fake, { cmd: "crawl", what: "", engine: ["crawl"] }, runs, runs)!;
    await Bun.sleep(300);
    await stopAll(3000);
    expect(item.proc.exitCode).toBe(0);
    expect(existsSync(item.log)).toBe(true);
  });
});
