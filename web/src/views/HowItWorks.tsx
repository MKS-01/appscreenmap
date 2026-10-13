import { useEffect, useMemo, useState } from "react";
import { runFile, runKey, useIndex, usePolled } from "../api";
import { CopyButton } from "../components/common";
import { Icon, type IconName } from "../components/Icon";
import { href } from "../router";
import type { AppMapData, Screen, UIElement } from "../types";
import { shortActivity } from "../util";

// ── helpers mirroring the crawler (src/appscreenmap/analyzer.py) ───────────────

/** Same as analyzer.normalize_text: lower-case, digits → #, collapse spaces, 40 chars. */
const normalizeText = (s: string) => s.trim().toLowerCase().replace(/\d/g, "#").replace(/\s+/g, " ").slice(0, 40);

const jaccard = (a: Set<string>, b: Set<string>) => {
  let inter = 0;
  for (const t of a) if (b.has(t)) inter++;
  const union = a.size + b.size - inter;
  return union ? inter / union : 1;
};

const PRIORITY: [string, string][] = [
  ["nav", "Bottom nav"],
  ["tab", "Tab"],
  ["button", "Button"],
  ["scroll", "Scroll"],
  ["list_item", "List item"],
  ["toggle", "Toggle"],
  ["long_click", "Long-press"],
  ["up", "Navigate up"],
  ["back", "System back"],
];

function usePrefersReducedMotion() {
  const q = "(prefers-reduced-motion: reduce)";
  const [reduce, setReduce] = useState(() => typeof matchMedia !== "undefined" && matchMedia(q).matches);
  useEffect(() => {
    const m = matchMedia(q);
    const on = () => setReduce(m.matches);
    m.addEventListener("change", on);
    return () => m.removeEventListener("change", on);
  }, []);
  return reduce;
}

/** The latest run's platform; runs from before the iOS work have no `platform` and are Android. */
const isIosRun = (map: AppMapData | null) => map?.run.device?.platform === "ios";

// ── page ─────────────────────────────────────────────────────────────────────

export default function HowItWorks() {
  const { data: index } = useIndex();
  const latest = index?.runs[0];
  const run = latest ? runKey(latest) : null;
  const { data: map } = usePolled<AppMapData>(run ? runFile(run, "map.json") : null, (t) => JSON.parse(t));

  // The screen with the most to show: most elements, with a screenshot.
  const demo = useMemo(() => {
    const app = (map?.screens ?? []).filter((s) => s.kind === "app" && s.screenshot);
    return [...app].sort((a, b) => b.elements.length - a.elements.length)[0];
  }, [map]);
  const ios = isIosRun(map);
  const root = useMemo(() => (map?.screens ?? []).find((s) => s.kind === "app" && s.depth === 0), [map]);

  return (
    <div className="page how">
      <header className="how-head">
        <span className="how-badge">
          <Icon name="map" size={14} /> How it works
        </span>
        <h1 className="how-title">{ios ? "From an app build to a map of every screen" : "From an APK to a map of every screen"}</h1>
        <p className="how-lede">
          An AI agent runs the crawl for you. You ask in plain language; the agent drives AppScreenMap's crawler, which explores the
          app the way a very patient tester would: look at the screen, tap the most promising thing, note where it led, repeat. No
          app-specific code, no scripts to write.
          {map && (
            <>
              {" "}
              The examples below use your latest run, <b>{map.run.app.label ?? map.run.app.package}</b>.
            </>
          )}
        </p>
      </header>

      <WhoDoesWhat />
      <CrawlLoop run={run} map={map} demo={demo} root={root} ios={ios} />
      <ScreenIdentity map={map} demo={demo} ios={ios} />
      <SavedFiles />
      <AfterMapping run={run} />
      <Tuning />

      <section className="how-section">
        <SectionTitle icon="alert" kicker="Good to know" title="Limits" />
        <ul className="limits">
          <li>
            {ios
              ? "About 3 s per step over simctl and idb; a 300-step crawl takes ~15 minutes. iOS Simulator support is beta."
              : "About 3 s per step over plain ADB; a 300-step crawl takes ~15 minutes."}
          </li>
          <li>Canvas, game and custom-drawn UIs expose no hierarchy, so they're captured but not explored.</li>
          <li>WebView content is only as visible as its accessibility tree.</li>
          <li>
            Screen identity is a heuristic, so expect occasional over-splitting or merging. Tune <code>similarity</code>.
          </li>
        </ul>
      </section>
    </div>
  );
}

function SectionTitle({ icon, kicker, title, children }: { icon: IconName; kicker: string; title: string; children?: React.ReactNode }) {
  return (
    <div className="sec-title">
      <span className="sec-icon">
        <Icon name={icon} size={18} />
      </span>
      <div>
        <span className="sec-kicker">{kicker}</span>
        <h2>{title}</h2>
        {children && <p className="muted">{children}</p>}
      </div>
    </div>
  );
}

// ── 0. who does what ─────────────────────────────────────────────────────────

const ROLES: { icon: IconName; who: string; does: string[] }[] = [
  {
    icon: "user",
    who: "You",
    does: ["Ask for what you need, in plain language", "Browse the map and screens here", "Confirm or dismiss findings"],
  },
  {
    icon: "bot",
    who: "Your AI agent",
    does: [
      "Checks the device and runs the crawl",
      "Reviews the map: duplicates, dead ends, missed screens",
      "Tunes the config and re-crawls; turns crawler bugs into tests",
      "Runs accessibility audits and writes up findings",
    ],
  },
  {
    icon: "cpu",
    who: "The crawler",
    does: [
      "Explores the app deterministically, with no model calls",
      "Same build and settings → same map, so runs are comparable",
      "Writes plain files the agent and this viewer read",
    ],
  },
];

const PROMPTS: [string, string][] = [
  ["crawl-app", "Map my app from a clean install and review the map"],
  ["tune-crawler", "Two different screens got merged in the last run. Fix it"],
  ["a11y-audit", "Audit accessibility on the latest run at WCAG 2.2 AA"],
  ["crawl-app", "Crawl the new build and compare it with the last run"],
  ["extend-crawler", "Add an Appium page-object export"],
];

function WhoDoesWhat() {
  return (
    <section className="how-section">
      <SectionTitle icon="bot" kicker="Agent-driven" title="Who does what">
        The agent does the work a QA engineer would do around a crawler: run it, judge the result, adjust, run again. The crawler
        underneath stays predictable.
      </SectionTitle>
      <div className="roles">
        {ROLES.map((r, i) => (
          <div key={r.who} className="panel role stagger" style={{ "--i": i } as React.CSSProperties}>
            <span className="use-icon">
              <Icon name={r.icon} size={18} />
            </span>
            <b>{r.who}</b>
            <ul>
              {r.does.map((d) => (
                <li key={d}>{d}</li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      <div className="cmd-list">
        {PROMPTS.map(([skill, prompt]) => (
          <div key={prompt} className="cmd-row">
            <Icon name="message" size={15} />
            <span className="prompt-text grow">{prompt}</span>
            <span className="chip mono" title="Project skill the agent uses (.claude/skills)">
              {skill}
            </span>
            <CopyButton text={prompt} />
          </div>
        ))}
      </div>
      <p className="small muted" style={{ marginTop: 10 }}>
        The project ships these as skills in <code>.claude/skills/</code>, so Claude Code knows how to crawl, tune, audit and extend
        AppScreenMap without extra instructions. Everything also works by hand from the terminal.
      </p>
    </section>
  );
}

// ── 1. the crawl loop (interactive stepper) ──────────────────────────────────

const STEPS: { icon: IconName; title: string; short: string }[] = [
  { icon: "rocket", title: "Launch", short: "Install, grant permissions, start fresh" },
  { icon: "eye", title: "Observe", short: "Dump the hierarchy, take a screenshot" },
  { icon: "scan", title: "Identify", short: "New screen, or one we've seen?" },
  { icon: "pointer", title: "Act", short: "Tap the most promising untried element" },
  { icon: "database", title: "Record", short: "Save the transition, then loop" },
];
const STEP_MS = 5200;

function CrawlLoop({ run, map, demo, root, ios }: { run: string | null; map: AppMapData | null; demo?: Screen; root?: Screen; ios: boolean }) {
  const reduce = usePrefersReducedMotion();
  const [active, setActive] = useState(0);
  const [playing, setPlaying] = useState(!reduce);
  const [hovering, setHovering] = useState(false);
  useEffect(() => {
    if (reduce) setPlaying(false);
  }, [reduce]);

  const next = () => setActive((a) => (a + 1) % STEPS.length);
  const paused = !playing || hovering;

  return (
    <section className="how-section">
      <SectionTitle icon="replay" kicker="Mapping" title="The crawl loop">
        Steps 2–5 repeat until nothing is left to try or the step / time budget runs out. Pick a step, or let it play.
      </SectionTitle>

      <div className="loop" onPointerEnter={() => setHovering(true)} onPointerLeave={() => setHovering(false)}>
        <div className="loop-steps" role="tablist" aria-label="Crawl loop steps">
          {STEPS.map((s, i) => (
            <button
              key={s.title}
              role="tab"
              id={`loop-tab-${i}`}
              aria-selected={active === i}
              aria-controls="loop-stage"
              className={`loop-step ${active === i ? "on" : ""}`}
              onClick={() => {
                setActive(i);
                setPlaying(false);
              }}
            >
              <span className="loop-step-icon">
                <Icon name={s.icon} size={18} />
              </span>
              <span className="loop-step-text">
                <span className="loop-step-n">Step {i + 1}</span>
                <b>{s.title}</b>
                <span className="small muted">{s.short}</span>
              </span>
              {active === i && playing && (
                <span
                  key={`p${active}`}
                  className="loop-progress"
                  style={{ animationDuration: `${STEP_MS}ms`, animationPlayState: paused ? "paused" : "running" }}
                  onAnimationEnd={next}
                  aria-hidden
                />
              )}
            </button>
          ))}
          <button className="btn loop-play" onClick={() => setPlaying((p) => !p)} aria-pressed={playing}>
            <Icon name={playing ? "pause" : "play"} size={14} /> {playing ? "Pause" : "Play"} walkthrough
          </button>
        </div>

        <div className="loop-stage" id="loop-stage" role="tabpanel" aria-labelledby={`loop-tab-${active}`}>
          <div key={active} className="stage-swap">
            {active === 0 && <LaunchStage run={run} map={map} root={root} ios={ios} />}
            {active === 1 && <ObserveStage run={run} screen={demo} ios={ios} />}
            {active === 2 && <IdentifyStage run={run} screen={demo} ios={ios} />}
            {active === 3 && <ActStage run={run} screen={demo} map={map} />}
            {active === 4 && <RecordStage run={run} screen={demo} map={map} />}
          </div>
        </div>
      </div>
    </section>
  );
}

function Phone({
  run,
  screen,
  children,
  small,
}: {
  run: string | null;
  screen?: Screen;
  children?: React.ReactNode;
  small?: boolean;
}) {
  return (
    <div className={`mini-phone ${small ? "small" : ""}`}>
      <div className="mini-screen" style={{ aspectRatio: `${screen?.width || 1080} / ${screen?.height || 2400}` }}>
        {run && screen?.screenshot ? <img src={runFile(run, screen.screenshot)} alt={screen.title} /> : <div className="mini-placeholder" />}
        {children}
      </div>
    </div>
  );
}

const pct = (screen: Screen | undefined, b: [number, number, number, number]) => {
  const W = screen?.width || 1080;
  const H = screen?.height || 2400;
  return {
    left: `${(100 * b[0]) / W}%`,
    top: `${(100 * b[1]) / H}%`,
    width: `${(100 * (b[2] - b[0])) / W}%`,
    height: `${(100 * (b[3] - b[1])) / H}%`,
  };
};

function StageText({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="stage-text">
      <h3>{title}</h3>
      {children}
    </div>
  );
}

function LaunchStage({ run, map, root, ios }: { run: string | null; map: AppMapData | null; root?: Screen; ios: boolean }) {
  const app = map?.run.app;
  const lines = [
    `Installing ${app?.package ?? (ios ? "App.app" : "app.apk")}`,
    "Granting runtime permissions",
    ios ? "Setting Dynamic Type and appearance for repeatable screenshots" : "Disabling animations for stable screenshots",
    ios ? `Launching ${app?.package ?? "the app"}` : `Launching ${shortActivity(app?.launch_activity) || "the launcher activity"}`,
  ];
  return (
    <div className="stage-grid">
      <StageText title="The agent starts a crawl">
        <div className="term">
          <div className="term-prompt">
            <Icon name="bot" size={13} /> “Map {app?.label ?? "my app"} from a clean install”
          </div>
          <div className="term-cmd">
            <Icon name="terminal" size={13} /> appscreenmap crawl {ios ? "--platform ios --app" : "--apk"}{" "}
            {app ? `${app.label ?? "app"}.${ios ? "app" : "apk"}` : ios ? "App.app" : "app.apk"}
          </div>
          {lines.map((l, i) => (
            <div key={l} className="term-line stagger" style={{ "--i": i } as React.CSSProperties}>
              <Icon name="check" size={13} className="ok" /> {l}
            </div>
          ))}
        </div>
        <p className="small muted">
          Every replay also starts here: force-stop and relaunch, so a path from launch always means the same thing.
        </p>
      </StageText>
      <Phone run={run} screen={root} />
    </div>
  );
}

function ObserveStage({ run, screen, ios }: { run: string | null; screen?: Screen; ios: boolean }) {
  const els = (screen?.elements ?? []).filter((e) => e.scroll_depth === 0 && e.bounds[2] > e.bounds[0]);
  return (
    <div className="stage-grid">
      <StageText title="Read the screen">
        <p>
          {ios ? (
            <>
              <code>idb ui describe-all</code> gives the accessibility tree: every element's type, identifier, label, value, frame and
              traits, converted to the same hierarchy the Android crawl reads. A screenshot is taken alongside.
            </>
          ) : (
            <>
              <code>uiautomator dump</code> gives the full view hierarchy: every node's class, resource-id, text, content
              description, bounds and flags. A screenshot is taken alongside.
            </>
          )}
        </p>
        <p>
          Anything visible, enabled and clickable / scrollable / checkable becomes an <b>element</b>.
          {screen && (
            <>
              {" "}
              On <b>{screen.title}</b> that's <b>{els.length}</b> elements.
            </>
          )}
        </p>
        <p className="small muted">Full-screen click-away backgrounds (≥ 90% of the screen) are ignored.</p>
      </StageText>
      <Phone run={run} screen={screen}>
        {els.slice(0, 40).map((e, i) => (
          <span key={e.id} className="mini-box stagger" style={{ ...pct(screen, e.bounds), "--i": Math.min(i, 12) } as React.CSSProperties} />
        ))}
      </Phone>
    </div>
  );
}

function IdentifyStage({ run, screen, ios }: { run: string | null; screen?: Screen; ios: boolean }) {
  const tokens = screen?.tokens ?? ["S:FrameLayout|", "S:TextView|title", "T:alarm", "T:#:## am", "D:navigate up"];
  const pick = [
    ...tokens.filter((t) => t.startsWith("S:")).slice(0, 5),
    ...tokens.filter((t) => t.startsWith("T:")).slice(0, 5),
    ...tokens.filter((t) => t.startsWith("D:")).slice(0, 4),
  ];
  return (
    <div className="stage-grid">
      <StageText title="Fingerprint it">
        <p>The hierarchy becomes a set of tokens: structure (class | id), text and descriptions, with digits normalised.</p>
        <div className="token-cloud">
          {pick.map((t, i) => (
            <span key={t} className={`token tk-${t[0]} stagger`} style={{ "--i": i } as React.CSSProperties}>
              {t}
            </span>
          ))}
          {tokens.length > pick.length && <span className="token more">+{tokens.length - pick.length}</span>}
        </div>
        <div className="sig">
          <Icon name="hash" size={14} /> {ios ? "sha1(tokens)" : "sha1(activity + tokens)"} = <code>{screen?.signature ?? "3f9a0c1e…"}</code>
        </div>
        <p className="small muted">Exact match → same screen. Otherwise ≥ 80% token overlap{ios ? "" : " (same activity)"} → same screen. Else: new.</p>
      </StageText>
      <Phone run={run} screen={screen} small />
    </div>
  );
}

function ActStage({ run, screen, map }: { run: string | null; screen?: Screen; map: AppMapData | null }) {
  const counts = new Map<string, number>();
  for (const e of screen?.elements ?? []) counts.set(e.kind, (counts.get(e.kind) ?? 0) + 1);
  const first: UIElement | undefined = (screen?.elements ?? []).find((e) => e.kind !== "back" && e.bounds[2] > e.bounds[0] && e.status === "done");
  const target = first?.target ? map?.screens.find((s) => s.id === first.target) : undefined;
  const topKind = first?.kind;
  const blocked = (screen?.elements ?? []).filter((e) => e.status === "blocked").length;
  return (
    <div className="stage-grid">
      <StageText title="Pick what to tap">
        <ol className="ladder">
          {PRIORITY.map(([k, label]) => (
            <li key={k} className={`${k === topKind ? "on" : ""} ${counts.get(k) ? "" : "none"}`}>
              <span>{label}</span>
              <span className="mono">{counts.get(k) ?? 0}</span>
            </li>
          ))}
        </ol>
        {first && (
          <p className="small">
            Here it taps <b>{first.label}</b>
            {target && (
              <>
                {" "}
                → <b>{target.title}</b>
              </>
            )}
            .
          </p>
        )}
        <p className="small muted">
          <Icon name="shield" size={12} /> Labels like log out, delete, pay, buy, call are never tapped
          {blocked ? ` (${blocked} blocked here)` : ""}. Lists: only the first 2 rows.
        </p>
      </StageText>
      <Phone run={run} screen={screen}>
        {first && (
          <span
            className="mini-tap"
            style={{
              left: `${(100 * (first.bounds[0] + first.bounds[2])) / 2 / (screen?.width || 1080)}%`,
              top: `${(100 * (first.bounds[1] + first.bounds[3])) / 2 / (screen?.height || 2400)}%`,
            }}
          />
        )}
      </Phone>
    </div>
  );
}

function RecordStage({ run, screen, map }: { run: string | null; screen?: Screen; map: AppMapData | null }) {
  const out = (map?.transitions ?? []).filter((t) => t.from === screen?.id && t.to !== t.from).slice(0, 5);
  const byId = new Map((map?.screens ?? []).map((s) => [s.id, s]));
  return (
    <div className="stage-grid">
      <StageText title="Remember where it led">
        <p>Each tap becomes a transition. A new screen is saved with its screenshot and the taps that reached it.</p>
        <div className="edges">
          {out.length ? (
            out.map((t, i) => {
              const to = byId.get(t.to);
              return (
                <div key={t.id} className="edge-row stagger" style={{ "--i": i } as React.CSSProperties}>
                  <span className="sid">{t.from}</span>
                  <span className="edge-label">{t.label}</span>
                  <Icon name="arrow" size={13} />
                  {run && to?.thumb ? <img src={runFile(run, to.thumb)} alt="" /> : <span className="edge-dot" />}
                  <span className="ellipsis">{to?.title ?? t.to}</span>
                </div>
              );
            })
          ) : (
            <div className="small muted">Transitions appear here as the crawl discovers them.</div>
          )}
        </div>
        {map && run && (
          <a className="btn" href={href("r", run, "replay")}>
            <Icon name="replay" size={14} /> Watch this run step by step
          </a>
        )}
      </StageText>
      <div className="record-stats">
        <div>
          <b>{map?.stats.screens ?? "—"}</b>
          <span>screens</span>
        </div>
        <div>
          <b>{map?.stats.transitions ?? "—"}</b>
          <span>transitions</span>
        </div>
        <div>
          <b>{map?.run.steps ?? "—"}</b>
          <span>steps</span>
        </div>
      </div>
    </div>
  );
}

// ── 2. screen identity (playground) ──────────────────────────────────────────

function ScreenIdentity({ map, demo, ios }: { map: AppMapData | null; demo?: Screen; ios: boolean }) {
  const [a, setA] = useState("Alarm at 7:30 AM · 2 new");
  const [b, setB] = useState("Alarm at 9:45 AM · 5 new");
  const na = normalizeText(a);
  const nb = normalizeText(b);
  const same = na === nb;

  const [threshold, setThreshold] = useState(0.8);
  const others = useMemo(() => {
    if (!map || !demo) return [];
    const base = new Set(demo.tokens);
    return map.screens
      .filter((s) => s.kind === "app" && s.id !== demo.id)
      .map((s) => ({ s, sim: jaccard(base, new Set(s.tokens)), sameAct: s.activity === demo.activity }))
      .sort((x, y) => y.sim - x.sim)
      .slice(0, 6);
  }, [map, demo]);

  return (
    <section className="how-section">
      <SectionTitle icon="scan" kicker="Identity" title="Telling screens apart">
        Screen identity has to survive clocks, counters and feeds, while still separating screens that share {ios ? "one navigation container" : "one activity"}.
      </SectionTitle>

      <div className="grid2">
        <div className="panel panel-pad col" style={{ gap: 12 }}>
          <h3>Try it: text normalisation</h3>
          <label className="field">
            <span className="small muted">Text on screen, visit 1</span>
            <input type="text" value={a} onChange={(e) => setA(e.target.value)} />
          </label>
          <label className="field">
            <span className="small muted">Same place, visit 2</span>
            <input type="text" value={b} onChange={(e) => setB(e.target.value)} />
          </label>
          <div className="norm">
            <code>T:{na}</code>
            <code>T:{nb}</code>
          </div>
          <div className={`verdict ${same ? "yes" : "no"}`} aria-live="polite">
            <Icon name={same ? "check" : "alert"} size={16} />
            {same ? "Same token: these count as the same screen text." : "Different tokens: the text really differs."}
          </div>
          <p className="small muted" style={{ margin: 0 }}>
            Digit count still shows (<code>9:45</code> vs <code>10:45</code> differ); the similarity match below absorbs that.
            Repeated list rows and editable fields are left out entirely, so a feed with new content is still the same screen.
          </p>
        </div>

        <div className="panel panel-pad col" style={{ gap: 12 }}>
          <h3>Try it: similarity threshold</h3>
          {demo && others.length ? (
            <>
              <label className="field">
                <span className="small muted">
                  Merge screens with ≥ <b className="mono">{threshold.toFixed(2)}</b> token overlap (same activity)
                </span>
                <input
                  type="range"
                  className="scrub"
                  min={0.5}
                  max={1}
                  step={0.01}
                  value={threshold}
                  onChange={(e) => setThreshold(+e.target.value)}
                />
              </label>
              <div className="small muted">
                Compared with <b>{demo.title}</b> ({demo.id}):
              </div>
              <div className="sim-list">
                {others.map(({ s, sim, sameAct }) => {
                  const merge = sameAct && sim >= threshold;
                  return (
                    <div key={s.id} className={`sim-row ${merge ? "merge" : ""}`}>
                      <span className="ellipsis">
                        <span className="sid">{s.id}</span> {s.title}
                      </span>
                      <span className="sim-bar" aria-hidden>
                        <span style={{ transform: `scaleX(${sim})` }} />
                        <i style={{ left: `${threshold * 100}%` }} />
                      </span>
                      <span className="mono small">{sim.toFixed(2)}</span>
                      <span className="sim-tag">{merge ? "merged" : sameAct ? "separate" : "other activity"}</span>
                    </div>
                  );
                })}
              </div>
              <p className="small muted" style={{ margin: 0 }}>
                Lower it if one real screen is split into several; raise it if different screens get merged. Default 0.80.
              </p>
            </>
          ) : (
            <p className="muted">Run a crawl to try this against your own screens.</p>
          )}
        </div>
      </div>
    </section>
  );
}

// ── 3. saved files (explorer) ─────────────────────────────────────────────────

const FILES: { name: string; icon: IconName; what: string; usedBy: string; sample: string }[] = [
  {
    name: "map.json",
    icon: "file",
    what: "The whole graph: screens, their elements and outcomes, transitions, events. Updated live while a crawl runs.",
    usedBy: "Map, Screens, Insights, every export",
    sample: `{ "screens": [{ "id": "s003", "title": "Timer",
    "patterns": ["bottom_nav"], "depth": 1,
    "reach_path": [{ "screen": "s001", "label": "Timer" }],
    "elements": [{ "kind": "nav", "status": "done", "target": "s001" }] }],
  "transitions": [{ "from": "s001", "to": "s003", "label": "Timer" }] }`,
  },
  {
    name: "trace.jsonl",
    icon: "replay",
    what: "One line per step: what was tapped, where it led, and whether it was exploring or navigating.",
    usedBy: "Crawl replay",
    sample: `{"step": 4, "screen": "s001", "label": "Timer", "to": "s003", "effect": "new_screen", "explore": true}`,
  },
  {
    name: "screens/",
    icon: "image",
    what: "Per screen: full screenshot, thumbnail, and the raw hierarchy XML it was identified from.",
    usedBy: "Screen detail, Accessibility, Compare",
    sample: `s003.png   full-size screenshot
s003.jpg   thumbnail
s003.xml   view hierarchy (uiautomator on Android, idb accessibility tree on iOS)`,
  },
  {
    name: "flows/",
    icon: "test",
    what: "One Maestro flow per screen: launch, follow the path (filling forms), assert you arrived.",
    usedBy: "Screen detail → Maestro flow",
    sample: `appId: com.google.android.deskclock
---
- launchApp: { stopApp: true }
- tapOn: { id: "…:id/tab_menu_timer" }
- assertVisible: { id: "…:id/tab_menu_alarm" }`,
  },
  {
    name: "notes.json",
    icon: "check",
    what: "Your stars, screen notes and accessibility review decisions, saved from the viewer.",
    usedBy: "Screens, Accessibility",
    sample: `{ "notes": { "s002": { "star": true, "note": "alarm list" } },
  "a11y": { "s001::field-unlabeled::…": { "status": "confirmed" } } }`,
  },
  {
    name: "map.mmd",
    icon: "map",
    what: "A Mermaid flowchart of the map. Renders on GitHub and in most wikis.",
    usedBy: "Docs, PRs",
    sample: `flowchart LR
  s001["s001 · Clock"]
  s001 -->|"Timer"| s003`,
  },
  {
    name: "diff/<base>/",
    icon: "compare",
    what: "From `appscreenmap diff`: matched screens across two builds with pixel-diff overlays.",
    usedBy: "Compare",
    sample: `diff.json            summary + per-screen status
s002__s002.png       red overlay of changed pixels`,
  },
];

function SavedFiles() {
  const [sel, setSel] = useState(0);
  const f = FILES[sel];
  return (
    <section className="how-section">
      <SectionTitle icon="folder" kicker="Output" title="What gets saved">
        Everything is plain files in <code>runs/&lt;app&gt;/&lt;run&gt;/</code>. The viewer has no backend; it reads them
        directly.
      </SectionTitle>
      <div className="explorer panel">
        <div className="explorer-list" role="tablist" aria-label="Run files">
          {FILES.map((x, i) => (
            <button
              key={x.name}
              role="tab"
              aria-selected={sel === i}
              className={`explorer-item ${sel === i ? "on" : ""}`}
              onClick={() => setSel(i)}
            >
              <Icon name={x.icon} size={15} />
              <span className="mono">{x.name}</span>
            </button>
          ))}
        </div>
        <div className="explorer-body" role="tabpanel">
          <div key={sel} className="stage-swap col" style={{ gap: 10 }}>
            <div className="row" style={{ gap: 8 }}>
              <Icon name={f.icon} size={18} />
              <b className="mono">{f.name}</b>
            </div>
            <p style={{ margin: 0 }}>{f.what}</p>
            <div className="small muted">
              Used by: <b>{f.usedBy}</b>
            </div>
            <pre className="code">{f.sample}</pre>
          </div>
        </div>
      </div>
    </section>
  );
}

// ── 4. after mapping ─────────────────────────────────────────────────────────

const USES: { icon: IconName; title: string; tab: string; text: string }[] = [
  { icon: "map", title: "Map", tab: "map", text: "The screen graph. Click a screen to light up the path from launch." },
  { icon: "grid", title: "Screens", tab: "screens", text: "Gallery of every screen. Search titles, element text and resource-ids." },
  { icon: "replay", title: "Crawl replay", tab: "replay", text: "Each tap with before/after screens and why the crawler made it." },
  { icon: "chart", title: "Insights", tab: "insights", text: "Coverage, dead ends, untried actions, crashes. Whether to raise the budget." },
  { icon: "a11y", title: "Accessibility", tab: "a11y", text: "Scanner-style checks on every screen, with triage and export." },
  { icon: "compare", title: "Compare", tab: "compare", text: "Two builds side by side with pixel diffs, so regressions stand out." },
];

function AfterMapping({ run }: { run: string | null }) {
  const cmds: [IconName, string, string][] = [
    ["test", "Turn screens into tests", "maestro test runs/<app>/<run>/flows/"],
    ["compare", "Diff two builds", "appscreenmap diff runs/<app>/<v1-run> runs/<app>/<v2-run>"],
    ["file", "Regenerate exports", "appscreenmap export runs/<app>/<run>"],
  ];
  return (
    <section className="how-section">
      <SectionTitle icon="route" kicker="After mapping" title="Using the map">
        Each view answers a different question{run ? "; these open your latest run" : ""}.
      </SectionTitle>
      <div className="use-grid">
        {USES.map((u) => {
          const inner = (
            <>
              <span className="use-icon">
                <Icon name={u.icon} size={18} />
              </span>
              <b>{u.title}</b>
              <span className="small muted">{u.text}</span>
              {run && (
                <span className="use-go">
                  Open <Icon name="arrow" size={13} />
                </span>
              )}
            </>
          );
          return run ? (
            <a key={u.tab} className="panel use-card" href={href("r", run, u.tab)}>
              {inner}
            </a>
          ) : (
            <div key={u.tab} className="panel use-card">
              {inner}
            </div>
          );
        })}
      </div>
      <div className="cmd-list">
        {cmds.map(([icon, label, cmd]) => (
          <div key={cmd} className="cmd-row">
            <Icon name={icon} size={15} />
            <span className="cmd-label">{label}</span>
            <code className="grow ellipsis">{cmd}</code>
            <CopyButton text={cmd} />
          </div>
        ))}
      </div>
    </section>
  );
}

// ── 5. tuning ────────────────────────────────────────────────────────────────

const TUNE: { symptom: string; fix: string; cmd: string; prompt: string }[] = [
  { symptom: "Many untried actions", fix: "The crawl ran out of budget. Give it more steps or time.", cmd: "--max-steps 600 --max-minutes 45", prompt: "Crawl again with a bigger step budget" },
  { symptom: "One screen split into several", fix: "Screens are too strict to match. Lower the similarity threshold.", cmd: "[crawl]\nsimilarity = 0.7", prompt: "One screen shows up as several in the map. Fix it" },
  { symptom: "Different screens merged", fix: "Screens match too loosely. Raise the threshold.", cmd: "[crawl]\nsimilarity = 0.9", prompt: "Two different screens got merged. Fix it" },
  { symptom: "Stuck at login", fix: "Give the form filler test credentials by field-name regex.", cmd: '[inputs]\n"e-?mail|username" = "qa@example.com"\n"pass(word)?" = "…"', prompt: "Log in with the test account and map what is behind it" },
  { symptom: "A risky button got tapped", fix: "Add its label to the blocked list.", cmd: '[safety]\nblocked_text = ["\\\\bunsubscribe\\\\b"]  # added to the defaults', prompt: "Never tap Unsubscribe during crawls" },
  { symptom: "Lists need deeper coverage", fix: "Explore more rows per list.", cmd: "[crawl]\nmax_list_items = 5", prompt: "Explore more rows in each list" },
];

function Tuning() {
  const [sel, setSel] = useState(0);
  const t = TUNE[sel];
  return (
    <section className="how-section">
      <SectionTitle icon="sliders" kicker="Iterate" title="Tune the next crawl">
        Pick what you saw in Insights. Tell your agent, or change it yourself.
      </SectionTitle>
      <div className="row wrap" style={{ gap: 8 }} role="tablist" aria-label="Symptoms">
        {TUNE.map((x, i) => (
          <button key={x.symptom} role="tab" aria-selected={sel === i} className={`chip pick ${sel === i ? "on" : ""}`} onClick={() => setSel(i)}>
            {x.symptom}
          </button>
        ))}
      </div>
      <div className="panel panel-pad tune-answer" role="tabpanel">
        <div key={sel} className="stage-swap col" style={{ gap: 10 }}>
          <p style={{ margin: 0 }}>{t.fix}</p>
          <div className="row">
            <span className="hero-prompt grow">
              <Icon name="bot" size={15} />
              <span>{t.prompt}</span>
            </span>
            <CopyButton text={t.prompt} />
          </div>
          <span className="small faint">Or yourself:</span>
          <div className="row" style={{ alignItems: "flex-start" }}>
            <pre className="code grow" style={{ margin: 0 }}>
              {t.cmd}
            </pre>
            <CopyButton text={t.cmd} />
          </div>
          <span className="small faint">
            Flags go on <code>appscreenmap crawl</code>; sections go in <code>appscreenmap.toml</code>, passed with <code>--config</code>.
          </span>
        </div>
      </div>
    </section>
  );
}

