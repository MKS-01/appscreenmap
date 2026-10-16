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
  useViewport,
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
import { useNotes, type MapComment, type RunNotes, type ScreenNote, type TreeEdits } from "../notes";
import {
  addPlanned,
  Composer,
  EditToolbar,
  labelIn,
  moveIn,
  newScreenId,
  Pin,
  pinPoint,
  plannedScreens,
  removeIn,
  renameIn,
  Thread,
  toCanvas,
  TOOLS,
  type Draft,
  type Point,
  type Tool,
} from "./MapEdit";
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
  drop?: boolean; // a dragged card would go under this one
}
type ScreenNode = Node<ScreenNodeData, "screen">;

const ScreenNodeView = memo(function ScreenNodeView({ data }: NodeProps<ScreenNode>) {
  const { screen, run, dir } = data;
  const ext = screen.kind !== "app";
  const size = nodeSize(screen);
  const cls = ["snode", ext && "ext", data.root && "root", data.orphan && "orphan", data.sel && "sel", data.onpath && !data.sel && "onpath", data.dim && "dim", screen.planned && "planned", data.drop && "drop"]
    .filter(Boolean)
    .join(" ");
  return (
    <div className={cls} style={{ "--w": `${size.w}px`, "--ar": `${screen.width || 1080} / ${screen.height || 2400}` } as React.CSSProperties}>
      <Handle type="target" position={dir === "LR" ? Position.Left : Position.Top} style={{ opacity: 0 }} />
      <div
        className="hdr"
        title={`${screen.id} · ${screen.title}${screen.planned ? " (planned, not crawled)" : ext ? " (left the app)" : data.orphan ? " (no recorded path)" : ` · depth ${screen.depth}`}`}
      >
        {data.star && <span className="star-mark">★</span>}
        <span className="t">{screen.title}</span>
        <span className="sid">{ext ? "ext" : screen.planned ? "new" : screen.id}</span>
      </div>
      {screen.thumb ? (
        <img src={runFile(run, screen.thumb)} alt="" draggable={false} />
      ) : (
        <div className="noshot">{screen.planned && <span className="planned-label">Planned</span>}</div>
      )}
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

function MapInner({ run, map: rawMap, focus, layout }: { run: string; map: AppMapData; focus?: string; layout?: string }) {
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
  const editor = useNotes(run);
  const { notes, edits, comments } = editor;
  // Edits made in the viewer sit on top of map.json: renamed screens, screens taken out, screens moved, planned
  // screens added, links relabelled.
  const map = useMemo(
    () => ({
      ...rawMap,
      screens: [
        ...rawMap.screens.map((s) => (edits.titles[s.id] ? { ...s, title: edits.titles[s.id] } : s)),
        ...plannedScreens(edits, rawMap.screens.find((s) => s.kind === "app")),
      ],
    }),
    [rawMap, edits],
  );
  const rawById = useMemo(() => screenMap(rawMap), [rawMap]);
  const deleted = useMemo(() => new Set(edits.deleted), [edits.deleted]);
  const parents = useMemo(
    () => ({ ...Object.fromEntries(Object.entries(edits.added).map(([id, a]) => [id, a.parent])), ...edits.parents }),
    [edits.added, edits.parents],
  );
  // The crawled name, for planned screens their own.
  const titleOf = (id: string) => rawById.get(id)?.title ?? edits.added[id]?.title ?? id;
  const [renameInSide, setRenameInSide] = useState<string | null>(null);
  const [activeComment, setActiveComment] = useState<string | null>(null);
  const [panTo, setPanTo] = useState<{ id: string; n: number } | null>(null);

  const byId = useMemo(() => screenMap(map), [map]);
  const patterns = useMemo(() => [...new Set(map.screens.flatMap((s) => s.patterns))].sort(), [map]);
  const visible = useMemo(() => map.screens.filter((s) => (showExternal || s.kind === "app") && !deleted.has(s.id)), [map, showExternal, deleted]);
  const tree = useMemo(
    () => discoveryTree(map, visible, { deleted, parents, labels: edits.labels }),
    [map, visible, deleted, parents, edits.labels],
  );
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
    if (selected !== renameInSide) setRenameInSide(null); // only the screen just added opens with its name field
  }, [selected, renameInSide]);
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
            editor={editor}
            titleOf={titleOf}
            activeComment={activeComment}
            setActiveComment={setActiveComment}
            panTo={panTo}
          />
        )}
      </div>
      <aside className={`map-side ${sel ? "open" : ""}`} aria-label={sel ? `Screen ${sel.title}` : "Map overview"}>
        {sel ? (
          <SidePanel
            key={sel.id}
            run={run}
            map={map}
            screen={sel}
            byId={byId}
            note={notes[sel.id]}
            onClose={() => setSelected(null)}
            tree={tree}
            visible={visible}
            original={titleOf(sel.id)}
            autoRename={renameInSide === sel.id}
            onEdit={editor.edit}
            onAdded={(id) => (setSelected(id), setRenameInSide(id))}
            onRemoved={() => setSelected(null)}
          />
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
            {variant !== "story" && Object.keys(comments).length > 0 && (
              <CommentList
                comments={comments}
                placed={(c) => !c.screen || visible.some((s) => s.id === c.screen)}
                onPick={(c) => {
                  setSelected(null);
                  setActiveComment(c.id);
                  setPanTo({ id: c.id, n: Date.now() });
                }}
                active={activeComment}
              />
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
  editor,
  titleOf,
  activeComment,
  setActiveComment,
  panTo,
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
  editor: ReturnType<typeof useNotes>;
  titleOf: (id: string) => string;
  activeComment: string | null;
  setActiveComment: (id: string | null) => void;
  panTo: { id: string; n: number } | null;
}) {
  const rf = useReactFlow();
  const vp = useViewport();
  const { comments, edits } = editor;
  const [tool, setTool] = useState<Tool>("select");
  const [showPins, setShowPins] = useState(true);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [renaming, setRenaming] = useState<string | null>(null);
  const [relabel, setRelabel] = useState<string | null>(null); // the child whose incoming tree link is relabelled
  const [moveFrom, setMoveFrom] = useState<string | null>(null);
  const [dropOn, setDropOn] = useState<string | null>(null);
  const [toast, setToast] = useState<{ text: string; undo?: () => void } | null>(null);
  const toastTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  // Hand-placed positions, remembered per run, layout and direction.
  const [dragged, setDragged] = useStored<Record<string, { x: number; y: number }>>(keys.positions(run, `${variant}-${dir}`), {});
  const [live, setLive] = useState<Record<string, { x: number; y: number }>>({}); // mid-drag, not yet saved
  // Card sizes React Flow measured. Kept on the nodes so rebuilding them (on every edit or selection) doesn't
  // un-measure and hide every card until it is measured again.
  const [measured, setMeasured] = useState<Record<string, { width: number; height: number }>>({});
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
      const top = pad + 52; // the edit toolbar floats over the top edge
      const [W, H] = [el.clientWidth - 2 * pad, el.clientHeight - pad - top];
      const zoom = Math.min(1, Math.max(0.55, Math.min(W / b.width, H / b.height)));
      const [w, h] = [b.width * zoom, b.height * zoom];
      // Along the tree's direction pin the start; across it, keep the launch screen in the middle.
      const root = ns.find((n) => (n.data as { root?: boolean }).root);
      const rx = root ? root.position.x + (root.measured?.width ?? 0) / 2 : b.x + b.width / 2;
      const ry = root ? root.position.y + (root.measured?.height ?? 0) / 2 : b.y + b.height / 2;
      const lr = dir === "LR";
      const x = w <= W ? pad + (W - w) / 2 - b.x * zoom : lr ? pad - b.x * zoom : pad + W / 2 - rx * zoom;
      const y = h <= H ? top + (H - h) / 2 - b.y * zoom : lr ? top + H / 2 - ry * zoom : top - b.y * zoom;
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
        className: s.id === moveFrom ? "node-move-from" : undefined,
        position: live[s.id] ?? dragged[s.id] ?? layout.get(s.id) ?? { x: 0, y: 0 },
        measured: measured[s.id],
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
          drop: s.id === dropOn,
        },
      })),
    [visible, live, dragged, layout, run, dir, tree, selected, onPath, dim, notes, moveFrom, dropOn, measured],
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
        if (!g.labels.includes(t.label) && !(g.discovery && editor.edits.labels[g.to])) g.labels.push(t.label); // a label you wrote stands alone
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
        label: label && (showLabels || hot || touchesSel || (g.discovery && !!editor.edits.labels[g.to])) ? label : undefined,
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
  }, [tree, map.transitions, ids, links, selected, pathPairs, showLabels, variant, editor.edits.labels]);

  // Track positions in memory while dragging; save to storage once, when the drag ends.
  const liveRef = useRef(live);
  liveRef.current = live;
  const onNodesChange = useCallback(
    (changes: NodeChange<ScreenNode>[]) => {
      const next = { ...liveRef.current };
      const done: Record<string, { x: number; y: number }> = {};
      const sized = changes.flatMap((c) => (c.type === "dimensions" && c.dimensions ? [[c.id, c.dimensions] as const] : []));
      if (sized.length)
        setMeasured((m) =>
          sized.every(([id, d]) => m[id]?.width === d.width && m[id]?.height === d.height) ? m : { ...m, ...Object.fromEntries(sized) },
        );
      for (const c of changes) {
        if (c.type !== "position" || tool !== "select") continue; // other tools click cards; they never drag them
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
    [setDragged, tool],
  );

  // ── editing: tools, comments ──
  const nodePos = useMemo(() => {
    const m = new Map(nodes.map((n) => [n.id, n.position]));
    return (id: string): Point | undefined => m.get(id);
  }, [nodes]);
  const pinned = useMemo(() => Object.values(comments).sort((a, b) => a.created.localeCompare(b.created)), [comments]);
  const openCount = pinned.filter((c) => c.status === "open").length;
  const size: Point = { x: canvas.current?.clientWidth ?? 0, y: canvas.current?.clientHeight ?? 0 };
  const flowAt = (e: { clientX: number; clientY: number }) => rf.screenToFlowPosition({ x: e.clientX, y: e.clientY });

  const say = (text: string, undo?: () => void) => {
    setToast({ text, undo });
    clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(null), 5000);
  };
  const pickTool = (t: Tool) => {
    setTool(t);
    setDraft(null);
    setRenaming(null);
    setRelabel(null);
    setMoveFrom(null);
    if (t !== "select") setActiveComment(null);
  };
  const nameOf = (id: string) => byId.get(id)?.title ?? id;
  const below = (id: string) => {
    const out = new Set<string>();
    const walk = (x: string) => {
      for (const c of tree.children.get(x) ?? []) if (!out.has(c)) (out.add(c), walk(c));
    };
    walk(id);
    return out;
  };
  const removeScreen = (id: string) => {
    if (id === tree.root) return say("The launch screen can't be removed");
    const name = nameOf(id);
    editor.edit((e) => removeIn(e, id));
    if (selected === id) setSelected(null);
    say(`Removed ${name}`, editor.undoEdit);
  };
  /** Why `id` can't go under `parent`, or null when it can. */
  const cantMove = (id: string, parent: string) =>
    id === tree.root ? "The launch screen stays the root" : id === parent ? "" : below(id).has(parent) ? "A screen can't go under its own child" : null;
  const moveScreen = (id: string, parent: string | null) => {
    editor.edit((e) => moveIn(e, id, parent));
    say(parent ? `Moved ${nameOf(id)} under ${nameOf(parent)}` : `${nameOf(id)} is now a root of its own`, editor.undoEdit);
    setMoveFrom(null);
  };
  const addScreen = (parent: string | null) => {
    const id = newScreenId();
    editor.edit((e) => addPlanned(e, id, parent));
    setRenaming(id); // name it straight away
  };
  const clickNode = (e: React.MouseEvent, n: Node) => {
    if (tool === "comment") {
      const f = flowAt(e);
      setActiveComment(null);
      setDraft({ x: f.x - n.position.x, y: f.y - n.position.y, screen: n.id });
    } else if (tool === "rename") (setRelabel(null), setRenaming(n.id));
    else if (tool === "add") addScreen(n.id);
    else if (tool === "delete") removeScreen(n.id);
    else if (tool === "move") {
      if (!moveFrom) {
        if (n.id === tree.root) say("The launch screen stays the root");
        else setMoveFrom(n.id);
      } else {
        const why = cantMove(moveFrom, n.id);
        if (why === null) moveScreen(moveFrom, n.id);
        else if (why) say(why);
        else setMoveFrom(null);
      }
    } else setSelected(n.id === selected ? null : n.id);
  };
  const clickEdge = (_: React.MouseEvent, edge: Edge) => {
    // Only tree links (parent → child) carry a label of their own to edit.
    if (tool === "rename" && tree.parent.get(edge.target) === edge.source) (setRenaming(null), setRelabel(edge.target));
  };
  const clickPane = (e: React.MouseEvent) => {
    if (tool === "comment") {
      setActiveComment(null);
      setDraft(flowAt(e));
    } else if (tool === "add") addScreen(null);
    else if (tool === "move" && moveFrom) moveScreen(moveFrom, null);
    else {
      setSelected(null);
      setActiveComment(null);
      setDraft(null);
      setRenaming(null);
      setRelabel(null);
    }
  };
  // Tree: drop a card on another to move it under that one. The card goes back into the tidy layout.
  const dropTarget = (e: React.MouseEvent, n: Node) => {
    const c = flowAt(e); // under the pointer
    const hit = rf
      .getNodes()
      .find(
        (o) =>
          o.id !== n.id &&
          c.x >= o.position.x &&
          c.x <= o.position.x + (o.measured?.width ?? 0) &&
          c.y >= o.position.y &&
          c.y <= o.position.y + (o.measured?.height ?? 0),
      );
    return hit && cantMove(n.id, hit.id) === null ? hit.id : null;
  };
  const reparentOnDrop = variant === "tree" && tool === "select";
  const onNodeDrag = (e: React.MouseEvent, n: Node) => reparentOnDrop && setDropOn(dropTarget(e, n));
  const onNodeDragStop = (e: React.MouseEvent, n: Node) => {
    setDropOn(null);
    const to = reparentOnDrop ? dropTarget(e, n) : null;
    if (!to) return;
    setDragged((d) => {
      const next = { ...d };
      delete next[n.id];
      return next;
    });
    moveScreen(n.id, to);
  };
  const onKey = (e: KeyboardEvent) => {
    if ((e.target as HTMLElement | null)?.closest("input, textarea, select, [contenteditable]")) return;
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "z") {
      e.preventDefault();
      return editor.undoEdit();
    }
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    const k = e.key.toLowerCase();
    const t = TOOLS.find((x) => x.id !== "delete" && x.key.toLowerCase() === k);
    if (t) return pickTool(t.id);
    if (k === "escape") return (pickTool("select"), setActiveComment(null));
    // Delete removes the selected screen, unless focus is in a popover, the toolbar or the side panel.
    const inUi = (e.target as HTMLElement | null)?.closest?.(".cm-pop, .rename-box, .edit-bar, .map-side, .map-toolbar");
    if ((k === "delete" || k === "backspace") && selected && !inUi) removeScreen(selected);
  };
  const keyRef = useRef(onKey);
  keyRef.current = onKey;
  useEffect(() => {
    const h = (e: KeyboardEvent) => keyRef.current(e);
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, []);
  // A comment picked from the side list: bring it into view.
  useEffect(() => {
    if (!panTo) return;
    const c = comments[panTo.id];
    const p = c && pinPoint(c, nodePos);
    if (p) rf.setCenter(p.x, p.y, { zoom: Math.max(rf.getZoom(), 0.8), duration: 250 });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [panTo]);

  const active = activeComment ? comments[activeComment] : undefined;
  const activeAt = active ? pinPoint(active, nodePos) : null;
  const draftAt = draft ? pinPoint(draft, nodePos) : null;
  const renamingNode = renaming ? nodes.find((n) => n.id === renaming) : undefined;
  // The relabel box sits halfway along the link.
  const relabelAt = (() => {
    const from = relabel && tree.parent.get(relabel);
    const a = from && rf.getNode(from);
    const b = relabel && rf.getNode(relabel);
    if (!a || !b) return null;
    const mid = (n: Node) => ({ x: n.position.x + (n.measured?.width ?? 0) / 2, y: n.position.y + (n.measured?.height ?? 0) / 2 });
    const [m, n] = [mid(a), mid(b)];
    return { x: (m.x + n.x) / 2 - 100, y: (m.y + n.y) / 2 + 30 };
  })();

  return (
    <div className={`map-canvas tool-${tool}`} ref={canvas}>
      <EditToolbar
        tool={tool}
        setTool={pickTool}
        edits={edits}
        canUndo={editor.canUndo()}
        onUndo={editor.undoEdit}
        showPins={showPins}
        setShowPins={setShowPins}
        openCount={openCount}
        titleOf={titleOf}
        onChange={editor.edit}
      />
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
        onNodeClick={clickNode}
        onNodeDoubleClick={(_, n) => tool === "select" && !byId.get(n.id)?.planned && go(screenHref(run, n.id))}
        onNodeDrag={onNodeDrag}
        onNodeDragStop={onNodeDragStop}
        onEdgeClick={clickEdge}
        onPaneClick={clickPane}
        nodesDraggable={tool === "select"}
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
      <div className="cm-layer">
        {showPins &&
          pinned.map((c, i) => {
            const p = pinPoint(c, nodePos);
            if (!p) return null;
            return (
              <Pin
                key={c.id}
                n={i + 1}
                comment={c}
                at={toCanvas(vp, p)}
                zoom={vp.zoom}
                active={activeComment === c.id}
                onToggle={() => (setDraft(null), setActiveComment(activeComment === c.id ? null : c.id))}
                onDragEnd={(dx, dy) => editor.updateComment(c.id, { x: c.x + dx, y: c.y + dy })}
              />
            );
          })}
        {active && activeAt && (
          <Thread
            key={active.id}
            comment={active}
            at={toCanvas(vp, activeAt)}
            size={size}
            onUpdate={(patch: Partial<MapComment>) => editor.updateComment(active.id, patch)}
            onReply={(text) => editor.replyComment(active.id, text)}
            onDelete={() => {
              const gone = active;
              editor.deleteComment(gone.id);
              setActiveComment(null);
              say("Comment deleted", () => editor.restoreComment(gone));
            }}
            onClose={() => setActiveComment(null)}
          />
        )}
        {draft && draftAt && (
          <Composer
            key={`${draft.screen ?? ""}${draft.x},${draft.y}`}
            at={toCanvas(vp, draftAt)}
            size={size}
            anchor={draft.screen}
            onCancel={() => setDraft(null)}
            onPost={(text, tag) => {
              const id = editor.addComment({ ...draft, text, tag });
              setDraft(null);
              setActiveComment(id);
            }}
          />
        )}
        {renaming && renamingNode && (
          <RenameBox
            key={renaming}
            at={toCanvas(vp, renamingNode.position)}
            value={byId.get(renaming)?.title ?? ""}
            original={titleOf(renaming)}
            label="Screen name"
            onCancel={() => setRenaming(null)}
            onSave={(title) => {
              editor.edit((e) => renameIn(e, renaming, title, titleOf(renaming)));
              setRenaming(null);
            }}
          />
        )}
        {relabel && relabelAt && (
          <RenameBox
            key={`link-${relabel}`}
            at={toCanvas(vp, relabelAt)}
            value={tree.via.get(relabel)?.label ?? ""}
            original="Link label"
            label={`Label of the link into ${nameOf(relabel)}`}
            onCancel={() => setRelabel(null)}
            onSave={(text) => {
              editor.edit((e) => labelIn(e, relabel, text));
              setRelabel(null);
            }}
          />
        )}
      </div>
      {toast && (
        <div className="edit-toast" role="status">
          {toast.text}
          {toast.undo && (
            <button className="btn small" onClick={() => (toast.undo?.(), setToast(null))}>
              Undo
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function RenameBox({
  at,
  value,
  original,
  label,
  onSave,
  onCancel,
}: {
  at: Point;
  value: string;
  original: string;
  label: string;
  onSave: (t: string) => void;
  onCancel: () => void;
}) {
  const [text, setText] = useState(value);
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => ref.current?.select(), []);
  return (
    <div className="rename-box panel" style={{ left: at.x, top: Math.max(8, at.y - 46) }} onClick={(e) => e.stopPropagation()} onPointerDown={(e) => e.stopPropagation()}>
      <input
        ref={ref}
        className="cm-input"
        aria-label={label}
        value={text}
        placeholder={original}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") onSave(text.trim());
          if (e.key === "Escape") onCancel();
        }}
      />
      <button className="btn small primary" onClick={() => onSave(text.trim())}>Save</button>
    </div>
  );
}

function CommentList({
  comments,
  placed,
  onPick,
  active,
}: {
  comments: Record<string, MapComment>;
  placed: (c: MapComment) => boolean; // false: its screen is removed or hidden, so it has no pin
  onPick: (c: MapComment) => void;
  active: string | null;
}) {
  const byAge = Object.values(comments).sort((a, b) => a.created.localeCompare(b.created));
  const num = new Map(byAge.map((c, i) => [c.id, i + 1])); // the number on its pin
  const list = byAge.sort((a, b) => (a.status === b.status ? 0 : a.status === "open" ? -1 : 1));
  return (
    <div className="cm-list">
      <div className="kicker">Comments · {list.filter((c) => c.status === "open").length} open</div>
      {list.map((c) => (
        <button key={c.id} className={`cm-row ${active === c.id ? "on" : ""}`} onClick={() => onPick(c)} disabled={!placed(c)}>
          <span className={`cm-chip ${c.tag}`}>
            {num.get(c.id)} · {c.tag}
          </span>
          <span className="cm-row-text">{c.text}</span>
          <span className="cm-row-meta">
            {!placed(c) ? `${c.screen} hidden` : c.status === "resolved" ? "resolved" : (c.screen ?? "canvas")}
          </span>
        </button>
      ))}
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
                    className={`story-card ${selected === id ? "sel" : ""} ${dim(s) ? "dim" : ""} ${s.kind !== "app" || s.planned ? "ext" : ""}`}
                    onClick={() => setSelected(selected === id ? null : id)}
                    onDoubleClick={() => !s.planned && go(screenHref(run, id))}
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
  tree,
  visible,
  original,
  autoRename,
  onEdit,
  onAdded,
  onRemoved,
}: {
  run: string;
  map: AppMapData;
  screen: Screen;
  byId: Map<string, Screen>;
  note?: ScreenNote;
  onClose: () => void;
  tree: DiscoveryTree;
  visible: Screen[];
  original: string; // crawled name
  autoRename: boolean;
  onEdit: (change: (e: TreeEdits) => TreeEdits) => void;
  onAdded: (id: string) => void;
  onRemoved: () => void;
}) {
  const out = map.transitions.filter((t) => t.from === screen.id);
  const into = map.transitions.filter((t) => t.to === screen.id);
  const [naming, setNaming] = useState(autoRename);
  const [name, setName] = useState(screen.title);
  const parent = tree.parent.get(screen.id);
  const isRoot = screen.id === tree.root;
  // Where it can go: anywhere but under itself or its own subtree.
  const options = useMemo(() => {
    const mine = new Set([screen.id]);
    for (const id of tree.order) if (mine.has(tree.parent.get(id) ?? "")) mine.add(id);
    return visible.filter((s) => !mine.has(s.id));
  }, [screen.id, tree, visible]);
  const saveName = () => {
    onEdit((e) => renameIn(e, screen.id, name.trim(), original));
    setNaming(false);
  };
  return (
    <div className="col" style={{ gap: 14 }}>
      <div className="row side-head" style={{ alignItems: "flex-start", gap: 12 }}>
        <button className="btn icon-only side-close" onClick={onClose} aria-label="Close screen details" title="Close (Esc)">
          <Icon name="x" size={16} />
        </button>
        <Thumb run={run} screen={screen} className="side-thumb" />
        <div className="col grow" style={{ gap: 4 }}>
          {naming ? (
            <input
              className="cm-input"
              aria-label="Screen name"
              autoFocus
              onFocus={(e) => e.currentTarget.select()}
              value={name}
              placeholder={original}
              onChange={(e) => setName(e.target.value)}
              onBlur={saveName}
              onKeyDown={(e) => {
                if (e.key === "Enter") saveName();
                if (e.key === "Escape") (setName(screen.title), setNaming(false));
              }}
            />
          ) : (
            <h2>{screen.title}</h2>
          )}
          <span className="sid">{screen.planned ? "planned, not crawled" : screen.id}</span>
          {!screen.planned && <span className="small muted">{shortActivity(screen.activity)}</span>}
          <div className="row wrap" style={{ gap: 4 }}>
            {screen.patterns.map((p) => (
              <span key={p} className="chip">
                {p}
              </span>
            ))}
          </div>
          {screen.kind === "app" && !screen.planned && (
            <a className="btn primary" href={screenHref(run, screen.id)} style={{ alignSelf: "flex-start", marginTop: 6 }}>
              Open screen →
            </a>
          )}
        </div>
      </div>

      <div className="tree-edit">
        <h3 style={{ marginBottom: 6 }}>In the tree</h3>
        <div className="row wrap" style={{ gap: 6 }}>
          <button className="btn small" onClick={() => (setName(screen.title), setNaming(true))}>
            <Icon name="pencil" size={13} /> Rename
          </button>
          <button
            className="btn small"
            onClick={() => {
              const id = newScreenId();
              onEdit((e) => addPlanned(e, id, screen.id));
              onAdded(id);
            }}
          >
            <Icon name="plus" size={13} /> Add screen under
          </button>
          {!isRoot && (
            <button
              className="btn small"
              onClick={() => {
                onEdit((e) => removeIn(e, screen.id));
                onRemoved();
              }}
            >
              <Icon name="trash" size={13} /> Remove
            </button>
          )}
        </div>
        {!isRoot && (
          <label className="tree-edit-field small">
            <span className="muted">Under</span>
            <select
              value={parent ?? ""}
              onChange={(e) => onEdit((ed) => moveIn(ed, screen.id, e.target.value || null))}
            >
              <option value="">(a root of its own)</option>
              {options.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.planned ? "new" : s.id} · {s.title}
                </option>
              ))}
            </select>
          </label>
        )}
        {parent && (
          <label className="tree-edit-field small">
            <span className="muted">Reached by</span>
            <input
              className="cm-input"
              key={tree.via.get(screen.id)?.label ?? ""}
              defaultValue={tree.via.get(screen.id)?.label ?? ""}
              placeholder="Link label, e.g. Sign in"
              onBlur={(e) => onEdit((ed) => labelIn(ed, screen.id, e.target.value.trim()))}
              onKeyDown={(e) => e.key === "Enter" && e.currentTarget.blur()}
            />
          </label>
        )}
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
            {screen.planned
              ? "Added on the map: the crawl has not found this screen. Crawl again once it exists in the app."
              : screen.kind !== "app"
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
      {!screen.planned && (
        <a className="small" href={href("r", run, "replay") + `?screen=${encodeURIComponent(screen.id)}`}>
          See when the crawler found it →
        </a>
      )}
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
