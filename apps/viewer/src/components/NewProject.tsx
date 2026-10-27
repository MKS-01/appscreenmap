import { useEffect, useMemo, useState } from "react";
import { listApps, listDevices, scanStack, type DeviceRow } from "../insights/stack";
import { href } from "../router";
import { Icon } from "./Icon";

// Start a project from an app already installed on the emulator or a booted iOS simulator: pick the device, pick
// the app, scan its stack.
// The scan makes the app's canvas (no screens yet); a crawl merges into it later. Needs `appscreenmap serve`.

type Apps = { package: string; run: string | null }[];

export default function NewProject({ onClose }: { onClose: () => void }) {
  const [devices, setDevices] = useState<DeviceRow[] | null | undefined>(undefined); // undefined: loading, null: not served
  const [serial, setSerial] = useState<string | null>(null);
  const [apps, setApps] = useState<Apps | null>(null);
  const platform = devices?.find((d) => d.serial === serial)?.platform ?? "android";
  const [filter, setFilter] = useState("");
  const [scanning, setScanning] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = () => {
    setDevices(undefined);
    listDevices().then((d) => {
      setDevices(d);
      const ready = d?.filter((x) => x.state === "device") ?? [];
      setSerial((s) => (s && ready.some((x) => x.serial === s) ? s : (ready[0]?.serial ?? null)));
    });
  };
  useEffect(refresh, []);
  useEffect(() => {
    if (!serial) return;
    setApps(null);
    setError(null);
    listApps(serial, platform).then(setApps, (e) => setError(String(e.message ?? e)));
  }, [serial, platform]);

  const shown = useMemo(() => (apps ?? []).filter((a) => a.package.toLowerCase().includes(filter.trim().toLowerCase())), [apps, filter]);

  const scan = async (pkg: string) => {
    setScanning(pkg);
    setError(null);
    try {
      const { path } = await scanStack({ package: pkg, platform, serial: serial ?? undefined });
      location.hash = href("r", path, "insights", "stack");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setScanning(null);
    }
  };

  return (
    <section className="panel newproj" aria-labelledby="newproj-title">
      <div className="newproj-head">
        <div className="grow">
          <h2 id="newproj-title">New project</h2>
          <p className="small muted">
            Pick an app installed on the emulator or an iOS simulator. AppScreenMap reads what it's built with and makes its canvas; map
            the screens after.
          </p>
        </div>
        <button className="btn icon-only" onClick={onClose} aria-label="Close">
          <Icon name="x" size={14} />
        </button>
      </div>

      {devices === undefined && <p className="small muted">Looking for devices…</p>}
      {devices === null && (
        <p className="small muted">
          Scanning from here needs the dashboard server: run <code>appscreenmap serve</code>. In a terminal:{" "}
          <code>appscreenmap stack --package &lt;app&gt;</code> (add <code>--platform ios</code> for a simulator)
        </p>
      )}
      {devices && devices.filter((d) => d.state === "device").length === 0 && (
        <div className="row wrap" style={{ gap: 10 }}>
          <span className="small muted grow">
            No emulator or simulator is running. Start one (Android Studio's Device Manager, or Xcode's Devices window), install the app, then look
            again.
          </span>
          <button className="btn" onClick={refresh}>
            Look again
          </button>
        </div>
      )}

      {devices && devices.some((d) => d.state === "device") && (
        <>
          <div className="newproj-step">
            <span className="ins-kicker">1 · Device</span>
            <div className="seg" role="group" aria-label="Device">
              {devices
                .filter((d) => d.state === "device")
                .map((d) => (
                  <button key={d.serial} aria-pressed={serial === d.serial} className={serial === d.serial ? "on" : ""} onClick={() => setSerial(d.serial)}>
                    <Icon name={d.platform === "ios" ? "apple" : "android"} size={13} /> {d.name ?? d.serial}
                    {d.platform === "ios"
                      ? d.ios && <span className="faint mono"> {d.ios}</span>
                      : d.api != null && <span className="faint mono"> API {d.api}</span>}
                  </button>
                ))}
            </div>
          </div>

          <div className="newproj-step">
            <div className="row wrap" style={{ gap: 10 }}>
              <span className="ins-kicker grow">2 · App {apps && `· ${apps.length} installed`}</span>
              <input
                className="newproj-filter"
                type="search"
                placeholder="Filter by package"
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                aria-label="Filter apps by package"
              />
            </div>
            {!apps && !error && <p className="small muted">Reading installed apps…</p>}
            {apps && apps.length === 0 && (
              <p className="small muted">
                No apps installed besides the system ones. Install the build first (
                {platform === "ios" ? "xcrun simctl install booted <App>.app" : "adb install"}).
              </p>
            )}
            {shown.length > 0 && (
              <ul className="newproj-apps">
                {shown.map((a) => (
                  <li key={a.package}>
                    <span className="mono grow ellipsis" title={a.package}>
                      {a.package}
                    </span>
                    {a.run && <span className="chip">has a canvas</span>}
                    <button className="btn small" disabled={scanning !== null} onClick={() => scan(a.package)} aria-busy={scanning === a.package}>
                      <Icon name="scan" size={13} /> {scanning === a.package ? "Scanning…" : a.run ? "Scan again" : "Scan"}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
          {scanning && (
            <p className="small muted" aria-live="polite">
              {platform === "ios"
                ? "Reading the app's Info.plist, frameworks and binaries from the simulator."
                : "Reading the package, pulling its APKs from the device and fingerprinting them."}{" "}
              Large apps take a minute.
            </p>
          )}
        </>
      )}
      {error && (
        <p className="stack-error small" role="alert">
          {error}
        </p>
      )}
    </section>
  );
}
