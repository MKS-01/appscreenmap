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
import { downloadText, flowSvg, loadShots, storySvg, type Card } from "../exportSvg";
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
const HDR_H = 14;
const SHOT_AREA = 30000;
const CARD_BORDER = 3; // 1.5px on each side: the screenshot is that much narrower than the card
const nodeSize = (s: Screen | undefined) => {
  const b = shotBox(s, SHOT_AREA);
  const img = Math.round((b.w - CARD_BORDER) * b.ratio); // exact device aspect at the width it is drawn
  return { w: b.w, h: img + HDR_H + CARD_BORDER, img };
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
    <div className={cls} style={{ "--w": `${size.w}px`, "--ar": `${screen.width || 1080} / ${screen.height || 2400}` } as React.CSSProperties}>
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
  // Narrow toolbar: everything but layout and search folds behind an Options button.
  const [optionsOpen, setOptionsOpen] = useState(false);
  const changedOptions =
    (variant !== "story" ? +(direction !== "auto") + +(links !== "paths") + +showLabels : 0) + +!showExternal + +!!patternFilter;
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
  useEffect(() => {
    if (!selected) return;
    const onKey = (e: KeyboardEvent) => {
      const typing = e.target instanceof Element && e.target.closest("input, select, textarea");
      if (e.key === "Escape" && !typing) setSelected(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selected]);
  const extraLinks = map.transitions.filter((t) => t.from !== t.to && tree.parent.get(t.to) !== t.from).length;

  // Export the layout as it is on screen: node positions and links come from React Flow, the storyboard from its lanes.
  const rf = useReactFlow();
  const [exporting, setExporting] = useState(false);
  const exportSvg = async () => {
    setExporting(true);
    try {
      const shots = await loadShots(run, visible);
      const app = map.run.app;
      const name = variant === "story" ? "storyboard" : variant;
      const head = {
        title: `${app.label || app.package} · ${map.run.id}`,
        subtitle: `${visible.length} screens · ${name}${variant !== "story" ? ` · ${dir === "TB" ? "top to bottom" : "left to right"}` : ""}`,
      };
      let svg: string;
      if (variant === "story") {
        const lanes = storyLanes(tree).map((lane) => ({
          title: byId.get(lane.hub)?.title ?? lane.hub,
          label: lane.label,
          cards: lane.items.flatMap(({ id }) => {
            const s = byId.get(id);
            if (!s) return [];
            const box = shotBox(s, 34000);
            const via = tree.via.get(id);
            return [
              {
                id,
                title: s.title,
                kind: s.kind,
                w: box.w + 16,
                h: 0,
                img: box.h,
                data: shots.get(id) ?? null,
                sub: id === lane.hub ? "" : `via ${via?.label || byId.get(tree.parent.get(id) ?? "")?.title || "?"}`,
                star: !!notes[id]?.star,
              },
            ];
          }),
        }));
        svg = storySvg(lanes, head);
      } else {
        const cards: Card[] = rf.getNodes().flatMap((n) => {
          const s = (n.data as { screen?: Screen }).screen;
          if (!s) return [];
          const size = nodeSize(s);
          return [{ id: s.id, title: s.title, kind: s.kind, x: n.position.x, y: n.position.y, w: size.w, h: size.h, img: size.img, data: shots.get(s.id) ?? null, star: !!notes[s.id]?.star }];
        });
        const links = rf.getEdges().map((e) => ({
          from: e.source,
          to: e.target,
          label: typeof e.label === "string" ? e.label : undefined,
          discovery: !e.style?.strokeDasharray,
        }));
        svg = flowSvg(cards, links, dir, variant, head);
      }
      downloadText(`${map.run.id}-${name}.svg`, svg);
    } catch (e) {
      window.alert(e instanceof Error ? e.message : "Could not export the map.");
    } finally {
      setExporting(false);
    }
  };

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
                aria-label={v.label}
              >
                <Icon name={v.icon} size={14} /> <span className="seg-label">{v.label}</span>
              </button>
            ))}
          </div>
          <div id="map-options" className={`map-options ${optionsOpen ? "open" : ""}`}>
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
          <select aria-label="Highlight a UI pattern" value={patternFilter ?? ""} onChange={(e) => setPatternFilter(e.target.value || null)}>
            <option value="">All patterns</option>
            {patterns.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
          </div>
          <input type="search" placeholder="Find screen…" aria-label="Find screen" value={query} onChange={(e) => setQuery(e.target.value)} />
          <button
            className="btn"
            onClick={exportSvg}
            disabled={exporting}
            title="Download this layout as one SVG, with full-size screenshots. Opens in a browser; drag it into Figma. It can show the app's real data, so check it before sharing."
          >
            <Icon name="download" size={14} /> {exporting ? "Exporting…" : "Export SVG"}
          </button>
          <button
            className={`btn map-options-toggle ${optionsOpen ? "on" : ""}`}
            aria-expanded={optionsOpen}
            aria-controls="map-options"
            onClick={() => setOptionsOpen((o) => !o)}
          >
            <Icon name="sliders" size={14} /> Options
            {changedOptions > 0 && (
              <span className="count-badge" aria-label={`${changedOptions} changed`}>
                {changedOptions}
              </span>
            )}
          </button>
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
      <aside className={`map-side ${sel ? "open" : ""}`} aria-label={sel ? `Screen ${sel.title}` : "Map overview"}>
        {sel ? (
          <SidePanel run={run} map={map} screen={sel} byId={byId} note={notes[sel.id]} onClose={() => setSelected(null)} />
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

  // Fit the whole map, but never so far out that cards become unreadable (zoom ≥ 0.55) or blown up past 1:1.
  // When the map is too big for that, centring it would cut off both ends, the launch screen included, so pin it to
  // where the tree starts instead (top for top-down, left for left-to-right) and let the reader pan for the rest.
  const canvas = useRef<HTMLDivElement>(null);
  const fitted = useRef(false);
  useEffect(() => {
    const t = setTimeout(() => {
      const el = canvas.current;
      const ns = rf.getNodes();
      if (!el || !ns.length) return;
      const b = rf.getNodesBounds(ns);
      const pad = 28;
      const [W, H] = [el.clientWidth - 2 * pad, el.clientHeight - 2 * pad];
      const zoom = Math.min(1, Math.max(0.55, Math.min(W / b.width, H / b.height)));
      const [w, h] = [b.width * zoom, b.height * zoom];
      // Along the tree's direction pin the start; across it, keep the launch screen in the middle.
      const root = ns.find((n) => (n.data as { root?: boolean }).root);
      const rx = root ? root.position.x + (root.measured?.width ?? 0) / 2 : b.x + b.width / 2;
      const ry = root ? root.position.y + (root.measured?.height ?? 0) / 2 : b.y + b.height / 2;
      const lr = dir === "LR";
      const x = w <= W ? pad + (W - w) / 2 - b.x * zoom : lr ? pad - b.x * zoom : pad + W / 2 - rx * zoom;
      const y = h <= H ? pad + (H - h) / 2 - b.y * zoom : lr ? pad + H / 2 - ry * zoom : pad - b.y * zoom;
      rf.setViewport({ x, y, zoom }, { duration: fitted.current ? 250 : 0 });
      fitted.current = true;
    }, 50);
    return () => clearTimeout(t);
  }, [layout, rf, dir]);

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
    <div className="map-canvas" ref={canvas}>
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
  onClose,
}: {
  run: string;
  map: AppMapData;
  screen: Screen;
  byId: Map<string, Screen>;
  note?: ScreenNote;
  onClose: () => void;
}) {
  const out = map.transitions.filter((t) => t.from === screen.id);
  const into = map.transitions.filter((t) => t.to === screen.id);
  return (
    <div className="col" style={{ gap: 14 }}>
      <div className="row side-head" style={{ alignItems: "flex-start", gap: 12 }}>
        <button className="btn icon-only side-close" onClick={onClose} aria-label="Close screen details" title="Close (Esc)">
          <Icon name="x" size={16} />
        </button>
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
    <ul className="edge-list">
      {items.map(([label, s, n], i) => (
        <li key={i}>
          <span className="edge-label">{label}</span>
          <span className="edge-to">
            → <ScreenLink run={run} screen={s} />
          </span>
          {n > 1 && <span className="edge-n faint small" title={`Taken ${n} times`}>×{n}</span>}
        </li>
      ))}
    </ul>
  );
}
