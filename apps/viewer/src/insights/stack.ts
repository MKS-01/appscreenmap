// audits/stack.json's `facts` block (docs/MAP_SCHEMA.md, "audits/stack.json"), written by `appscreenmap stack`.

export type Confidence = "certain" | "strong" | "likely";
export type SignalSource = "device" | "runtime";

export interface StackSignal {
  id: string;
  label: string;
  category: "framework" | "runtime" | "language" | "ui" | "kmp";
  confidence: Confidence;
  evidence: string[];
  source: SignalSource;
}

export interface StackLibrary {
  label: string;
  team?: string | null;
  url?: string | null;
}

export interface StackStorage {
  id: string;
  label: string;
  encrypted: boolean | null;
  locations: string[];
  confidence: Confidence;
  evidence: string[];
  source: SignalSource;
}

interface StackFactsBase {
  package: string;
  version?: string | null;
  stack: { kind: "native" | "cross-platform" | "kmp"; summary: string };
  signals: StackSignal[];
  storage: StackStorage[];
  notes: string[];
}

export interface AndroidStackFacts extends StackFactsBase {
  platform: "android";
  version_code?: number | null;
  min_sdk?: number | null;
  target_sdk?: number | null;
  compile_sdk?: number | null;
  debuggable?: boolean | null;
  installer?: string | null;
  signing_version?: number | null;
  primary_abi?: string | null;
  apks: string[];
  abis: string[];
  native_libs: { name: string; abis: string[]; library?: StackLibrary }[];
  components: { name: string; library: StackLibrary }[];
  libraries: { name: string; version: string }[];
  page_16k: { path: string; abi: string; align: number | null; elf_ok: boolean; zip_ok: boolean | null }[];
}

/** Read from the `.app` on a booted simulator: Info.plist, Frameworks/ and the Mach-O load commands. */
export interface IosStackFacts extends StackFactsBase {
  platform: "ios";
  app: string;
  executable?: string | null;
  debug_build: boolean;
  build?: string | null;
  label?: string | null;
  deployment_target?: string | null;
  build_sdk?: string | null;
  xcode?: string | null;
  simulator_build?: boolean | null;
  min_os?: string | null;
  sdk?: string | null;
  binary_platform?: string | null;
  arches: string[];
  /** FairPlay: true for an App Store build, null when the binary has no encryption command. */
  encrypted: boolean | null;
  frameworks: { name: string; version?: string }[];
  linked: string[];
  data_container?: string | null;
}

export type StackFacts = AndroidStackFacts | IosStackFacts;

export const isStackFacts = (f: unknown): f is StackFacts =>
  !!f && typeof f === "object" && Array.isArray((f as StackFacts).signals) && Array.isArray((f as StackFacts).storage);

/** Scan an installed app through `appscreenmap serve` (POST /api/stack). Resolves to the canvas folder. */
export async function scanStack(body: { package: string; platform?: "android" | "ios"; serial?: string; run?: string }): Promise<{ run: string; path: string }> {
  const r = await fetch("/api/stack", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error ?? (r.status === 404 ? "Scanning needs the dashboard server: run appscreenmap serve." : `${r.status} ${r.statusText}`));
  return data;
}

export interface DeviceRow {
  serial: string;
  state: string;
  platform: "android" | "ios";
  name?: string;
  api?: number | null;
  /** iOS release of a simulator, "iOS 27.0". */
  ios?: string | null;
  android?: string | null;
  build_type?: string | null;
}

/** null: not served by `appscreenmap serve` (a static host), so the scan can't start from the page. */
export async function listDevices(): Promise<DeviceRow[] | null> {
  try {
    const r = await fetch("/api/devices", { cache: "no-store" });
    if (!r.ok) return null;
    return ((await r.json()) as { devices: DeviceRow[] }).devices;
  } catch {
    return null;
  }
}

export async function listApps(serial: string, platform: "android" | "ios" = "android"): Promise<{ package: string; run: string | null }[]> {
  const r = await fetch(`/api/devices/${encodeURIComponent(serial)}/apps?platform=${platform}`, { cache: "no-store" });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error ?? `${r.status} ${r.statusText}`);
  return data.apps;
}
