import { useEffect, useMemo, useRef, useState } from "react";
import { parseTrace, runFile, usePolled } from "../api";
import { ErrorBox, Loading, ScreenLink } from "../components/common";
import { screenHref, useRoute } from "../router";
import type { AppMapData, RunEvent, Screen, TraceRow } from "../types";
import { fmtDuration, screenMap } from "../util";

const EFFECT_TEXT: Record<string, (to: Screen | undefined) => string> = {
  new_screen: (to) => `Never seen before → registered as a new screen${to ? ` (${to.id})` : ""}.`,
  known_screen: (to) => `Matched a screen already in the map${to ? ` (${to.id})` : ""} by its signature / token similarity, so only the transition is recorded.`,
  same_screen: () => "Nothing navigated — the tap changed the screen in place (or did nothing). Any new elements are merged into this screen.",
  left_app: () => "The app handed off to another app. Recorded as an external screen, then the crawler pressed back / relaunched.",
  crash: () => "The app crashed. The crash dialog and logcat were saved, then the app was relaunched.",
};

const EVENT_TEXT: Record<string, (e: RunEvent) => string> = {
  restart: (e) => `Force-stopped and relaunched the app — ${e.detail}.`,
  nav_failed: (e) => `Couldn't get back to ${e.detail} by replaying its path; it will be retried or its remaining actions marked unreachable.`,
  permission: (e) => `A system permission dialog appeared — tapped “${e.detail}”.`,
  crash: (e) => `Crash detected: ${e.detail}`,
};

export default function Replay({ run, map }: { run: string; map: AppMapData }) {
  const running = map.run.status === "running";
  const { data: trace, error } = usePolled<TraceRow[]>(runFile(run, "trace.jsonl"), parseTrace, running ? 2000 : 0, () => running);
  const route = useRoute();
  const byId = useMemo(() => screenMap(map), [map]);
  const [i, setI] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [follow, setFollow] = useState(running);
  const listRef = useRef<HTMLDivElement>(null);
  const playerRef = useRef<HTMLDivElement>(null);
  const [playerH, setPlayerH] = useState<number | null>(null);
  const [q, setQ] = useState("");
  const jumped = useRef(false);

  const rows = trace ?? [];
  const eventsByStep = useMemo(() => {
    const m = new Map<number, RunEvent[]>();
    for (const e of map.events) m.set(e.step, [...(m.get(e.step) ?? []), e]);
    return m;
  }, [map.events]);

  // Screens discovered so far, after each row.
  const discovered = useMemo(() => {
    let n = map.screens.some((s) => s.kind === "app" && s.depth === 0) ? 1 : 0;
    return rows.map((r) => (n += r.effect === "new_screen" && byId.get(r.to ?? "")?.kind === "app" ? 1 : 0));
  }, [rows, byId, map.screens]);

  // Deep link: ?screen=s004 → the step that discovered it.
  useEffect(() => {
    const sid = route.query.get("screen");
    if (jumped.current || !rows.length || !sid) return;
    jumped.current = true;
    const at = rows.findIndex((r) => r.to === sid);
    if (at >= 0) setI(at);
  }, [rows, route.query]);

  useEffect(() => {
    if (follow && rows.length) setI(rows.length - 1);
  }, [follow, rows.length]);

  useEffect(() => {
    if (!playing) return;
    if (i >= rows.length - 1) {
      setPlaying(false);
      return;
    }
    const t = setTimeout(() => setI((x) => Math.min(x + 1, rows.length - 1)), 1300);
    return () => clearTimeout(t);
  }, [playing, i, rows.length]);

  useEffect(() => {
    const on = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement).tagName === "INPUT") return;
      if (e.key === "ArrowRight") setI((x) => Math.min(x + 1, rows.length - 1));
      if (e.key === "ArrowLeft") setI((x) => Math.max(x - 1, 0));
      if (e.key === " ") {
        e.preventDefault();
        setPlaying((p) => !p);
      }
    };
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, [rows.length]);

  useEffect(() => {
    listRef.current?.querySelector(".steprow.sel")?.scrollIntoView({ block: "nearest" });
  }, [i]);

  // The step list is as tall as the player beside it, so the two columns end together.
  useEffect(() => {
    const el = playerRef.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setPlayerH(e.borderBoxSize?.[0]?.blockSize ?? el.offsetHeight));
    ro.observe(el);
    return () => ro.disconnect();
  }, [trace]);

  // Search: step number, screen id or title, the tapped label, where it led, and the outcome word.
  const shown = useMemo(() => {
    const words = q.trim().toLowerCase().split(/\s+/).filter(Boolean);
    const all = rows.map((r, k) => ({ r, k }));
    if (!words.length) return all;
    return all.filter(({ r }) => {
      const hay = [
        r.step,
        r.screen,
        byId.get(r.screen)?.title,
        r.label,
        r.to,
        r.to && byId.get(r.to)?.title,
        effectWord(r),
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return words.every((w) => hay.includes(w));
    });
  }, [q, rows, byId]);

  if (error) return <div className="page"><ErrorBox error={error} /></div>;
  if (!trace) return <Loading />;
  if (!rows.length) return <div className="page empty">No steps recorded yet.</div>;

  const row = rows[Math.min(i, rows.length - 1)];
  const from = byId.get(row.screen);
  const to = row.to ? byId.get(row.to) : undefined;
  const el = from?.elements.find((e) => e.key === row.key);
  const evs = eventsByStep.get(row.step) ?? [];
  const notFound = row.result === "not_found";

  return (
    <div className="page" style={{ maxWidth: 1400 }}>
      <div className="row wrap" style={{ marginBottom: 16, gap: 12 }}>
        <div className="grow" style={{ minWidth: "min(100%, 320px)" }}>
          <span className="kicker">Crawl replay · {rows.length} steps</span>
          <h1>Watch the crawler map the app</h1>
          <p className="lede">
            Step through the crawl to see how this map was built: what the crawler tapped, what it concluded, and when it backtracked.
          </p>
        </div>
      </div>

      <div className="replay">
        <div className="col" style={{ gap: 14 }}>
          <div className="panel" ref={playerRef}>
            <div className="row wrap" style={{ padding: "12px 16px", borderBottom: "1px solid var(--border)", gap: 10 }}>
              <button className="btn" onClick={() => setI(Math.max(0, i - 1))} disabled={i === 0} aria-label="Previous step">
                ←
              </button>
              <button className="btn primary" onClick={() => { setFollow(false); setPlaying(!playing); }} style={{ minWidth: 76 }}>
                {playing ? "❚❚ Pause" : "▶ Play"}
              </button>
              <button className="btn" onClick={() => setI(Math.min(rows.length - 1, i + 1))} disabled={i >= rows.length - 1} aria-label="Next step">
                →
              </button>
              <input
                className="scrub grow"
                type="range"
                min={0}
                max={rows.length - 1}
                value={i}
                onChange={(e) => { setFollow(false); setI(+e.target.value); }}
              />
              <span className="mono small muted">
                step {row.step} · {fmtDuration(row.t)}
              </span>
              {running && (
                <label className="check">
                  <input type="checkbox" checked={follow} onChange={(e) => setFollow(e.target.checked)} /> Follow live
                </label>
              )}
            </div>

            <div className="stage">
              <Phone run={run} screen={from} caption="before" tap={!notFound && row.action !== "back" && row.action !== "scroll" ? el?.bounds : undefined}
                swipe={row.action === "scroll"} />
              <div className="act">
                <span className={`chip ${row.explore === false ? "" : "on"}`}>{row.explore === false ? "navigating" : row.action === "scroll" ? "scrolling" : "exploring"}</span>
                <div>
                  {row.action === "back" ? "Press" : row.action === "scroll" ? "Scroll through" : row.action === "long_click" ? "Long-press" : notFound ? "Look for" : "Tap"}{" "}
                  <b>{row.label}</b>
                </div>
                <div className="arrow">{notFound ? "✕" : "→"}</div>
                {row.effect && <span className={`effect ${row.effect}`}>{row.action === "scroll" ? `+${row.revealed ?? 0} elements` : row.effect.replace("_", " ")}</span>}
                {notFound && <span className="effect not_found">element not found</span>}
              </div>
              <Phone run={run} screen={notFound ? undefined : to} caption={notFound ? "—" : "after"} />
            </div>

            <div style={{ padding: "0 20px 18px" }} className="col">
              <Explain row={row} from={from} to={to} run={run} />
              {evs.map((e, k) => (
                <div key={k} className="small" style={{ color: e.type === "crash" ? "var(--st-blocked)" : "var(--st-pending)" }}>
                  ⚑ {(EVENT_TEXT[e.type] ?? ((x: RunEvent) => `${x.type}: ${x.detail}`))(e)}
                </div>
              ))}
            </div>
          </div>

          <div className="panel panel-pad">
            <div className="row" style={{ marginBottom: 8 }}>
              <h3 className="grow">Screens discovered over time</h3>
              <span className="small muted">
                {discovered[i]} of {map.stats.screens} by step {row.step}
              </span>
            </div>
            <Discovery values={discovered} at={i} onPick={(k) => { setFollow(false); setI(k); }} />
            <div className="small faint" style={{ marginTop: 6 }}>
              The curve flattens as the crawler runs out of new screens and spends its steps navigating back to screens with untried actions.
            </div>
          </div>
        </div>

        <div className="panel steps-panel" style={playerH ? ({ "--player-h": `${playerH}px` } as React.CSSProperties) : undefined}>
          <div className="steps-head">
            <div className="row">
              <h3 className="grow">All steps</h3>
              <span className="small muted">{q ? `${shown.length} of ${rows.length}` : rows.length}</span>
            </div>
            <input
              type="search"
              placeholder="Find a step: 42, s005, Sign in, crash…"
              aria-label="Find a step"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              onKeyDown={(e) => e.key === "Escape" && setQ("")}
            />
          </div>
          <div className="steps" ref={listRef}>
            {shown.length === 0 && <div className="steps-empty small muted">No step matches “{q}”.</div>}
            {shown.map(({ r, k }) => (
              <div key={k}>
                {!q &&
                  (k === 0 || rows[k - 1].step !== r.step) &&
                  (eventsByStep.get(r.step) ?? []).map((e, j) => (
                    <div key={j} className="event-row">
                      ⚑ {e.type} — {e.detail}
                    </div>
                  ))}
                <button type="button" className={`steprow ${k === i ? "sel" : ""}`} aria-current={k === i ? "step" : undefined} onClick={() => { setFollow(false); setI(k); }}>
                  <span className="n">{r.step}</span>
                  <span className="ellipsis">
                    <span className="sid">{r.screen}</span> {r.label}
                    {r.to && r.to !== r.screen && <span className="faint"> → {byId.get(r.to)?.kind === "app" ? r.to : "ext"}</span>}
                  </span>
                  <span className={`effect ${r.effect ?? "not_found"}`}>{effectWord(r)}</span>
                </button>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

/** The short outcome word shown on a step row (and matched by search). */
const effectWord = (r: TraceRow) =>
  !r.effect ? "miss" : r.effect === "new_screen" ? "new" : r.effect.replace("_screen", "").replace("_", " ");

function Explain({ row, from, to, run }: { row: TraceRow; from?: Screen; to?: Screen; run: string }) {
  if (row.result === "not_found")
    return (
      <div className="small">
        The crawler looked for <b>{row.label}</b> on <ScreenLink run={run} screen={from} /> and couldn't find it any more (it
        moved, scrolled away, or was dynamic content). The element is marked <i>failed</i> and the crawler moves on to the next one.
      </div>
    );
  if (row.action === "scroll")
    return (
      <div className="small">
        <b>Scrolling:</b> swiped through <b>{row.label}</b> to look below the fold, then scrolled back.{" "}
        {row.revealed
          ? `Found ${row.revealed} new element(s), merged into this screen and queued for exploration.`
          : "Nothing new turned up."}
      </div>
    );
  return (
    <div className="small">
      {row.explore === false ? (
        <>
          <b>Navigating:</b> this screen has nothing left to try, so the crawler is walking the known graph toward the nearest screen
          that still has pending actions.{" "}
        </>
      ) : (
        <>
          <b>Exploring:</b> picked the highest-priority untried action on <ScreenLink run={run} screen={from} /> (nav → tab → button →
          scroll → list item → toggle → back).{" "}
        </>
      )}
      {row.effect && EFFECT_TEXT[row.effect]?.(to)}
      {to && to.kind === "app" && to.id !== from?.id && (
        <>
          {" "}
          <a href={screenHref(run, to.id)}>Open {to.title} →</a>
        </>
      )}
    </div>
  );
}

function Phone({
  run,
  screen,
  caption,
  tap,
  swipe,
}: {
  run: string;
  screen?: Screen;
  caption: string;
  tap?: [number, number, number, number];
  swipe?: boolean;
}) {
  const W = screen?.width || 1080;
  const H = screen?.height || 2400;
  return (
    <div className="phone">
      <div className="frame" style={{ aspectRatio: `${W} / ${H}` }}>
        {screen?.thumb && <img src={runFile(run, screen.screenshot ?? screen.thumb)} alt="" />}
        {swipe && <span className="swipe">↕</span>}
        {tap && tap[2] > tap[0] && (
          <span className="tap" style={{ left: `${(100 * (tap[0] + tap[2])) / 2 / W}%`, top: `${(100 * (tap[1] + tap[3])) / 2 / H}%` }} />
        )}
      </div>
      <span className="small muted ellipsis" style={{ maxWidth: "100%" }}>
        {caption}: {screen ? <ScreenLink run={run} screen={screen} /> : "—"}
      </span>
    </div>
  );
}

function Discovery({ values, at, onPick }: { values: number[]; at: number; onPick: (i: number) => void }) {
  const W = 600;
  const H = 90;
  const max = Math.max(1, ...values);
  const n = Math.max(1, values.length - 1);
  const x = (k: number) => (k / n) * W;
  const y = (v: number) => H - 4 - (v / max) * (H - 12);
  const d = values.map((v, k) => `${k ? "L" : "M"}${x(k).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      preserveAspectRatio="none"
      style={{ width: "100%", height: H, cursor: "pointer", display: "block" }}
      onClick={(e) => {
        const r = (e.currentTarget as SVGSVGElement).getBoundingClientRect();
        onPick(Math.round(((e.clientX - r.left) / r.width) * n));
      }}
      role="img"
      aria-label="Screens discovered per step"
    >
      <path d={`${d} L${W},${H} L0,${H} Z`} fill="var(--accent-soft)" />
      <path d={d} fill="none" stroke="var(--accent)" strokeWidth={2} vectorEffect="non-scaling-stroke" />
      <line x1={x(at)} x2={x(at)} y1={0} y2={H} stroke="var(--text)" strokeWidth={1} strokeDasharray="3 3" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}
