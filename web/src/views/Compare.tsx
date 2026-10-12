import { useMemo, useState } from "react";
import { runFile, runKey, useIndex, useMap, usePolled } from "../api";
import { CopyButton, ErrorBox, Loading, ScreenLink } from "../components/common";
import { href } from "../router";
import type { AppMapData, DiffItem, DiffReport, Screen } from "../types";
import { fmtDate, screenMap } from "../util";

export default function Compare({ run, map, base }: { run: string; map: AppMapData; base?: string }) {
  const { data: index } = useIndex();
  const row = index?.runs.find((r) => runKey(r) === run);
  const diffs = row?.diffs ?? [];
  const chosen = base ?? diffs[0];

  if (!index) return <Loading />;
  if (!chosen) {
    const siblings = index.runs.filter((r) => runKey(r) !== run && r.app.package === map.run.app.package);
    return (
      <div className="page narrow">
        <h1>Compare builds</h1>
        <p className="muted">
          Crawl two builds of the same app, then diff them. Screens are matched across runs by signature and token similarity, and
          their screenshots compared pixel by pixel (status bar masked).
        </p>
        {siblings.length === 0 ? (
          <div className="panel panel-pad">
            <p style={{ marginTop: 0 }}>There's no other run of <code>{map.run.app.package}</code> to compare with yet. Crawl another build, then run:</p>
            <Cmd text={`appscreenmap diff runs/<baseline-run> runs/${run}`} />
          </div>
        ) : (
          <div className="panel">
            <table className="tbl">
              <thead>
                <tr>
                  <th>Baseline run</th>
                  <th>Version</th>
                  <th>Command</th>
                </tr>
              </thead>
              <tbody>
                {siblings.map((s) => (
                  <tr key={runKey(s)}>
                    <td>
                      <div>{s.id}</div>
                      <div className="small faint">{fmtDate(s.started_at)}</div>
                    </td>
                    <td>{s.app.version ?? "—"}</td>
                    <td>
                      <Cmd text={`appscreenmap diff runs/${runKey(s)} runs/${run}`} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    );
  }
  // diff/<base> is named by the baseline's run id; its files live at the baseline's path.
  const basePath = (id: string) => {
    const r = index.runs.find((x) => x.id === id);
    return r ? runKey(r) : id;
  };
  return <DiffView run={run} map={map} base={chosen} basePath={basePath(chosen)} others={diffs} />;
}

function Cmd({ text }: { text: string }) {
  return (
    <div className="row">
      <code className="grow ellipsis" style={{ padding: "6px 10px", background: "var(--panel-2)", borderRadius: 6 }}>
        {text}
      </code>
      <CopyButton text={text} />
    </div>
  );
}

const STATUS_COLOR: Record<DiffItem["status"], string> = {
  changed: "var(--st-pending)",
  new: "var(--st-done)",
  missing: "var(--st-blocked)",
  same: "var(--faint)",
};

function DiffView({
  run,
  map,
  base,
  basePath,
  others,
}: {
  run: string;
  map: AppMapData;
  base: string;
  basePath: string;
  others: string[];
}) {
  const { data: report, error } = usePolled<DiffReport>(runFile(run, `diff/${base}/diff.json`), (t) => JSON.parse(t));
  const { data: baseMap } = useMap(basePath);
  const [show, setShow] = useState<Set<DiffItem["status"]>>(new Set(["changed", "new", "missing"]));
  const cand = useMemo(() => screenMap(map), [map]);
  const baseScreens = useMemo(() => (baseMap ? screenMap(baseMap) : new Map<string, Screen>()), [baseMap]);

  if (error) return <div className="page"><ErrorBox error={error} /></div>;
  if (!report) return <Loading />;

  const items = report.items.filter((i) => show.has(i.status));
  return (
    <div className="page">
      <div className="row wrap" style={{ marginBottom: 16, gap: 12 }}>
        <div className="grow">
          <h1>
            {report.base_app.version ?? "baseline"} → {report.cand_app.version ?? "this run"}
          </h1>
          <div className="muted small">
            Baseline <a href={href("r", basePath, "map")}>{base}</a> vs. this run
          </div>
        </div>
        {others.length > 1 && (
          <select value={base} onChange={(e) => (location.hash = href("r", run, "compare", e.target.value))}>
            {others.map((o) => (
              <option key={o}>{o}</option>
            ))}
          </select>
        )}
      </div>
      <div className="row wrap" style={{ gap: 8, marginBottom: 16 }}>
        {(Object.keys(STATUS_COLOR) as DiffItem["status"][]).map((s) => (
          <button
            key={s}
            className={`chip ${show.has(s) ? "on" : ""}`}
            onClick={() => {
              const n = new Set(show);
              n.has(s) ? n.delete(s) : n.add(s);
              setShow(n);
            }}
          >
            <i className="dot" style={{ background: STATUS_COLOR[s] }} /> {report.summary[s] ?? 0} {s}
          </button>
        ))}
      </div>
      <div className="panel">
        {items.length === 0 && <div className="empty">Nothing to show with these filters.</div>}
        {items.map((it, k) => {
          const b = it.base ? baseScreens.get(it.base) : undefined;
          const c = it.cand ? cand.get(it.cand) : undefined;
          return (
            <div key={k} className="cmp-row" style={{ borderTop: k ? "1px solid var(--border)" : undefined }}>
              <div className="col" style={{ gap: 6 }}>
                <span className="row" style={{ gap: 6 }}>
                  <i className="dot" style={{ background: STATUS_COLOR[it.status] }} />
                  <b>{it.status}</b>
                </span>
                <b>{it.title}</b>
                {it.changed_ratio != null && <span className="small muted">{(it.changed_ratio * 100).toFixed(2)}% of pixels differ</span>}
                {it.similarity != null && <span className="small faint">match similarity {it.similarity}</span>}
                {c && <ScreenLink run={run} screen={c}>open in this run →</ScreenLink>}
              </div>
              <Img label="baseline" src={b?.screenshot ? runFile(basePath, b.screenshot) : undefined} />
              <Img label="this run" src={c?.screenshot ? runFile(run, c.screenshot) : undefined} />
              <Img label="diff" src={it.diff ? runFile(run, it.diff) : undefined} />
            </div>
          );
        })}
      </div>
    </div>
  );
}

function Img({ src, label }: { src?: string; label: string }) {
  return (
    <div className="col" style={{ gap: 4 }}>
      <span className="small faint">{label}</span>
      {src ? <img src={src} alt={label} loading="lazy" /> : <div className="ph">—</div>}
    </div>
  );
}
