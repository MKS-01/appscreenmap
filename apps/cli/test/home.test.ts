import { describe, expect, test } from "bun:test";
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { compareVersions, Home, homeDir } from "../src/home";

const tempHome = () => new Home(mkdtempSync(join(tmpdir(), "asm-home-")));
const addViewer = (home: Home, v: string) => {
  mkdirSync(join(home.viewersDir, v), { recursive: true });
  writeFileSync(join(home.viewersDir, v, "index.html"), "<!doctype html>");
};

describe("home folder", () => {
  test("where it lives", () => {
    expect(homeDir({ HOME: "/Users/me" }, "darwin")).toBe("/Users/me/Library/Application Support/appscreenmap");
    expect(homeDir({ HOME: "/home/me" }, "linux")).toBe("/home/me/.local/share/appscreenmap");
    expect(homeDir({ HOME: "/home/me", XDG_DATA_HOME: "/data" }, "linux")).toBe("/data/appscreenmap");
    expect(homeDir({ APPSCREENMAP_HOME: "/x", HOME: "/Users/me" }, "darwin")).toBe("/x");
  });

  test("config has defaults and keeps what's saved", () => {
    const home = tempHome();
    expect(home.config()).toEqual({ updateCheck: true });
    home.saveConfig({ updateCheck: false });
    expect(home.config()).toEqual({ updateCheck: false });
  });

  test("viewer versions: install, switch, never remove the active one", () => {
    const home = tempHome();
    expect(home.currentViewer()).toBeNull();
    addViewer(home, "0.10.0");
    addViewer(home, "0.9.0");
    expect(home.viewers()).toEqual(["0.9.0", "0.10.0"]);
    home.useViewer("0.10.0");
    expect(home.currentViewer()).toBe("0.10.0");
    expect(home.currentViewerDir()).toBe(join(home.viewersDir, "0.10.0"));
    home.useViewer("0.9.0");
    expect(home.currentViewer()).toBe("0.9.0");
    expect(() => home.removeViewer("0.9.0")).toThrow("active");
    home.removeViewer("0.10.0");
    expect(home.viewers()).toEqual(["0.9.0"]);
    expect(() => home.useViewer("1.0.0")).toThrow("isn't installed");
  });

  test("versions compare numerically, pre-releases first", () => {
    expect(compareVersions("0.10.0", "0.9.9")).toBe(1);
    expect(compareVersions("1.0.0", "1.0.0")).toBe(0);
    expect(compareVersions("1.0.0-rc.1", "1.0.0")).toBe(-1);
    expect(compareVersions("1.0", "1.0.1")).toBe(-1);
  });
});
