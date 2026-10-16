import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { clock, elapsed, SOURCE_LABEL, useSessionLines, type Live, type LogEvent, type Session } from "../activity";
import { href } from "../router";
import { fmtDuration, plural } from "../util";
import { StatusBadge } from "./common";
import { Icon } from "./Icon";

/** "crawl · AI agent" */
export const who = (s: Pick<Session, "cmd" | "source">) => `${s.cmd} · ${SOURCE_LABEL[s.source] ?? s.source}`;

/** Status word for a command run; the exit code when it failed. */
export function RunStatus({ s }: { s: Session }) {
  return <StatusBadge status={s.status === "failed" && s.exit != null ? `failed ${s.exit}` : s.status} />;
}

/** Lines of one command run, in mono, time in the gutter. Sticks to the bottom while `follow`, unless scrolled up. */
export function LogLines({ events, follow, empty }: { events: LogEvent[]; follow?: boolean; empty?: string }) {
  const box = useRef<HTMLDivElement>(null);
  const pinned = useRef(true);
  const toMatch = useRef(true); // a search result opens at its first match, once
  useLayoutEffect(() => {
    const el = box.current;
    if (!el) return;
    const hit = toMatch.current ? el.querySelector<HTMLElement>(".log-line.match") : null;
    if (hit) {
      el.scrollTop = hit.offsetTop - el.offsetTop - 32;
      toMatch.current = false;
    } else if (follow && pinned.current) el.scrollTop = el.scrollHeight;
  }, [events, follow]);
  const onScroll = () => {
    const el = box.current;
    if (el) pinned.current = el.scrollHeight - el.scrollTop - el.clientHeight < 24;
  };
  return (
    <div className="log-lines" ref={box} onScroll={onScroll} role="log" aria-live={follow ? "polite" : "off"}>
      {events.length === 0 && <div className="log-empty">{empty ?? "No output yet."}</div>}
      {events.map((e, i) => (
        <div key={i} className={`log-line ${e.level} ${e.kind ?? ""} ${e.match ? "match" : ""}`}>
          <span className="log-t">{clock(e.t)}</span>
          {e.level !== "info" && <span className="log-lvl">{e.level === "error" ? "ERROR" : "WARN"}</span>}
          <span className="log-msg">{e.msg}</span>
        </div>
      ))}
    </div>
  );
}

/** Top-bar chip: only there while a command runs (or just finished). Opens the drawer. */
export function LiveChip({ live, open, onToggle }: { live: Live | null; open: boolean; onToggle: () => void }) {
  const running = live?.running ?? [];
  const recent = live?.recent ?? [];
  if (!running.length && !recent.length) return null;
  const first = running[0] ?? recent[0]!;
  const label = running.length > 1 ? plural(running.length, "command") : who(first);
  return (
    <button className={`live-chip ${open ? "on" : ""}`} onClick={onToggle} aria-pressed={open} aria-controls="activity-dock" title={open ? "Hide the log" : "Show the log"}>
      <RunStatus s={running.length ? { ...first, status: "running" } : first} />
      <span className="live-chip-what">{label}</span>
    </button>
  );
}

/** Bottom drawer with the live log of whatever is running. Opens from the chip, never by itself. */
export function ActivityDock({ live, onClose }: { live: Live | null; onClose: () => void }) {
  const shown = [...(live?.running ?? []), ...(live?.recent ?? []).filter((r) => !(live?.running ?? []).some((s) => s.id === r.id))];
  const [pick, setPick] = useState<string | null>(null);
  const [kept, setKept] = useState<Session | null>(null); // the last one shown, once it drops out of the live list
  const current = shown.find((s) => s.id === pick) ?? shown[0] ?? kept;
  useEffect(() => {
    if (current && current !== kept) setKept(current);
  }, [current?.id, current?.status]);
  const { events, session } = useSessionLines(current?.id ?? null, true);
  const s = session ?? current;
  const [, tick] = useState(0);
  useEffect(() => {
    if (s?.status !== "running") return;
    const t = setInterval(() => tick((n) => n + 1), 1000); // the elapsed time
    return () => clearInterval(t);
  }, [s?.status]);

  return (
    <section className="dock" id="activity-dock" aria-label="Live log">
      <header className="dock-head">
        {shown.length > 1 && (
          <div className="seg" role="tablist" aria-label="Running commands">
            {shown.map((x) => (
              <button key={x.id} role="tab" aria-selected={x.id === current?.id} aria-pressed={x.id === current?.id} onClick={() => setPick(x.id)}>
                {who(x)}
              </button>
            ))}
          </div>
        )}
        {s ? (
          <div className="dock-meta">
            <RunStatus s={s} />
            <b>{who(s)}</b>
            {s.run && (
              <a className="mono small" href={href("r", s.run)}>
                {s.run}
              </a>
            )}
            <span className="faint mono small">{fmtDuration(elapsed(s.start, s.end))}</span>
          </div>
        ) : (
          <span className="faint">Nothing is running.</span>
        )}
        <div className="spacer" />
        <a className="btn" href={`#/logs${s?.id ? `?open=${encodeURIComponent(s.id)}` : ""}`}>
          All logs
        </a>
        <button className="btn icon-only" onClick={onClose} aria-label="Hide the log">
          <Icon name="x" size={15} />
        </button>
      </header>
      {s?.command && <div className="dock-cmd mono">{s.command}</div>}
      <LogLines events={events.filter((e) => e.kind !== "start")} follow empty={s ? "No output yet." : "Commands show up here while they run."} />
    </section>
  );
}
