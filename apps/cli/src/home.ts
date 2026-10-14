// The CLI's home folder: config, installed viewer versions, download cache, the running dashboard's record.
//   macOS  ~/Library/Application Support/appscreenmap   (APPSCREENMAP_HOME overrides; Linux uses XDG_DATA_HOME)
import { existsSync, lstatSync, mkdirSync, readdirSync, readFileSync, readlinkSync, renameSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

export function homeDir(env: Record<string, string | undefined> = process.env, platform = process.platform): string {
  if (env.APPSCREENMAP_HOME) return env.APPSCREENMAP_HOME;
  const home = env.HOME || homedir();
  if (platform === "darwin") return join(home, "Library", "Application Support", "appscreenmap");
  return join(env.XDG_DATA_HOME || join(home, ".local", "share"), "appscreenmap");
}

export interface Config {
  updateCheck: boolean; // look for a newer release at most once a day when the terminal home starts
  releaseUrl?: string; // where releases come from (default: the project's GitHub Releases)
}

const DEFAULTS: Config = { updateCheck: true };

export class Home {
  constructor(readonly dir: string = homeDir()) {}

  get configFile() {
    return join(this.dir, "config.json");
  }
  get viewersDir() {
    return join(this.dir, "viewer");
  }
  get cacheDir() {
    return join(this.dir, "cache");
  }
  get dashboardFile() {
    return join(this.dir, "dashboard.json");
  }

  config(): Config {
    try {
      return { ...DEFAULTS, ...(JSON.parse(readFileSync(this.configFile, "utf8")) as Partial<Config>) };
    } catch {
      return { ...DEFAULTS };
    }
  }

  saveConfig(patch: Partial<Config>): Config {
    const next = { ...this.config(), ...patch };
    this.writeJson(this.configFile, next);
    return next;
  }

  /** Installed viewer versions, oldest first. */
  viewers(): string[] {
    if (!existsSync(this.viewersDir)) return [];
    return readdirSync(this.viewersDir)
      .filter((v) => v !== "current" && !v.startsWith(".") && existsSync(join(this.viewersDir, v, "index.html")))
      .sort(compareVersions);
  }

  /** The active viewer version (the `current` link), or null. */
  currentViewer(): string | null {
    const link = join(this.viewersDir, "current");
    try {
      return lstatSync(link).isSymbolicLink() ? readlinkSync(link) : null;
    } catch {
      return null;
    }
  }

  currentViewerDir(): string | null {
    const v = this.currentViewer();
    return v && existsSync(join(this.viewersDir, v, "index.html")) ? join(this.viewersDir, v) : null;
  }

  /** Point `current` at an installed version (an atomic swap of the link). */
  useViewer(version: string): void {
    if (!existsSync(join(this.viewersDir, version, "index.html"))) throw new Error(`viewer ${version} isn't installed`);
    const tmp = join(this.viewersDir, `.current-${process.pid}`);
    rmSync(tmp, { force: true });
    symlinkSync(version, tmp);
    renameSync(tmp, join(this.viewersDir, "current"));
  }

  removeViewer(version: string): void {
    if (version === this.currentViewer()) throw new Error(`viewer ${version} is the active one`);
    rmSync(join(this.viewersDir, version), { recursive: true, force: true });
  }

  readJson<T>(file: string): T | null {
    try {
      return JSON.parse(readFileSync(file, "utf8")) as T;
    } catch {
      return null;
    }
  }

  writeJson(file: string, data: unknown): void {
    mkdirSync(join(file, ".."), { recursive: true });
    const tmp = `${file}.${process.pid}.tmp`;
    writeFileSync(tmp, JSON.stringify(data, null, 1) + "\n");
    renameSync(tmp, file);
  }
}

/** Compare dotted versions numerically ("0.10.0" > "0.9.1"); a pre-release suffix sorts before the release. */
export function compareVersions(a: string, b: string): number {
  const [ma, pa = ""] = a.split("-", 2) as [string, string?];
  const [mb, pb = ""] = b.split("-", 2) as [string, string?];
  const na = ma.split(".").map(Number);
  const nb = mb.split(".").map(Number);
  for (let i = 0; i < Math.max(na.length, nb.length); i++) {
    const d = (na[i] ?? 0) - (nb[i] ?? 0);
    if (d) return d < 0 ? -1 : 1;
  }
  if (pa === pb) return 0;
  return pa === "" ? 1 : pb === "" ? -1 : pa < pb ? -1 : 1;
}
