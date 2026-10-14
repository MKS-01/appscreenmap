import { describe, expect, test } from "bun:test";
import { parseAdbDevices, parseSimctlBooted } from "../src/devices";
import { ago, parseIndex, runUrl } from "../src/runs";
import { C, parseTokens, resolveToken } from "../src/theme";

describe("devices", () => {
  test("adb devices -l", () => {
    const out = `List of devices attached
emulator-5554          device product:sdk_gphone64_arm64 model:sdk_gphone64_arm64 device:emu64a transport_id:1
R5CT1234ABC            unauthorized usb:1-1 transport_id:2

`;
    expect(parseAdbDevices(out)).toEqual([
      { serial: "emulator-5554", state: "device", model: "sdk gphone64 arm64" },
      { serial: "R5CT1234ABC", state: "unauthorized" },
    ]);
    expect(parseAdbDevices("* daemon started successfully\nList of devices attached\n")).toEqual([]);
  });

  test("simctl booted devices", () => {
    const json = JSON.stringify({
      devices: {
        "com.apple.CoreSimulator.SimRuntime.iOS-27-0": [
          { udid: "U1", name: "iPhone 17", state: "Booted" },
          { udid: "U2", name: "iPad", state: "Shutdown" },
        ],
      },
    });
    expect(parseSimctlBooted(json)).toEqual([{ udid: "U1", name: "iPhone 17", runtime: "iOS 27.0" }]);
  });
});

describe("runs", () => {
  const index = JSON.stringify({
    runs: [
      { id: "playground-v1-1", path: "playground/playground-v1-1", project: "playground", status: "done",
        started_at: "2026-10-13T03:10:07+00:00", screens: 31, transitions: 70,
        app: { package: "dev.appscreenmap.playground", label: "Playground", version: "1.0" } },
      { id: "sample-ios-1", path: "sample-ios/sample-ios-1", status: "running", started_at: "2026-10-14T01:00:00+00:00",
        app: { package: "com.example.sample", platform: "ios" } },
    ],
  });

  test("newest first, labels and platform", () => {
    const runs = parseIndex(index);
    expect(runs.map((r) => r.id)).toEqual(["sample-ios-1", "playground-v1-1"]);
    expect(runs[0]).toMatchObject({ app: "com.example.sample", platform: "ios", screens: 0 });
    expect(runs[1]).toMatchObject({ app: "Playground", version: "1.0", platform: "android", screens: 31 });
  });

  test("dashboard link and age", () => {
    expect(runUrl("http://127.0.0.1:8765/", { path: "playground/playground-v1-1" })).toBe(
      "http://127.0.0.1:8765/#/r/playground%2Fplayground-v1-1/map",
    );
    const now = Date.parse("2026-10-14T12:00:00Z");
    expect(ago("2026-10-14T11:59:30Z", now)).toBe("just now");
    expect(ago("2026-10-14T09:00:00Z", now)).toBe("3h ago");
    expect(ago("2026-10-11T12:00:00Z", now)).toBe("3d ago");
    expect(ago(undefined, now)).toBe("");
  });
});

describe("theme", () => {
  test("tokens resolve through var() and ignore comments", () => {
    const t = parseTokens(":root { --blue-500: #4da3ff; /* --fake: red; */ --accent: var(--blue-500); --x: var(--accent); }");
    expect(resolveToken(t, "x")).toBe("#4da3ff");
    expect(t.has("fake")).toBe(false);
    expect(() => resolveToken(t, "missing")).toThrow("--missing");
  });

  test("the terminal palette is the dashboard's", () => {
    expect(C.accent).toBe("#4da3ff");
    for (const value of Object.values(C)) expect(value).toMatch(/^#[0-9a-f]{6}$/i);
  });
});
