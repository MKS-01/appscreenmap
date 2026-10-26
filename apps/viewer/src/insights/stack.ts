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

export interface StackFacts {
  platform: "android" | "ios";
  package: string;
  version?: string | null;
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
  stack: { kind: "native" | "cross-platform" | "kmp"; summary: string };
  signals: StackSignal[];
  native_libs: { name: string; abis: string[]; library?: StackLibrary }[];
  components: { name: string; library: StackLibrary }[];
  libraries: { name: string; version: string }[];
  storage: StackStorage[];
  page_16k: { path: string; abi: string; align: number | null; elf_ok: boolean; zip_ok: boolean | null }[];
  notes: string[];
}

export const isStackFacts = (f: unknown): f is StackFacts =>
  !!f && typeof f === "object" && Array.isArray((f as StackFacts).signals) && Array.isArray((f as StackFacts).storage);

/** Scan an installed app through `appscreenmap serve` (POST /api/stack). Resolves to the canvas folder. */
export async function scanStack(body: { package: string; serial?: string; run?: string }): Promise<{ run: string; path: string }> {
  const r = await fetch("/api/stack", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error ?? (r.status === 404 ? "Scanning needs the dashboard server: run appscreenmap serve." : `${r.status} ${r.statusText}`));
  return data;
}

export interface DeviceRow {
  serial: string;
  state: string;
  platform: "android";
  name?: string;
  api?: number | null;
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

export async function listApps(serial: string): Promise<{ package: string; run: string | null }[]> {
  const r = await fetch(`/api/devices/${encodeURIComponent(serial)}/apps`, { cache: "no-store" });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error ?? `${r.status} ${r.statusText}`);
  return data.apps;
}
