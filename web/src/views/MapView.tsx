import dagre from "@dagrejs/dagre";
import {
  Background,
  Controls,
  Handle,
  MarkerType,
  MiniMap,
  Position,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  type Edge,
  type Node,
  type NodeChange,
  type NodeProps,
} from "@xyflow/react";
import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { runFile } from "../api";
import { ScreenLink, Thumb } from "../components/common";
import { Icon, type IconName } from "../components/Icon";
import { discoveryTree, storyLanes, tidyLayout, type DiscoveryTree } from "../mapLayout";
import { useNotes, type RunNotes, type ScreenNote } from "../notes";
import { go, href, screenHref } from "../router";
import { keys, useStored } from "../storage";
import type { AppMapData, Screen } from "../types";
import { pathScreens, screenMap, shortActivity, shotBox } from "../util";

type Dir = "LR" | "TB";
type Variant = "tree" | "graph" | "story";
type Links = "paths" | "all";

// Cards show the whole screenshot at the device's own aspect ratio (shotBox), under a one-line header.
const HDR_H = 22;
const SHOT_AREA = 30000;
const nodeSize = (s: Screen | undefined) => {
  const b = shotBox(s, SHOT_AREA);
  return { w: b.w, h: b.h + HDR_H, img: b.h };
};

const VARIANTS: { id: Variant; label: string; icon: IconName; hint: string }[] = [
  { id: "tree", label: "Tree", icon: "route", hint: "Each screen under the screen it was found from" },
  { id: "graph", label: "Graph", icon: "map", hint: "Free layout of the whole graph" },
  { id: "story", label: "Storyboard", icon: "grid", hint: "Screens grouped by app section, no lines" },
];

interface ScreenNodeData extends Record<string, unknown> {
  screen: Screen;
  run: string;
  dir: Dir;
  root: boolean;
  orphan: boolean; // no recorded way to reach it
  sel?: boolean;
  onpath?: boolean;
  dim?: boolean;
  star?: boolean;
}
type ScreenNode = Node<ScreenNodeData, "screen">;

const ScreenNodeView = memo(function ScreenNodeView({ data }: NodeProps<ScreenNode>) {
  const { screen, run, dir } = data;
  const ext = screen.kind !== "app";
  const size = nodeSize(screen);
  const cls = ["snode", ext && "ext", data.root && "root", data.orphan && "orphan", data.sel && "sel", data.onpath && !data.sel && "onpath", data.dim && "dim"]
    .filter(Boolean)
    .join(" ");
  return (
    <div className={cls} style={{ "--w": `${size.w}px`, "--ih": `${size.img}px` } as React.CSSProperties}>
      <Handle type="target" position={dir === "LR" ? Position.Left : Position.Top} style={{ opacity: 0 }} />
      <div
        className="hdr"
        title={`${screen.id} · ${screen.title}${ext ? " (left the app)" : data.orphan ? " (no recorded path)" : ` · depth ${screen.depth}`}`}
      >
        {data.star && <span className="star-mark">★</span>}
        <span className="t">{screen.title}</span>
        <span className="sid">{ext ? "ext" : screen.id}</span>
      </div>
      {screen.thumb ? <img src={runFile(run, screen.thumb)} alt="" draggable={false} /> : <div className="noshot" />}
      <Handle type="source" position={dir === "LR" ? Position.Right : Position.Bottom} style={{ opacity: 0 }} />
    </div>
  );
});

const nodeTypes = { screen: ScreenNodeView };

interface EdgeGroup {
  from: string;
  to: string;
  labels: string[];
  count: number;
}

export default function MapView(props: { run: string; map: AppMapData; focus?: string; layout?: string }) {
  return (
    <ReactFlowProvider>
      <MapInner {...props} />
    </ReactFlowProvider>
  );
}

function MapInner({ run, map, focus, layout }: { run: string; map: AppMapData; focus?: string; layout?: string }) {
  const [prefs, setPrefs] = useStored(keys.mapPrefs, {
    variant: "tree" as Variant,
    direction: "auto" as Dir | "auto",
    links: "paths" as Links,
    showExternal: true,
    showLabels: false,
  });
  const { variant, direction, links, showExternal, showLabels } = prefs;
  const set = <K extends keyof typeof prefs>(k: K, v: (typeof prefs)[K]) => setPrefs((p) => ({ ...p, [k]: v }));
  // ?layout=tree|graph|story picks a variant from a link (and becomes the remembered choice).
  useEffect(() => {
    if (layout && VARIANTS.some((v) => v.id === layout)) setPrefs((p) => ({ ...p, variant: layout as Variant }));
  }, [layout, setPrefs]);

  const [patternFilter, setPatternFilter] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<string | null>(focus ?? null);
  const { notes } = useNotes(run);

  const byId = useMemo(() => screenMap(map), [map]);
  const patterns = useMemo(() => [...new Set(map.screens.flatMap((s) => s.patterns))].sort(), [map]);
  const visible = useMemo(() => map.screens.filter((s) => showExternal || s.kind === "app"), [map, showExternal]);
  const tree = useMemo(() => discoveryTree(map, visible), [map, visible]);
  // Auto direction: tall (portrait) cards pack best side by side, so lay the tree out top-down;
  // wide (landscape/tablet) cards pack best stacked, so left-to-right.
  const autoDir: Dir = useMemo(() => {
    const ratios = visible.filter((s) => s.kind === "app").map((s) => (s.height || 2400) / (s.width || 1080)).sort((a, b) => a - b);
    return (ratios[Math.floor(ratios.length / 2)] ?? 2) >= 1 ? "TB" : "LR";
  }, [visible]);
  const dir: Dir = direction === "auto" ? autoDir : direction;

  const q = query.trim().toLowerCase();
  const matches = useCallback(
    (s: Screen) =>
      (!patternFilter || s.patterns.includes(patternFilter)) &&
      (!q || s.title.toLowerCase().includes(q) || s.id.toLowerCase().includes(q) || (s.activity ?? "").toLowerCase().includes(q)),
    [patternFilter, q],
  );
  const filtering = !!patternFilter || !!q;

  const sel = selected ? byId.get(selected) : undefined;
  const extraLinks = map.transitions.filter((t) => t.from !== t.to && tree.parent.get(t.to) !== t.from).length;

  return (
    <div className="map-wrap">
      <div className="map-main">
        <div className="map-toolbar">
          <div className="seg variant-seg" role="radiogroup" aria-label="Map layout">
            {VARIANTS.map((v) => (
              <button
                key={v.id}
                role="radio"
                aria-checked={variant === v.id}
                className={variant === v.id ? "on" : ""}
                onClick={() => set("variant", v.id)}
                title={v.hint}
              >
                <Icon name={v.icon} size={14} /> {v.label}
              </button>
            ))}
          </div>
          {variant !== "story" && (
            <>
              <div className="seg" role="radiogroup" aria-label="Direction">
                <button
                  role="radio"
                  aria-checked={direction === "auto"}
                  className={direction === "auto" ? "on" : ""}
                  onClick={() => set("direction", "auto")}
                  title={`Pick from the device's screen shape (now ${autoDir === "TB" ? "top to bottom for portrait screens" : "left to right for landscape screens"})`}
                >
                  Auto
                </button>
                <button role="radio" aria-checked={direction === "LR"} className={direction === "LR" ? "on" : ""} onClick={() => set("direction", "LR")} title="Left to right">
                  →
                </button>
                <button role="radio" aria-checked={direction === "TB"} className={direction === "TB" ? "on" : ""} onClick={() => set("direction", "TB")} title="Top to bottom">
                  ↓
                </button>
              </div>
              <div className="seg" role="radiogroup" aria-label="Links">
                <button
                  role="radio"
                  aria-checked={links === "paths"}
                  className={links === "paths" ? "on" : ""}
                  onClick={() => set("links", "paths")}
                  title="Only the tap that first found each screen. Other links appear for the selected screen."
                >
                  Discovery paths
                </button>
                <button role="radio" aria-checked={links === "all"} className={links === "all" ? "on" : ""} onClick={() => set("links", "all")} title="Every transition the crawl recorded">
                  All links
                </button>
              </div>
              <label className="check">
                <input type="checkbox" checked={showLabels} onChange={(e) => set("showLabels", e.target.checked)} /> Labels
              </label>
            </>
          )}
          <label className="check">
            <input type="checkbox" checked={showExternal} onChange={(e) => set("showExternal", e.target.checked)} /> External apps
          </label>
          <div className="grow" />
          <input type="search" placeholder="Find screen…" aria-label="Find screen" value={query} onChange={(e) => setQuery(e.target.value)} style={{ width: 150, padding: "3px 8px" }} />
          <select aria-label="Highlight a UI pattern" value={patternFilter ?? ""} onChange={(e) => setPatternFilter(e.target.value || null)} style={{ padding: "3px 8px" }}>
            <option value="">All patterns</option>
            {patterns.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </div>

        {variant === "story" ? (
          <Storyboard run={run} byId={byId} tree={tree} notes={notes} selected={selected} setSelected={setSelected} dim={(s) => filtering && !matches(s)} />
        ) : (
          <FlowCanvas
            key={variant}
            run={run}
            map={map}
            byId={byId}
            tree={tree}
            visible={visible}
            variant={variant}
            dir={dir}
            links={links}
            showLabels={showLabels}
            notes={notes}
            selected={selected}
            setSelected={setSelected}
            dim={(s) => filtering && !matches(s)}
          />
        )}
      </div>
      <aside className="map-side">
        {sel ? (
          <SidePanel run={run} map={map} screen={sel} byId={byId} note={notes[sel.id]} />
        ) : (
          <div className="col" style={{ gap: 14 }}>
            <h2>{map.run.app.label ?? map.run.app.package}</h2>
            <div className="muted small">
              {map.stats.screens} screens. {VARIANTS.find((v) => v.id === variant)?.hint}.
              {variant !== "story" && links === "paths" && extraLinks > 0 && ` ${extraLinks} other links are hidden; select a screen to see its own, or switch to All links.`}
            </div>
            <div className="muted small">
              <b>Click</b> a screen to see how the crawler reached it; the path from launch lights up.
              <br />
              <b>Double-click</b> to open the screen with its tappable elements.
            </div>
            {tree.root && (
              <div className="small">
                Launch screen: <ScreenLink run={run} screen={byId.get(tree.root)} />
              </div>
            )}
            {map.run.status === "running" && (
              <div className="badge running">
                <span className="dot" /> live, updating as the crawl runs
              </div>
            )}
          </div>
        )}
      </aside>
    </div>
  );
}

// ── Tree and Graph (React Flow) ──────────────────────────────────────────────

function FlowCanvas({
  run,
  map,
  byId,
  tree,
  visible,
  variant,
  dir,
  links,
  showLabels,
  notes,
  selected,
  setSelected,
  dim,
}: {
  run: string;
  map: AppMapData;
  byId: Map<string, Screen>;
  tree: DiscoveryTree;
  visible: Screen[];
  variant: "tree" | "graph";
  dir: Dir;
  links: Links;
  showLabels: boolean;
  notes: RunNotes;
  selected: string | null;
  setSelected: (id: string | null) => void;
  dim: (s: Screen) => boolean;
}) {
  const rf = useReactFlow();
  // Hand-placed positions, remembered per run, layout and direction.
  const [dragged, setDragged] = useStored<Record<string, { x: number; y: number }>>(keys.positions(run, `${variant}-${dir}`), {});
  const [live, setLive] = useState<Record<string, { x: number; y: number }>>({}); // mid-drag, not yet saved
  const ids = useMemo(() => new Set(visible.map((s) => s.id)), [visible]);

  // Positions depend only on the discovery tree, so toggling links never moves anything.
  const layout = useMemo(() => {
    const sizeOf = (id: string) => nodeSize(byId.get(id));
    if (variant === "tree") return tidyLayout(tree, sizeOf, dir);
    const g = new dagre.graphlib.Graph();
    g.setGraph({ rankdir: dir, nodesep: 28, ranksep: dir === "LR" ? 100 : 70, marginx: 20, marginy: 20 });
    g.setDefaultEdgeLabel(() => ({}));
    for (const s of visible) {
      const { w, h } = sizeOf(s.id);
      g.setNode(s.id, { width: w, height: h });
    }
    for (const [c, p] of tree.parent) g.setEdge(p, c);
    dagre.layout(g);
    const pos = new Map<string, { x: number; y: number }>();
    for (const s of visible) {
      const n = g.node(s.id);
      const { w, h } = sizeOf(s.id);
      pos.set(s.id, { x: n.x - w / 2, y: n.y - h / 2 });
    }
    return pos;
  }, [variant, tree, visible, dir, byId]);

  useEffect(() => {
    // Fit the whole map, but never so far out that cards become unreadable (pan for the rest) or blown up past 1:1.
    const t = setTimeout(() => rf.fitView({ padding: 0.08, duration: 250, minZoom: 0.55, maxZoom: 1 }), 50);
    return () => clearTimeout(t);
  }, [layout, rf]);

  const sel = selected ? byId.get(selected) : undefined;
  const pathPairs = useMemo(() => {
    if (!sel) return new Set<string>();
    const p = pathScreens(sel);
    return new Set(p.slice(0, -1).map((a, i) => `${a}->${p[i + 1]}`));
  }, [sel]);
  const onPath = useMemo(() => new Set(sel ? pathScreens(sel) : []), [sel]);

  const nodes: ScreenNode[] = useMemo(
    () =>
      visible.map((s) => ({
        id: s.id,
        type: "screen",
        position: live[s.id] ?? dragged[s.id] ?? layout.get(s.id) ?? { x: 0, y: 0 },
        data: {
          screen: s,
          run,
          dir,
          root: tree.entry.has(s.id),
          orphan: tree.orphan.has(s.id),
          sel: s.id === selected,
          onpath: onPath.has(s.id),
          dim: dim(s),
          star: !!notes[s.id]?.star,
        },
      })),
    [visible, live, dragged, layout, run, dir, tree.root, selected, onPath, dim, notes],
  );

  const edges: Edge[] = useMemo(() => {
    // Discovery edges: always shown. Extra links: all of them, or only the selected screen's.
    const groups = new Map<string, EdgeGroup & { discovery: boolean }>();
    for (const [c, p] of tree.parent) {
      groups.set(`${p}->${c}`, { from: p, to: c, labels: [tree.via.get(c)?.label ?? ""], count: 0, discovery: true });
    }
    for (const t of map.transitions) {
      if (t.from === t.to || !ids.has(t.from) || !ids.has(t.to)) continue;
      const id = `${t.from}->${t.to}`;
      const g = groups.get(id);
      if (g) {
        if (!g.labels.includes(t.label)) g.labels.push(t.label);
        g.count += t.count;
        continue;
      }
      if (links === "paths" && t.from !== selected && t.to !== selected) continue;
      groups.set(id, { from: t.from, to: t.to, labels: [t.label], count: t.count, discovery: false });
    }

    return [...groups.entries()].map(([id, g]) => {
      const hot = pathPairs.has(id);
      const touchesSel = !!selected && (g.from === selected || g.to === selected);
      const color = hot ? "var(--accent)" : touchesSel ? "var(--muted)" : g.discovery ? "var(--faint)" : "var(--border)";
      const label = g.labels.filter(Boolean).length > 1 ? `${g.labels[0]} +${g.labels.length - 1}` : g.labels[0];
      return {
        id,
        source: g.from,
        target: g.to,
        type: variant === "tree" ? "smoothstep" : "default",
        pathOptions: variant === "tree" ? { borderRadius: 12 } : undefined,
        label: label && (showLabels || hot || touchesSel) ? label : undefined,
        animated: hot,
        zIndex: hot ? 10 : touchesSel ? 5 : 0,
        style: {
          stroke: color,
          strokeWidth: hot ? 2.5 : touchesSel ? 1.6 : g.discovery ? 1.4 : 1,
          strokeDasharray: g.discovery ? undefined : "4 4",
          opacity: selected && !hot && !touchesSel ? 0.3 : 1,
        },
        markerEnd: { type: MarkerType.ArrowClosed, color, width: 14, height: 14 },
        labelBgPadding: [4, 2] as [number, number],
        labelBgBorderRadius: 4,
      } as Edge;
    });
  }, [tree, map.transitions, ids, links, selected, pathPairs, showLabels, variant]);

  // Track positions in memory while dragging; save to storage once, when the drag ends.
  const liveRef = useRef(live);
  liveRef.current = live;
  const onNodesChange = useCallback(
    (changes: NodeChange<ScreenNode>[]) => {
      const next = { ...liveRef.current };
      const done: Record<string, { x: number; y: number }> = {};
      for (const c of changes) {
        if (c.type !== "position") continue;
        const pos = c.position ?? next[c.id];
        if (c.dragging) {
          if (pos) next[c.id] = pos;
        } else {
          if (pos) done[c.id] = pos;
          delete next[c.id];
        }
      }
      setLive(next);
      if (Object.keys(done).length) setDragged((d) => ({ ...d, ...done }));
    },
    [setDragged],
  );

  return (
    <div className="map-canvas">
      {Object.keys(dragged).length > 0 && (
        <button className="btn map-reset" onClick={() => setDragged({})} title="Forget the positions you dragged screens to">
          Reset layout
        </button>
      )}
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onNodeClick={(_, n) => setSelected(n.id === selected ? null : n.id)}
        onNodeDoubleClick={(_, n) => go(screenHref(run, n.id))}
        onPaneClick={() => setSelected(null)}
        minZoom={0.1}
        maxZoom={2}
        proOptions={{ hideAttribution: true }}
        nodesConnectable={false}
        fitView
        fitViewOptions={{ padding: 0.08, minZoom: 0.55, maxZoom: 1 }}
      >
        <Background gap={24} size={1} color="var(--border)" />
        <Controls showInteractive={false} position="bottom-left" />
        <MiniMap
          pannable
          zoomable
          position="bottom-right"
          style={{ width: 140, height: 90 }}
          nodeColor={(n) => (n.id === selected ? "var(--accent)" : "var(--faint)")}
          maskColor="rgba(128,128,128,0.12)"
        />
      </ReactFlow>
    </div>
  );
}

// ── Storyboard ───────────────────────────────────────────────────────────────

function Storyboard({
  run,
  byId,
  tree,
  notes,
  selected,
  setSelected,
  dim,
}: {
  run: string;
  byId: Map<string, Screen>;
  tree: DiscoveryTree;
  notes: RunNotes;
  selected: string | null;
  setSelected: (id: string | null) => void;
  dim: (s: Screen) => boolean;
}) {
  const lanes = useMemo(() => storyLanes(tree), [tree]);
  return (
    <div className="story" onClick={(e) => e.target === e.currentTarget && setSelected(null)}>
      {lanes.map((lane) => {
        const hub = byId.get(lane.hub);
        return (
          <section key={lane.hub} className="lane" aria-label={`Section ${hub?.title ?? lane.hub}`}>
            <header className="lane-head">
              <b>{hub?.title ?? lane.hub}</b>
              <span className="small muted">{lane.label}</span>
              <span className="small faint">{lane.items.length} screens</span>
            </header>
            <div className="lane-row">
              {lane.items.map(({ id, rel }) => {
                const s = byId.get(id);
                if (!s) return null;
                const parent = tree.parent.get(id);
                const via = tree.via.get(id);
                const box = shotBox(s, 34000);
                return (
                  <button
                    key={id}
                    style={{ width: box.w }}
                    className={`story-card ${selected === id ? "sel" : ""} ${dim(s) ? "dim" : ""} ${s.kind !== "app" ? "ext" : ""}`}
                    onClick={() => setSelected(selected === id ? null : id)}
                    onDoubleClick={() => go(screenHref(run, id))}
                    aria-pressed={selected === id}
                    title={`${s.id} · ${s.title}`}
                  >
                    <span className="story-shot" style={{ aspectRatio: `${s.width || 1080} / ${s.height || 2400}` }}>
                      {s.thumb ? <img src={runFile(run, s.thumb)} alt="" loading="lazy" draggable={false} /> : <span className="mini-placeholder" />}
                      {rel > 0 && <span className="story-depth">+{rel}</span>}
                    </span>
                    <span className="story-title ellipsis">
                      {notes[id]?.star && <span className="star-mark">★ </span>}
                      {s.title}
                    </span>
                    <span className="story-via ellipsis">
                      {id === lane.hub ? (
                        <span className="sid">{s.id}</span>
                      ) : (
                        <>
                          <span className="sid">{s.id}</span> via {via?.label || byId.get(parent ?? "")?.title || "?"}
                        </>
                      )}
                    </span>
                  </button>
                );
              })}
            </div>
          </section>
        );
      })}
    </div>
  );
}

function SidePanel({
  run,
  map,
  screen,
  byId,
  note,
}: {
  run: string;
  map: AppMapData;
  screen: Screen;
  byId: Map<string, Screen>;
  note?: ScreenNote;
}) {
  const out = map.transitions.filter((t) => t.from === screen.id);
  const into = map.transitions.filter((t) => t.to === screen.id);
  return (
    <div className="col" style={{ gap: 14 }}>
      <div className="row" style={{ alignItems: "flex-start", gap: 12 }}>
        <Thumb run={run} screen={screen} className="side-thumb" />
        <div className="col grow" style={{ gap: 4 }}>
          <h2>{screen.title}</h2>
          <span className="sid">{screen.id}</span>
          <span className="small muted">{shortActivity(screen.activity)}</span>
          <div className="row wrap" style={{ gap: 4 }}>
            {screen.patterns.map((p) => (
              <span key={p} className="chip">
                {p}
              </span>
            ))}
          </div>
          {screen.kind === "app" && (
            <a className="btn primary" href={screenHref(run, screen.id)} style={{ alignSelf: "flex-start", marginTop: 6 }}>
              Open screen →
            </a>
          )}
        </div>
      </div>

      {note?.note && (
        <div>
          <h3 style={{ marginBottom: 6 }}>{note.star ? "★ " : ""}Your note</h3>
          <div className="small note-text">{note.note}</div>
        </div>
      )}

      <div>
        <h3 style={{ marginBottom: 6 }}>Path from launch</h3>
        {screen.reach_path.length === 0 ? (
          <div className="small muted">
            {screen.kind !== "app"
              ? "Opened from the app (see Reached from)."
              : screen.origin === "launch" || (!screen.origin && screen.id === map.screens.find((x) => x.kind === "app" && x.depth === 0)?.id)
                ? "This is where the app opens."
                : "The crawl recorded no path to this screen (it appeared outside a recorded tap, e.g. after returning from another app), so it has no Maestro flow."}
          </div>
        ) : (
          <ol className="small" style={{ margin: 0, paddingLeft: 18 }}>
            {screen.reach_path.map((st, i) => (
              <li key={i}>
                on <ScreenLink run={run} screen={byId.get(st.screen)} /> {st.action === "back" ? "press" : "tap"} <b>{st.label}</b>
              </li>
            ))}
          </ol>
        )}
      </div>

      <div>
        <h3 style={{ marginBottom: 6 }}>Leads to ({out.length})</h3>
        <EdgeList run={run} items={out.map((t) => [t.label, byId.get(t.to), t.count] as const)} />
      </div>
      <div>
        <h3 style={{ marginBottom: 6 }}>Reached from ({into.length})</h3>
        <EdgeList run={run} items={into.map((t) => [t.label, byId.get(t.from), t.count] as const)} />
      </div>
      <a className="small" href={href("r", run, "replay") + `?screen=${encodeURIComponent(screen.id)}`}>
        See when the crawler found it →
      </a>
    </div>
  );
}

function EdgeList({ run, items }: { run: string; items: (readonly [string, Screen | undefined, number])[] }) {
  if (!items.length) return <div className="small muted">none</div>;
  return (
    <table className="tbl">
      <tbody>
        {items.map(([label, s, n], i) => (
          <tr key={i}>
            <td className="ellipsis" style={{ maxWidth: 120 }} title={label}>
              {label}
            </td>
            <td className="ellipsis" style={{ maxWidth: 140 }}>
              <ScreenLink run={run} screen={s} />
            </td>
            <td className="faint small">{n > 1 ? `×${n}` : ""}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
