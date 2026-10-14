// What's connected: Android devices over adb, booted iOS simulators over simctl. Read-only and quick.

export interface AndroidDevice {
  serial: string;
  state: string; // "device" when ready; "unauthorized", "offline", …
  model?: string;
}

export interface Simulator {
  udid: string;
  name: string;
  runtime: string; // "iOS 27.0"
}

/** `adb devices -l` output. */
export function parseAdbDevices(text: string): AndroidDevice[] {
  const out: AndroidDevice[] = [];
  for (const line of text.split("\n")) {
    const parts = line.trim().split(/\s+/);
    if (parts.length < 2 || line.startsWith("List of devices") || line.startsWith("*")) continue;
    const [serial, state, ...rest] = parts as [string, string, ...string[]];
    const model = rest.find((r) => r.startsWith("model:"))?.slice(6).replace(/_/g, " ");
    out.push({ serial, state, ...(model ? { model } : {}) });
  }
  return out;
}

/** `xcrun simctl list devices booted -j` output. */
export function parseSimctlBooted(json: string): Simulator[] {
  const data = JSON.parse(json) as { devices?: Record<string, { udid: string; name: string; state: string }[]> };
  const out: Simulator[] = [];
  for (const [runtimeId, devices] of Object.entries(data.devices ?? {})) {
    const m = runtimeId.match(/SimRuntime\.(\w+)-([\d-]+)$/);
    const runtime = m ? `${m[1]} ${m[2]!.replace(/-/g, ".")}` : runtimeId;
    for (const d of devices) if (d.state === "Booted") out.push({ udid: d.udid, name: d.name, runtime });
  }
  return out;
}

async function output(cmd: string[], timeoutMs = 4000): Promise<string | null> {
  try {
    const proc = Bun.spawn(cmd, { stdout: "pipe", stderr: "ignore" });
    const timer = setTimeout(() => proc.kill(), timeoutMs);
    const text = await new Response(proc.stdout).text();
    clearTimeout(timer);
    return (await proc.exited) === 0 ? text : null;
  } catch {
    return null;
  }
}

/** Connected Android devices, or null when adb isn't installed. */
export async function androidDevices(): Promise<AndroidDevice[] | null> {
  const adb = Bun.which("adb");
  if (!adb) return null;
  const text = await output([adb, "devices", "-l"]);
  return text === null ? [] : parseAdbDevices(text);
}

/** Booted iOS simulators, or null off macOS / without Xcode. */
export async function simulators(): Promise<Simulator[] | null> {
  if (process.platform !== "darwin" || !Bun.which("xcrun")) return null;
  const text = await output(["xcrun", "simctl", "list", "devices", "booted", "-j"]);
  try {
    return text === null ? [] : parseSimctlBooted(text);
  } catch {
    return [];
  }
}
