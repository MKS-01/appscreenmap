import { describe, expect, test } from "bun:test";
import { existsSync, mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import { Home } from "../src/home";
import {
  DEFAULT_RELEASE_URL,
  download,
  installViewer,
  latestManifest,
  parseManifest,
  planUpdate,
  platformKey,
  releaseUrl,
  sha256,
  type Installed,
  type Manifest,
} from "../src/release";

function manifest(over: Partial<{ cli: string; engine: string; viewer: string; schema: number; minCli: string }> = {}): Manifest {
  return {
    version: over.cli ?? "0.2.0",
    map_schema: 1,
    cli: { version: over.cli ?? "0.2.0", binaries: { "darwin-arm64": { file: "appscreenmap-darwin-arm64", sha256: "x" } } },
    engine: { version: over.engine ?? "0.2.0", wheels: [] },
    viewer: { file: "viewer.tar.gz", sha256: "x", version: over.viewer ?? "0.2.0", map_schema: over.schema ?? 1, min_cli: over.minCli ?? "0.1.0" },
  };
}
const installed = (over: Partial<Installed> = {}): Installed => ({
  cli: "0.1.0", cliCompiled: true, engine: "0.1.0", engineSource: "path", viewer: "0.1.0", viewerSource: "home", ...over,
});

describe("what an update would do", () => {
  test("everything newer, from a normal install", () => {
    const plan = planUpdate(installed(), manifest(), 1);
    expect(plan).toEqual({
      cli: { from: "0.1.0", to: "0.2.0" }, engine: { from: "0.1.0", to: "0.2.0" }, viewer: { from: "0.1.0", to: "0.2.0" }, notes: [],
    });
  });

  test("up to date", () => {
    expect(planUpdate(installed({ cli: "0.2.0", engine: "0.2.0", viewer: "0.2.0" }), manifest(), 1)).toEqual({ notes: [] });
  });

  test("a source checkout updates with git, not the release", () => {
    const plan = planUpdate(installed({ cliCompiled: false, engineSource: "checkout", viewerSource: "checkout" }), manifest(), 1);
    expect(plan.cli ?? plan.engine ?? plan.viewer).toBeUndefined();
    expect(plan.notes.join(" ")).toContain("git pull");
  });

  test("a viewer for another map schema, or a newer CLI than this one, isn't installed", () => {
    expect(planUpdate(installed(), manifest({ schema: 2 }), 1).viewer).toBeUndefined();
    const needsCli = planUpdate(installed({ cliCompiled: false }), manifest({ minCli: "0.2.0" }), 1);
    expect(needsCli.viewer).toBeUndefined();
    expect(needsCli.notes.some((n) => n.includes("needs cli 0.2.0"))).toBe(true);
    // …but it is when this update also brings that CLI
    expect(planUpdate(installed(), manifest({ minCli: "0.2.0" }), 1).viewer).toEqual({ from: "0.1.0", to: "0.2.0" });
  });

  test("nothing installed yet", () => {
    expect(planUpdate(installed({ engine: null, engineSource: null, viewer: null, viewerSource: null }), manifest(), 1).engine).toEqual({ from: null, to: "0.2.0" });
  });
});

describe("release files", () => {
  test("release URL and platform", () => {
    expect(releaseUrl({})).toBe(DEFAULT_RELEASE_URL);
    expect(releaseUrl({ APPSCREENMAP_RELEASE_URL: "file:///tmp/r" })).toBe("file:///tmp/r/");
    expect(releaseUrl({}, { updateCheck: true, releaseUrl: "https://x/y/" })).toBe("https://x/y/");
    expect([platformKey("darwin", "arm64"), platformKey("darwin", "x64"), platformKey("linux", "x64")]).toEqual(["darwin-arm64", "darwin-x64", null]);
  });

  test("manifest validation", () => {
    expect(parseManifest(JSON.stringify(manifest())).cli.version).toBe("0.2.0");
    expect(() => parseManifest('{"version": "1"}')).toThrow("not an AppScreenMap release");
  });

  test("downloads are checked against the manifest", async () => {
    const rel = mkdtempSync(join(tmpdir(), "asm-rel-"));
    writeFileSync(join(rel, "a.bin"), "hello");
    const base = pathToFileURL(rel).href + "/";
    const dest = mkdtempSync(join(tmpdir(), "asm-dl-"));
    const good = sha256(new TextEncoder().encode("hello"));
    expect(await download(base, { file: "a.bin", sha256: good }, dest)).toBe(join(dest, "a.bin"));
    await expect(download(base, { file: "a.bin", sha256: "0".repeat(64) }, mkdtempSync(join(tmpdir(), "asm-dl-")))).rejects.toThrow("checksum mismatch");
  });

  test("a viewer bundle unpacks into the home folder and becomes the active one", async () => {
    const rel = mkdtempSync(join(tmpdir(), "asm-rel-"));
    const stage = join(rel, "stage");
    mkdirSync(stage);
    writeFileSync(join(stage, "index.html"), "<!doctype html>");
    Bun.spawnSync(["tar", "-czf", join(rel, "viewer.tar.gz"), "-C", stage, "."]);
    const m = manifest({ viewer: "0.3.0" });
    m.viewer.sha256 = sha256(new Uint8Array(await Bun.file(join(rel, "viewer.tar.gz")).arrayBuffer()));
    const home = new Home(mkdtempSync(join(tmpdir(), "asm-home-")));
    await installViewer(home, pathToFileURL(rel).href + "/", m);
    expect(home.currentViewer()).toBe("0.3.0");
    expect(existsSync(join(home.viewersDir, "0.3.0", "index.html"))).toBe(true);
  });

  test("the daily check fetches once a day and treats 'no release' as nothing new", async () => {
    const home = new Home(mkdtempSync(join(tmpdir(), "asm-home-")));
    const rel = mkdtempSync(join(tmpdir(), "asm-rel-"));
    const base = pathToFileURL(rel).href + "/";
    expect(await latestManifest(home, base, 1_000)).toBeNull(); // nothing published
    writeFileSync(join(rel, "manifest.json"), JSON.stringify(manifest()));
    expect(await latestManifest(home, base, 2_000)).toBeNull(); // cached for a day
    expect((await latestManifest(home, base, 1_000 + 25 * 3600_000))?.version).toBe("0.2.0");
  });
});
