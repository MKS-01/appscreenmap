// Releases: where they come from, what's in one (manifest.json), downloading with SHA-256 checks, and installing the
// engine (uv tool), the viewer (home folder) and this binary. A release is a flat folder of files, served from GitHub
// Releases or, for testing, a local folder (APPSCREENMAP_RELEASE_URL=file:///…/dist/release/, from `make release-local`).
import { chmodSync, existsSync, mkdirSync, renameSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { compareVersions, type Config, type Home } from "./home";

export const DEFAULT_RELEASE_URL = "https://github.com/MKS-01/appscreenmap/releases/latest/download/";
export const ENGINE_DIST = "appscreenmap-engine";

export interface FileRef {
  file: string; // a name in the release folder
  sha256: string;
}

export interface Manifest {
  version: string;
  map_schema: number;
  cli: { version: string; binaries: Record<string, FileRef> }; // "darwin-arm64" → the binary
  engine: { version: string; wheels: FileRef[] };
  viewer: FileRef & { version: string; map_schema: number; min_cli: string };
}

export function releaseUrl(env: Record<string, string | undefined> = process.env, config?: Config): string {
  const url = env.APPSCREENMAP_RELEASE_URL || config?.releaseUrl || DEFAULT_RELEASE_URL;
  return url.endsWith("/") ? url : `${url}/`;
}

/** "darwin-arm64" / "darwin-x64": the platforms binaries are built for (macOS first). */
export function platformKey(platform = process.platform, arch = process.arch): string | null {
  if (platform !== "darwin") return null;
  return arch === "arm64" ? "darwin-arm64" : arch === "x64" ? "darwin-x64" : null;
}

export async function fetchBytes(url: string, timeoutMs = 60_000): Promise<Uint8Array> {
  if (url.startsWith("file:")) {
    const file = Bun.file(fileURLToPath(url));
    if (!(await file.exists())) throw new Error(`not found: ${url}`);
    return new Uint8Array(await file.arrayBuffer());
  }
  const res = await fetch(url, { signal: AbortSignal.timeout(timeoutMs), redirect: "follow" });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}: ${url}`);
  return new Uint8Array(await res.arrayBuffer());
}

export function sha256(bytes: Uint8Array): string {
  return new Bun.CryptoHasher("sha256").update(bytes).digest("hex");
}

export function parseManifest(json: string): Manifest {
  const m = JSON.parse(json) as Manifest;
  const ok =
    typeof m.version === "string" &&
    typeof m.map_schema === "number" &&
    typeof m.cli?.version === "string" &&
    typeof m.engine?.version === "string" &&
    Array.isArray(m.engine.wheels) &&
    typeof m.viewer?.version === "string" &&
    typeof m.viewer.sha256 === "string";
  if (!ok) throw new Error("not an AppScreenMap release manifest");
  return m;
}

export async function fetchManifest(base: string, timeoutMs = 10_000): Promise<Manifest> {
  return parseManifest(new TextDecoder().decode(await fetchBytes(`${base}manifest.json`, timeoutMs)));
}

/** Download one release file into `dir`, refusing it if its SHA-256 doesn't match the manifest. */
export async function download(base: string, ref: FileRef, dir: string): Promise<string> {
  const bytes = await fetchBytes(base + ref.file);
  const got = sha256(bytes);
  if (got !== ref.sha256) throw new Error(`${ref.file}: checksum mismatch (expected ${ref.sha256.slice(0, 12)}…, got ${got.slice(0, 12)}…)`);
  mkdirSync(dir, { recursive: true });
  const path = join(dir, ref.file);
  writeFileSync(path, bytes);
  return path;
}

// ── what an update would do ──────────────────────────────────────────────────

export interface Installed {
  cli: string;
  cliCompiled: boolean; // a compiled binary can replace itself; `bun run` from source can't
  engine: string | null;
  engineSource: "env" | "checkout" | "path" | null;
  viewer: string | null;
  viewerSource: "checkout" | "home" | null;
}

export interface Step {
  from: string | null;
  to: string;
}

export interface UpdatePlan {
  cli?: Step;
  engine?: Step;
  viewer?: Step;
  notes: string[]; // why something newer isn't installed
}

const newer = (to: string, from: string | null) => from === null || compareVersions(to, from) > 0;

export function planUpdate(installed: Installed, m: Manifest, mapSchema: number): UpdatePlan {
  const plan: UpdatePlan = { notes: [] };
  if (newer(m.cli.version, installed.cli)) {
    if (installed.cliCompiled) plan.cli = { from: installed.cli, to: m.cli.version };
    else plan.notes.push(`cli ${m.cli.version} is out; this one runs from source: git pull`);
  }
  if (newer(m.engine.version, installed.engine)) {
    if (installed.engineSource === "checkout") plan.notes.push(`engine ${m.engine.version} is out; in a source checkout: git pull && make setup`);
    else if (installed.engineSource === "env") plan.notes.push(`engine ${m.engine.version} is out; $APPSCREENMAP_ENGINE points elsewhere, update it there`);
    else plan.engine = { from: installed.engine, to: m.engine.version };
  }
  if (installed.viewerSource !== "checkout" && newer(m.viewer.version, installed.viewer)) {
    if (m.viewer.map_schema !== mapSchema) plan.notes.push(`viewer ${m.viewer.version} reads map schema ${m.viewer.map_schema}; this CLI writes ${mapSchema}`);
    else if (compareVersions(installed.cli, m.viewer.min_cli) < 0 && !plan.cli) plan.notes.push(`viewer ${m.viewer.version} needs cli ${m.viewer.min_cli}`);
    else plan.viewer = { from: installed.viewer, to: m.viewer.version };
  }
  return plan;
}

export const planIsEmpty = (p: UpdatePlan) => !p.cli && !p.engine && !p.viewer;

// ── installing ───────────────────────────────────────────────────────────────

/** Download, check and unpack the viewer into the home folder, then make it the active one. */
export async function installViewer(home: Home, base: string, m: Manifest): Promise<string> {
  const tarball = await download(base, m.viewer, home.cacheDir);
  const dest = join(home.viewersDir, m.viewer.version);
  const tmp = `${dest}.tmp-${process.pid}`;
  rmSync(tmp, { recursive: true, force: true });
  mkdirSync(tmp, { recursive: true });
  const tar = Bun.spawnSync(["tar", "-xzf", tarball, "-C", tmp], { stderr: "pipe" });
  if (tar.exitCode !== 0) throw new Error(`couldn't unpack ${m.viewer.file}: ${tar.stderr.toString().trim()}`);
  if (!existsSync(join(tmp, "index.html"))) throw new Error(`${m.viewer.file} has no index.html`);
  rmSync(dest, { recursive: true, force: true });
  renameSync(tmp, dest);
  home.useViewer(m.viewer.version);
  return dest;
}

/** Download the engine's wheels and install them as a uv tool (`appscreenmap-engine` on PATH). Returns uv's exit code. */
export async function installEngine(home: Home, base: string, m: Manifest, uv: string): Promise<number> {
  const dir = join(home.cacheDir, `wheels-${m.engine.version}`);
  for (const w of m.engine.wheels) await download(base, w, dir);
  const proc = Bun.spawn(
    [uv, "tool", "install", "--force", "--find-links", dir, `${ENGINE_DIST}[mcp]==${m.engine.version}`],
    { stdio: ["inherit", "inherit", "inherit"] },
  );
  return proc.exited;
}

/** Replace the running binary with the release's one for this Mac (same folder, then an atomic rename). */
export async function installCli(base: string, m: Manifest, execPath = process.execPath): Promise<void> {
  const key = platformKey();
  const ref = key ? m.cli.binaries[key] : undefined;
  if (!ref) throw new Error(`no ${process.platform}-${process.arch} binary in release ${m.version}`);
  const dir = dirname(execPath);
  const downloaded = await download(base, ref, join(dir, ".appscreenmap-update"));
  chmodSync(downloaded, 0o755);
  renameSync(downloaded, execPath);
  rmSync(join(dir, ".appscreenmap-update"), { recursive: true, force: true });
}

// ── the daily check the terminal home does ───────────────────────────────────

interface CheckCache {
  checked_at: number;
  manifest: Manifest | null;
}

const DAY_MS = 24 * 60 * 60 * 1000;

export function updateCheckEnabled(home: Home, env: Record<string, string | undefined> = process.env): boolean {
  return !env.CI && !env.APPSCREENMAP_NO_UPDATE_CHECK && home.config().updateCheck;
}

/** The newest release manifest, fetched at most once a day (cached in the home folder); null when offline or none. */
export async function latestManifest(home: Home, base: string, now = Date.now()): Promise<Manifest | null> {
  const file = join(home.cacheDir, "update-check.json");
  const cached = home.readJson<CheckCache>(file);
  if (cached && now - cached.checked_at < DAY_MS) return cached.manifest;
  let manifest: Manifest | null = null;
  try {
    manifest = await fetchManifest(base, 3000);
  } catch {
    manifest = null; // offline, or no release published yet: never an error
  }
  home.writeJson(file, { checked_at: now, manifest } satisfies CheckCache);
  return manifest;
}
