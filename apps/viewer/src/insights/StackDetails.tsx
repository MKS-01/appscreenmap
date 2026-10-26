import { useEffect, useState } from "react";
import { Icon } from "../components/Icon";
import { href } from "../router";
import { fmtDate, plural } from "../util";

const libraries = (n: number, what = "") => `${n} ${what}${n === 1 ? "library" : "libraries"}`;
import { isStackFacts, listDevices, scanStack, type Confidence, type StackFacts, type StackStorage } from "./stack";
import type { AuditReport } from "./types";

// The App stack audit's own sections (audits/stack.json `facts`): what the build is, how sure each signal is,
// where the app keeps data, and which libraries it ships. The shared metrics and findings render around it.

const CONF_WORD: Record<Confidence, string> = { certain: "Certain", strong: "Strong", likely: "Likely" };
const CONF_HINT: Record<Confidence, string> = {
  certain: "Only this stack ships it (its runtime library)",
  strong: "A marker this stack's build leaves",
  likely: "A hint: often seen with this stack, not proof",
};
const KIND_WORD = { framework: "Framework", runtime: "Runtime", language: "Language", ui: "UI", kmp: "Multiplatform" };

const atRest = (s: StackStorage) =>
  s.encrypted === true
    ? { word: "Encrypted", color: "var(--good)" }
    : s.encrypted === false
      ? { word: "Plain", color: "var(--dim)" }
      : { word: "Optional", color: "var(--info)" };

export default function StackDetails({ run, report }: { run: string; report: AuditReport }) {
  if (!isStackFacts(report.facts)) return null;
  const f = report.facts;
  return (
    <div className="appstack">
      <Rescan run={run} facts={f} at={report.generated_at} />
      <BuildFacts f={f} />
      <Signals f={f} />
      <Storage run={run} f={f} />
      <PageSizes f={f} />
      <Libraries f={f} />
      {f.notes.length > 0 && (
        <ul className="stack-notes small">
          {f.notes.map((n) => (
            <li key={n}>
              <Icon name="alert" size={13} /> {n}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** Scan the installed build again (only with `appscreenmap serve`); a static host shows the command instead. */
function Rescan({ run, facts, at }: { run: string; facts: StackFacts; at?: string }) {
  const [served, setServed] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    listDevices().then((d) => setServed(d !== null));
  }, []);
  const cmd = `appscreenmap stack --package ${facts.package}`;
  const go = async () => {
    setBusy(true);
    setError(null);
    try {
      await scanStack({ package: facts.package, run });
      location.reload(); // the audit files are read once per run view
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  };
  return (
    <div className="stack-rescan">
      <span className="small muted grow">
        Read from the build installed on the emulator{at ? `, ${fmtDate(at)}` : ""}. Scan again after installing a new build.
      </span>
      {served ? (
        <button className="btn" onClick={go} disabled={busy} aria-busy={busy}>
          <Icon name="scan" size={14} /> {busy ? "Scanning…" : "Scan again"}
        </button>
      ) : (
        served === false && <code className="mono small">{cmd}</code>
      )}
      {error && (
        <span className="stack-error small" role="alert">
          {error}
        </span>
      )}
    </div>
  );
}

function BuildFacts({ f }: { f: StackFacts }) {
  const sdk = (n?: number | null) => (n == null ? "unknown" : String(n));
  const rows: [string, React.ReactNode][] = [
    ["Package", <span className="mono">{f.package}</span>],
    ["Version", f.version ? `${f.version}${f.version_code != null ? ` (${f.version_code})` : ""}` : "unknown"],
    ["SDK", <span className="mono">min {sdk(f.min_sdk)} · target {sdk(f.target_sdk)} · compile {sdk(f.compile_sdk)}</span>],
    ["ABIs", f.abis.length ? <span className="mono">{f.abis.join(" · ")}</span> : "No native code"],
    ["Installed by", f.installer ?? "adb (sideloaded)"],
    ["Build", f.debuggable ? "Debuggable (not the build users get)" : "Release (not debuggable)"],
    ["Signature", f.signing_version ? `APK Signature Scheme v${f.signing_version}` : "unknown"],
    ["APKs", <span className="mono">{f.apks.join(" · ")}</span>],
  ];
  return (
    <section className="ins-section">
      <h2 className="stack-h">Build</h2>
      <dl className="stack-facts">
        {rows.map(([k, v]) => (
          <div key={k}>
            <dt>{k}</dt>
            <dd>{v}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

function Signals({ f }: { f: StackFacts }) {
  const runtime = f.signals.some((s) => s.source === "runtime");
  return (
    <section className="ins-section">
      <h2 className="stack-h">What it's built with</h2>
      <div className="tbl-scroll">
        <table className="tbl stack-tbl">
          <thead>
            <tr>
              <th>Signal</th>
              <th>Kind</th>
              <th>Confidence</th>
              <th>Source</th>
              <th>Evidence</th>
            </tr>
          </thead>
          <tbody>
            {f.signals.map((s) => (
              <tr key={s.id}>
                <td>{s.label}</td>
                <td className="muted">{KIND_WORD[s.category] ?? s.category}</td>
                <td>
                  <span className={`stack-conf ${s.confidence}`} title={CONF_HINT[s.confidence]}>
                    {CONF_WORD[s.confidence]}
                  </span>
                </td>
                <td>
                  <span className="stack-src">{s.source}</span>
                </td>
                <td className="mono small faint stack-ev" title={s.evidence.join("\n")}>
                  {s.evidence[0]}
                  {s.evidence.length > 1 && ` +${s.evidence.length - 1}`}
                </td>
              </tr>
            ))}
            {!runtime && (
              <tr>
                <td>Runtime probe</td>
                <td className="muted">Frida</td>
                <td>
                  <span className="stack-conf not-run">Not run</span>
                </td>
                <td>
                  <span className="stack-src">runtime</span>
                </td>
                <td className="small muted">
                  Confirms what actually loads. Needs frida-tools and a Google APIs emulator image (planned).
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function Storage({ run, f }: { run: string; f: StackFacts }) {
  return (
    <section className="ins-section">
      <div className="ins-head">
        <h2 className="stack-h grow">Where it keeps data</h2>
        <a className="small" href={href("r", run, "insights", "security")}>
          Data at rest in Security →
        </a>
      </div>
      {f.storage.length === 0 ? (
        <p className="small muted">No storage library recognised. SharedPreferences and plain files are always possible.</p>
      ) : (
        <div className="tbl-scroll">
          <table className="tbl stack-tbl">
            <thead>
              <tr>
                <th>Storage</th>
                <th>At rest</th>
                <th>On the device</th>
              </tr>
            </thead>
            <tbody>
              {f.storage.map((s) => {
                const r = atRest(s);
                return (
                  <tr key={s.id}>
                    <td title={s.evidence.join("\n")}>{s.label}</td>
                    <td>
                      <span className="stack-rest" style={{ color: r.color }}>
                        {r.word}
                      </span>
                    </td>
                    <td className="mono small">{s.locations.length ? s.locations.join(" · ") : <span className="faint">keys in the Keystore, no file</span>}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      <p className="small faint">Bundled is not the same as used: each row is a library the build ships. Paths are under /data/data/{f.package}/.</p>
    </section>
  );
}

function PageSizes({ f }: { f: StackFacts }) {
  const bad = f.page_16k.filter((r) => !r.elf_ok || r.zip_ok === false);
  return (
    <section className="ins-section">
      <h2 className="stack-h">16 KB page sizes</h2>
      {f.page_16k.length === 0 ? (
        <p className="small muted">No 64-bit native libraries, so nothing to align.</p>
      ) : bad.length === 0 ? (
        <p className="small">
          <span className="stack-rest" style={{ color: "var(--good)" }}>
            Met
          </span>{" "}
          · {libraries(f.page_16k.length, "64-bit ")} aligned for 16 KB pages.
        </p>
      ) : (
        <ul className="stack-list mono small">
          {bad.map((r) => (
            <li key={r.path}>
              <span className="stack-rest" style={{ color: "var(--bad)" }}>
                Not aligned
              </span>{" "}
              {r.path} {r.align != null && <span className="faint">(LOAD align {r.align})</span>}
              {r.zip_ok === false && <span className="faint"> · stored off a 16 KB boundary</span>}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function Libraries({ f }: { f: StackFacts }) {
  const known = [
    ...f.native_libs.filter((n) => n.library).map((n) => ({ name: n.name, lib: n.library! })),
    ...f.components.map((c) => ({ name: c.name, lib: c.library })),
  ];
  const unknownNative = f.native_libs.filter((n) => !n.library);
  return (
    <section className="ins-section">
      <h2 className="stack-h">Libraries</h2>
      <details className="stack-more">
        <summary>
          {libraries(known.length, "known ")} · {plural(f.libraries.length, "versioned artifact")}
          {unknownNative.length > 0 && ` · ${libraries(unknownNative.length, "other native ")}`}
        </summary>
        {known.length > 0 && (
          <div className="tbl-scroll">
            <table className="tbl stack-tbl">
              <thead>
                <tr>
                  <th>Library</th>
                  <th>By</th>
                  <th>Found as</th>
                </tr>
              </thead>
              <tbody>
                {known.map((k) => (
                  <tr key={k.name}>
                    <td>{k.lib.url ? <a href={k.lib.url} target="_blank" rel="noreferrer">{k.lib.label} ↗</a> : k.lib.label}</td>
                    <td className="muted">{k.lib.team ?? "—"}</td>
                    <td className="mono small faint stack-ev">{k.name}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {f.libraries.length > 0 && (
          <ul className="stack-versions mono small">
            {f.libraries.map((l) => (
              <li key={l.name}>
                <span className="faint">{l.name}</span> {l.version}
              </li>
            ))}
          </ul>
        )}
        {unknownNative.length > 0 && <p className="mono small faint">{unknownNative.map((n) => n.name).join(" · ")}</p>}
        <p className="small faint">
          Library names: <a href="https://github.com/LibChecker/LibChecker-Rules" target="_blank" rel="noreferrer">LibChecker-Rules ↗</a> (Apache-2.0).
          Versions: the build's META-INF/*.version files.
        </p>
      </details>
    </section>
  );
}
