import { afterEach, describe, expect, test } from "bun:test";
import { createServer, type Server } from "node:net";
import { isDashboard, startDashboard, stopDashboard, type Dashboard } from "../src/dashboard";
import { engineVersion, type Engine } from "../src/engine";

const fake: Engine = { cmd: ["bun", `${import.meta.dir}/fake-engine.ts`], source: "env" };
const host = "127.0.0.1";
const basePort = () => 41000 + Math.floor(Math.random() * 2000) * 10;
let started: Dashboard[] = [];
let blockers: Server[] = [];

afterEach(() => {
  started.forEach((d) => stopDashboard(d));
  blockers.forEach((b) => b.close());
  started = [];
  blockers = [];
});

describe("the dashboard", () => {
  test("starts the engine's serve, attaches to it next time, and stops only what it started", async () => {
    const port = basePort();
    const d = await startDashboard(fake, { runs: "runs", host, port });
    started.push(d);
    expect(d).toMatchObject({ url: `http://${host}:${port}/`, origin: "spawned" });
    const again = await startDashboard(fake, { runs: "runs", host, port });
    expect(again.origin).toBe("attached");
    stopDashboard(again); // attached: left running
    expect(await isDashboard(`http://${host}:${port}`)).toBe(true);
    stopDashboard(d);
    await d.proc!.exited;
    expect(await isDashboard(`http://${host}:${port}`)).toBe(false);
  });

  test("skips a port something else is using", async () => {
    const port = basePort();
    const blocker = createServer();
    await new Promise<void>((r) => blocker.listen(port, host, r));
    blockers.push(blocker);
    const d = await startDashboard(fake, { runs: "runs", host, port });
    started.push(d);
    expect(d.url).toBe(`http://${host}:${port + 1}/`);
  });

  test("reports why the engine couldn't serve", async () => {
    const failing: Engine = { cmd: ["env", "FAKE_ENGINE_FAIL=1", ...fake.cmd], source: "env" };
    await expect(startDashboard(failing, { runs: "runs", host, port: basePort() })).rejects.toThrow("Web viewer not built");
  });

  test("reads the engine version", async () => {
    expect(await engineVersion(fake)).toBe("9.9.9");
    expect(await engineVersion({ cmd: ["false"], source: "env" })).toBeNull();
  });
});
