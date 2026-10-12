import { useMemo, useState } from "react";
import { runFile } from "../api";
import { screenHref } from "../router";
import type { AppMapData } from "../types";
import { useNotes } from "../notes";
import { keys, useStored } from "../storage";
import { shortActivity } from "../util";

export default function Screens({ run, map }: { run: string; map: AppMapData }) {
  const [q, setQ] = useState("");
  const [pattern, setPattern] = useState<string | null>(null);
  const [prefs, setPrefs] = useStored(keys.screensPrefs, { showExt: false, starredOnly: false });
  const { showExt, starredOnly } = prefs;
  const { notes } = useNotes(run);
  const starCount = Object.values(notes).filter((n) => n.star).length;
  const patterns = useMemo(() => [...new Set(map.screens.flatMap((s) => s.patterns))].sort(), [map]);

  const needle = q.trim().toLowerCase();
  const list = map.screens.filter((s) => {
    if (!showExt && s.kind !== "app") return false;
    if (pattern && !s.patterns.includes(pattern)) return false;
    if (starredOnly && !notes[s.id]?.star) return false;
    if (!needle) return true;
    // Search the title, id, activity, and every element label/id/text on the screen.
    const hay = [s.id, s.title, s.activity ?? "", notes[s.id]?.note ?? "", ...s.elements.flatMap((e) => [e.label, e.rid, e.text, e.desc])]
      .join("\n")
      .toLowerCase();
    return hay.includes(needle);
  });

  return (
    <div className="page">
      <div className="row wrap" style={{ marginBottom: 18, gap: 10 }}>
        <input type="search" placeholder="Search title, id, element text, resource-id…" value={q} onChange={(e) => setQ(e.target.value)} style={{ width: 320, maxWidth: "100%" }} />
        <button
          className={`chip ${starredOnly ? "on" : ""}`}
          onClick={() => setPrefs((p) => ({ ...p, starredOnly: !p.starredOnly }))}
          aria-pressed={starredOnly}
        >
          ★ Starred ({starCount})
        </button>
        {patterns.map((p) => (
          <button key={p} className={`chip ${pattern === p ? "on" : ""}`} onClick={() => setPattern(pattern === p ? null : p)}>
            {p}
          </button>
        ))}
        <div className="grow" />
        <label className="check">
          <input type="checkbox" checked={showExt} onChange={(e) => setPrefs((p) => ({ ...p, showExt: e.target.checked }))} /> External apps
        </label>
        <span className="muted small">{list.length} shown</span>
      </div>
      {list.length === 0 ? (
        <div className="panel empty">No screens match.</div>
      ) : (
        <div className="gallery">
          {list.map((s) => {
            // Count the same set on both sides (system Back excluded), so this can't exceed 100%.
            const actionable = s.elements.filter((e) => e.kind !== "back");
            const done = actionable.filter((e) => e.status === "done").length;
            return (
              <a key={s.id} className="panel shot-card" href={screenHref(run, s.id)}>
                <div className="img" style={{ aspectRatio: `${s.width || 1080} / ${s.height || 2400}` }}>{s.thumb && <img src={runFile(run, s.thumb)} alt="" loading="lazy" />}</div>
                <div className="meta">
                  <div className="row">
                    <span className="sid">{s.kind === "app" ? s.id : "external"}</span>
                    <div className="grow" />
                    {s.kind === "app" && <span className="faint small">depth {s.depth}</span>}
                  </div>
                  <b className="ellipsis" title={s.title}>
                    {notes[s.id]?.star && <span className="star-mark">★ </span>}
                    {s.title}
                  </b>
                  {notes[s.id]?.note && <span className="note-snip">{notes[s.id].note}</span>}
                  <span className="small muted ellipsis">{shortActivity(s.activity)}</span>
                  {s.kind === "app" && (
                    <span className="small faint">
                      {done}/{actionable.length} actions tried
                    </span>
                  )}
                  <div className="row wrap" style={{ gap: 4 }}>
                    {s.patterns.map((p) => (
                      <span key={p} className="chip">
                        {p}
                      </span>
                    ))}
                  </div>
                </div>
              </a>
            );
          })}
        </div>
      )}
    </div>
  );
}
