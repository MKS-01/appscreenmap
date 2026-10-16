import { useEffect, useState } from "react";
import { clock, elapsed, SOURCE_LABEL, SOURCES, useSessionLines, useSessions, type Session, type SessionQuery } from "../activity";
import { LogLines, RunStatus } from "../components/Activity";
import { ErrorBox, Loading } from "../components/common";
import { Icon } from "../components/Icon";
import { href } from "../router";
import { fmtDuration, plural } from "../util";

const STATUS_FILTERS: [SessionQuery["status"], string][] = [
  ["", "All"],
  ["running", "Running"],
  ["failed", "Failed"],
];

/** Day + time for a row: "Today 12:04:31", "16 Oct 09:12:03". */
function when(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const today = new Date().toDateString() === d.toDateString();
  return `${today ? "Today" : d.toLocaleDateString(undefined, { day: "numeric", month: "short" })} ${clock(iso)}`;
}

export default function Logs({ query }: { query: URLSearchParams }) {
  const [q, setQ] = useState("");
  const [source, setSource] = useState("");
  const [status, setStatus] = useState<SessionQuery["status"]>("");
  const [problems, setProblems] = useState(false);
  const [run, setRun] = useState(query.get("run") ?? "");
  const [open, setOpen] = useState<string | null>(query.get("open"));
  useEffect(() => setRun(query.get("run") ?? ""), [query.get("run")]);
  useEffect(() => setOpen(query.get("open")), [query.get("open")]);

  const filter: SessionQuery = { q: q.trim(), source, status, run, level: problems ? "warn" : "" };
  const filtered = !!(filter.q || source || status || run || problems);
  const { sessions, total, error } = useSessions(filter);

  return (
    <div className="page logs-page">
      <div className="page-head">
        <span className="kicker">Logs{sessions ? ` · ${filtered ? `${total} matching` : plural(total, "command run")}` : ""}</span>
        <h1>What every command did</h1>
        <p className="lede">
          Crawls, scans and audits, whoever started them: you in a terminal, an AI agent, the MCP server or CI. Secrets are masked. The same
          stream is in the terminal: <code>appscreenmap logs</code>.
        </p>
      </div>

      <div className="logs-filters">
        <input type="search" placeholder="Search the output" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search the output" />
        <div className="seg" aria-label="Who started it">
          <button aria-pressed={source === ""} onClick={() => setSource("")}>
            Everyone
          </button>
          {SOURCES.map((s) => (
            <button key={s} aria-pressed={source === s} onClick={() => setSource(source === s ? "" : s)}>
              {SOURCE_LABEL[s]}
            </button>
          ))}
        </div>
        <div className="seg" aria-label="Result">
          {STATUS_FILTERS.map(([v, label]) => (
            <button key={label} aria-pressed={status === v} onClick={() => setStatus(v)}>
              {label}
            </button>
          ))}
        </div>
        <button className={`chip ${problems ? "on" : ""}`} aria-pressed={problems} onClick={() => setProblems(!problems)}>
          Warnings and errors
        </button>
        {run && (
          <button className="chip on" onClick={() => setRun("")} aria-label={`Show every run, not only ${run}`}>
            run {run} <Icon name="x" size={12} />
          </button>
        )}
      </div>

      {error && <ErrorBox error={error} />}
      {!error && !sessions && <Loading />}
      {sessions && sessions.length === 0 && (
        <div className="empty">{filtered ? "Nothing matches. Clear a filter or search for something else." : "No commands have run yet. Crawls, scans and audits show up here."}</div>
      )}
      {sessions && sessions.length > 0 && (
        <div className="log-sessions">
          {sessions.map((s) => (
            <SessionRow key={s.id} s={s} open={open === s.id} onToggle={() => setOpen(open === s.id ? null : s.id)} filter={filter} />
          ))}
          {total > sessions.length && <div className="faint small log-more">Showing the newest {sessions.length} of {total}. Search to narrow it down.</div>}
        </div>
      )}
    </div>
  );
}

function SessionRow({ s, open, onToggle, filter }: { s: Session; open: boolean; onToggle: () => void; filter: SessionQuery }) {
  const searching = !!(filter.q || filter.level);
  return (
    <div className={`log-session ${open ? "open" : ""}`}>
      <button className="log-session-row" onClick={onToggle} aria-expanded={open}>
        <Icon name="chevron" size={14} className="log-caret" />
        <span className="log-when mono">{when(s.start)}</span>
        <span className="log-what">
          <b>{s.cmd}</b>
          <span className="log-cmdline mono">{s.command.replace(/^appscreenmap\s+/, "") || s.last}</span>
          {searching && s.snippet && <span className="log-snippet mono">{s.snippet}</span>}
        </span>
        <span className="log-who">{SOURCE_LABEL[s.source] ?? s.source}</span>
        <span className="log-dur mono">{fmtDuration(elapsed(s.start, s.status === "running" ? null : s.end ?? s.last_t))}</span>
        <span className="log-counts mono">
          {s.errors > 0 && <span className="bad">{plural(s.errors, "error")}</span>}
          {s.warnings > 0 && <span className="warn">{plural(s.warnings, "warning")}</span>}
          {!s.errors && !s.warnings && <span className="faint">{plural(s.lines, "line")}</span>}
        </span>
        <RunStatus s={s} />
      </button>
      {open && <SessionLines s={s} filter={filter} />}
    </div>
  );
}

function SessionLines({ s, filter }: { s: Session; filter: SessionQuery }) {
  const { events } = useSessionLines(s.id, s.status === "running", filter);
  const searching = !!(filter.q || filter.level); // then it opens at the first match and doesn't follow the tail
  return (
    <div className="log-session-body">
      <div className="log-session-meta small">
        {s.run && (
          <a className="mono" href={href("r", s.run)}>
            Open run {s.run}
          </a>
        )}
        <span className="faint mono">pid {s.pid}</span>
        {s.end && <span className="faint mono">ended {clock(s.end)}</span>}
      </div>
      {events.length === 0 && s.lines > 0 ? <Loading /> : <LogLines events={events} follow={s.status === "running" && !searching} />}
    </div>
  );
}
