import { describe, expect, test } from "bun:test";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { findCheckout, findEngine } from "../src/engine";

const REPO = resolve(import.meta.dir, "..", "..", "..");
const has = (...bins: string[]) => (bin: string) => (bins.includes(bin) ? `/usr/bin/${bin}` : null);

describe("finding the engine", () => {
  test("the checkout is found from anywhere inside it", () => {
    expect(findCheckout(import.meta.dir)).toBe(REPO);
    expect(findCheckout(mkdtempSync(join(tmpdir(), "asm-")))).toBeNull();
  });

  test("$APPSCREENMAP_ENGINE wins, then the checkout (via uv), then PATH", () => {
    const outside = mkdtempSync(join(tmpdir(), "asm-"));
    expect(findEngine({ env: { APPSCREENMAP_ENGINE: "python -m appscreenmap.engine" }, here: import.meta.dir, which: has() }))
      .toEqual({ cmd: ["python", "-m", "appscreenmap.engine"], source: "env" });
    expect(findEngine({ env: {}, here: import.meta.dir, which: has("uv", "appscreenmap-engine") })).toEqual({
      cmd: ["uv", "run", "--quiet", "--project", REPO, "appscreenmap-engine"],
      source: "checkout",
    });
    expect(findEngine({ env: {}, here: outside, baked: REPO, which: has("uv") })?.source).toBe("checkout");
    expect(findEngine({ env: {}, here: outside, baked: "", which: has("appscreenmap-engine"), toolBin: "/nonexistent" })).toEqual({
      cmd: ["/usr/bin/appscreenmap-engine"],
      source: "path",
    });
    expect(findEngine({ env: {}, here: outside, baked: "", which: has(), toolBin: "/nonexistent" })).toBeNull();
    // installed by `appscreenmap setup` into uv's tool folder, which isn't on PATH yet
    const toolBin = mkdtempSync(join(tmpdir(), "asm-bin-"));
    writeFileSync(join(toolBin, "appscreenmap-engine"), "#!/bin/sh\n");
    expect(findEngine({ env: {}, here: outside, baked: "", which: has(), toolBin })).toEqual({
      cmd: [join(toolBin, "appscreenmap-engine")],
      source: "path",
    });
  });
});
