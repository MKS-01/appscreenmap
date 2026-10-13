import { useEffect, useState } from "react";
import { CopyButton, Stat, StatusBadge } from "../components/common";
import { Icon, type IconName } from "../components/Icon";
import { Bars, Columns, Meter, SampleTag, Split } from "../insights/charts";
import { STATUS_HELP, STATUSES, statusColor } from "../util";

// Living reference for the viewer's design system (web/DESIGN.md). Renders the real tokens and classes,
// so it can't drift from the CSS. Not linked in the nav; open #/design.

const COLOR_TOKENS: [string, string][] = [
  ["--bg", "Page background"],
  ["--panel", "Cards, bars"],
  ["--panel-2", "Insets, code, hover"],
  ["--border", "Hairlines"],
  ["--text", "Primary text"],
  ["--muted", "Secondary text"],
  ["--faint", "Tertiary, ids"],
  ["--accent", "Primary action, focus"],
  ["--accent-soft", "Selected background"],
  ["--accent-text", "Links, selected text"],
];
const ICONS: IconName[] = [
  "map", "grid", "replay", "chart", "a11y", "compare", "rocket", "eye", "scan", "pointer", "database", "file", "folder",
  "image", "test", "check", "alert", "shield", "route", "sliders", "terminal", "hash", "bot", "cpu", "user", "message", "smartphone", "copy", "arrow", "play", "pause",
];

function useToken(name: string) {
  const [v, setV] = useState("");
  useEffect(() => {
    const read = () => setV(getComputedStyle(document.documentElement).getPropertyValue(name).trim());
    read();
    const m = matchMedia("(prefers-color-scheme: dark)");
    m.addEventListener("change", read);
    return () => m.removeEventListener("change", read);
  }, [name]);
  return v;
}

function Swatch({ token, role }: { token: string; role: string }) {
  const v = useToken(token);
  return (
    <div className="ds-swatch">
      <span className="ds-chip" style={{ background: `var(${token})` }} />
      <code>{token}</code>
      <span className="small muted">{role}</span>
      <span className="mono faint small">{v}</span>
    </div>
  );
}

function Block({ title, note, children }: { title: string; note?: string; children: React.ReactNode }) {
  return (
    <section className="ds-block">
      <div className="ds-block-head">
        <h3>{title}</h3>
        {note && <span className="small muted">{note}</span>}
      </div>
      <div className="panel panel-pad">{children}</div>
    </section>
  );
}

export default function DesignSystem() {
  const [replay, setReplay] = useState(0);
  const [seg, setSeg] = useState("a");
  return (
    <div className="page">
      <header className="how-head">
        <span className="how-badge">
          <Icon name="sliders" size={14} /> Design system
        </span>
        <h1 className="how-title">Viewer design system</h1>
        <p className="how-lede">
          Tokens and components exactly as the CSS renders them, in the current theme. The rules live in <code>web/DESIGN.md</code>;
          tokens in <code>web/src/tokens.css</code>.
        </p>
      </header>

      <Block title="Colour roles" note="Switch the OS theme to check dark mode">
        <div className="ds-swatches">
          {COLOR_TOKENS.map(([t, r]) => (
            <Swatch key={t} token={t} role={r} />
          ))}
        </div>
      </Block>

      <Block title="Status colours" note="Element outcomes; also used for severities">
        <div className="ds-swatches">
          {STATUSES.map((s) => (
            <div key={s} className="ds-swatch">
              <span className="ds-chip" style={{ background: statusColor(s) }} />
              <code>--st-{s}</code>
              <span className="small muted">{STATUS_HELP[s]}</span>
            </div>
          ))}
        </div>
      </Block>

      <Block title="Type" note="System UI font; mono for ids, code, numbers that align">
        <div className="col" style={{ gap: 10 }}>
          <div className="how-title">Display: hero and page titles</div>
          <h1>h1: view title (22px / 650)</h1>
          <h2>h2: card and section title (16px / 620)</h2>
          <h3>h3: eyebrow label (13px, uppercase)</h3>
          <p style={{ margin: 0 }}>Body: 14px / 1.5. Sentences, not fragments.</p>
          <span className="muted">Muted: secondary information.</span>
          <span className="small faint">Small faint: hints and metadata.</span>
          <span className="sid">s003 · mono id</span>
        </div>
      </Block>

      <Block title="Buttons and controls" note="Press any of them: scale(0.97) feedback">
        <div className="row wrap" style={{ gap: 10 }}>
          <button className="btn primary">Primary</button>
          <button className="btn">Secondary</button>
          <button className="btn">
            <Icon name="play" size={14} /> With icon
          </button>
          <button className="btn" disabled>
            Disabled
          </button>
          <CopyButton text="appscreenmap serve" />
          <div className="seg">
            {["a", "b", "c"].map((k) => (
              <button key={k} className={seg === k ? "on" : ""} onClick={() => setSeg(k)}>
                Segment {k.toUpperCase()}
              </button>
            ))}
          </div>
          <button className="chip on">Chip on</button>
          <button className="chip">Chip</button>
          <label className="check">
            <input type="checkbox" defaultChecked /> Checkbox
          </label>
          <input type="search" placeholder="Search…" />
        </div>
      </Block>

      <Block title="Status and labels">
        <div className="row wrap" style={{ gap: 10 }}>
          <StatusBadge status="running" />
          <StatusBadge status="done" />
          <StatusBadge status="failed" />
          <StatusBadge status="stopped" />
          {["new_screen", "known_screen", "same_screen", "left_app", "crash"].map((e) => (
            <span key={e} className={`effect ${e}`}>
              {e.replace("_", " ")}
            </span>
          ))}
          <span className="chip">pattern chip</span>
          <span className="token tk-S">S:structure</span>
          <span className="token tk-T">T:text</span>
          <span className="token tk-D">D:description</span>
        </div>
      </Block>

      <Block title="Surfaces">
        <div className="stats">
          <Stat value={42} label="stat tile" />
          <Stat value="88%" label="percent" />
          <Stat value={<span style={{ color: "var(--st-blocked)" }}>3</span>} label="warning value" />
        </div>
        <table className="tbl" style={{ marginTop: 16 }}>
          <thead>
            <tr>
              <th>Table header</th>
              <th>Kind</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            <tr className="hover">
              <td>Hover row</td>
              <td className="muted">button</td>
              <td>
                <span className="row" style={{ gap: 6 }}>
                  <i className="dot" style={{ background: statusColor("done") }} /> done
                </span>
              </td>
            </tr>
            <tr className="sel">
              <td>Selected row</td>
              <td className="muted">nav</td>
              <td>
                <span className="row" style={{ gap: 6 }}>
                  <i className="dot" style={{ background: statusColor("pending") }} /> pending
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </Block>

      <Block title="Charts and scores" note="insights/charts.tsx: thin marks, direct labels, tone only with a legend word">
        <div className="chart-grid">
          <div className="col" style={{ gap: 12 }}>
            <span className="small muted">Bars (ranked rows, optional budget line)</span>
            <Bars
              unit="ms"
              budget={1000}
              budgetLabel="1000 ms budget"
              data={[
                { label: "Reports", value: 2770, tone: "bad" },
                { label: "Gallery", value: 1825, tone: "warn" },
                { label: "Settings", value: 320, tone: "good" },
              ]}
            />
          </div>
          <div className="col" style={{ gap: 12 }}>
            <span className="small muted">Columns (ordered categories; highlight one)</span>
            <Columns data={[{ label: "Oct 1", value: 18 }, { label: "Oct 8", value: 21 }, { label: "Oct 13", value: 19 }]} highlight={2} />
          </div>
          <div className="col" style={{ gap: 12 }}>
            <span className="small muted">Split (parts of a whole) · meter · sample tag</span>
            <Split data={[{ label: "error", value: 3, tone: "bad" }, { label: "warning", value: 6, tone: "warn" }, { label: "info", value: 4, tone: "info" }]} />
            <Meter score={72} tone="warn" label="example score" />
            <span>
              <SampleTag />
            </span>
          </div>
        </div>
      </Block>

      <Block title="Icons" note="components/Icon.tsx: 24-grid strokes, currentColor, aria-hidden unless labelled">
        <div className="ds-icons">
          {ICONS.map((n) => (
            <div key={n} className="ds-icon">
              <Icon name={n} size={20} />
              <span className="mono small faint">{n}</span>
            </div>
          ))}
        </div>
      </Block>

      <Block title="Motion" note="--ease-out for UI; keyframes only for one-shot entries">
        <div className="row wrap" style={{ gap: 16, alignItems: "flex-start" }}>
          <button className="btn" onClick={() => setReplay((r) => r + 1)}>
            <Icon name="replay" size={14} /> Replay entry
          </button>
          <div key={replay} className="panel panel-pad stage-swap" style={{ width: 220 }}>
            <b>.stage-swap</b>
            <div className="small muted">fade + 6px rise + 2px blur, 260ms</div>
          </div>
          <div key={`s${replay}`} className="col" style={{ gap: 6 }}>
            {[0, 1, 2, 3].map((i) => (
              <span key={i} className="chip stagger" style={{ "--i": i } as React.CSSProperties}>
                .stagger item {i + 1} (45ms apart)
              </span>
            ))}
          </div>
          <a className="panel use-card" href="#/design" style={{ width: 220 }} onClick={(e) => e.preventDefault()}>
            <span className="use-icon">
              <Icon name="pointer" size={18} />
            </span>
            <b>.use-card</b>
            <span className="small muted">Hover lift only on fine pointers; press scales.</span>
          </a>
        </div>
      </Block>
    </div>
  );
}
