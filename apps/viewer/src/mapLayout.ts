import type { AppMapData, Screen } from "./types";
import { rootScreen } from "./util";

// Layouts for the Map view, all built on the *discovery tree*: each screen's parent is the screen the crawler
// was on when it first reached it (the last step of its reach path). Every screen has exactly one parent, so
// the tree reads cleanly; all other transitions are "extra links" drawn only on demand.

export interface DiscoveryTree {
  root: string | undefined;
  roots: string[]; // root first, then other entry points, then screens with no recorded path
  entry: Set<string>; // screens the app can start on (origin "launch", plus the root)
  orphan: Set<string>; // no recorded way to reach them (origin "unknown", or no parent in older runs)
  parent: Map<string, string>;
  children: Map<string, string[]>;
  depth: Map<string, number>; // depth in the tree (taps from launch along the discovery path)
  via: Map<string, { label: string; kind: string }>; // how the parent → child step was taken
  order: string[]; // pre-order: parents before children, siblings by discovery time
}

/** Tree edits that change the shape: screens taken out (their children move up), screens moved under another,
 *  and relabelled links (keyed by the child). */
export interface ShapeEdits {
  deleted: Set<string>;
  parents: Record<string, string | null>; // null: a root of its own
  labels?: Record<string, string>;
}

export function discoveryTree(map: AppMapData, visible: Screen[], edits?: ShapeEdits): DiscoveryTree {
  const ids = new Set(visible.map((s) => s.id));
  const byId = new Map(visible.map((s) => [s.id, s]));
  const hidden = edits?.deleted ?? new Set<string>();
  const everyone = new Map(map.screens.map((s) => [s.id, s]));
  const root = rootScreen(map)?.id;
  const parent = new Map<string, string>();
  const via = new Map<string, { label: string; kind: string }>();
  const moved = new Set<string>(); // screens moved to be a root of their own

  const firstTransition = (from: string, to: string) =>
    map.transitions.filter((t) => t.from === from && t.to === to).sort((a, b) => a.step - b.step)[0];

  // The screen the crawler was on when it first reached `s`, and how, among the screens in `known`.
  const found = (s: Screen, known: Set<string>) => {
    let p: string | undefined;
    let label = "";
    let kind = "";
    const last = s.reach_path[s.reach_path.length - 1];
    if (s.kind === "app" && last) {
      p = last.screen;
      label = last.label;
    } else {
      // External or path-less screens: the earliest transition into them.
      const t = map.transitions.filter((x) => x.to === s.id && x.from !== s.id && known.has(x.from)).sort((a, b) => a.step - b.step)[0];
      if (t) [p, label, kind] = [t.from, t.label, t.kind];
    }
    return { p, label, kind };
  };
  const allIds = new Set(everyone.keys());

  for (const s of visible) {
    if (s.id === root) continue;
    const want = edits?.parents[s.id];
    if (want === null) {
      moved.add(s.id);
      continue;
    }
    if (s.origin === "launch" && want === undefined) continue;
    if (s.origin === "unknown" && want === undefined) continue;
    let { p, label, kind } = found(s, hidden.size ? new Set([...ids, ...hidden]) : ids);
    if (want) [p, label, kind] = [want, firstTransition(want, s.id)?.label ?? "", ""];
    // A screen taken out of the tree: its children hang off whatever it hung off (its own move included).
    for (let n = 0; p && hidden.has(p) && n < 100; n++) {
      const up = everyone.get(p);
      const moved = edits?.parents[p];
      p = moved !== undefined ? (moved ?? undefined) : up ? found(up, allIds).p : undefined;
    }
    if (!p || !ids.has(p) || p === s.id) continue;
    parent.set(s.id, p);
    via.set(s.id, { label: edits?.labels?.[s.id] ?? label, kind: kind || firstTransition(p, s.id)?.kind || "" });
  }
  // A move that would put a screen under its own descendant is dropped (the UI refuses it too).
  const cyclic = (id: string) => {
    for (let at = parent.get(id), n = 0; at && n < 500; at = parent.get(at), n++) if (at === id) return true;
    return false;
  };
  for (const s of visible)
    if (parent.has(s.id) && cyclic(s.id)) {
      parent.delete(s.id);
      via.delete(s.id);
    }

  const children = new Map<string, string[]>();
  for (const [c, p] of parent) children.set(p, [...(children.get(p) ?? []), c]);
  const born = (id: string) => byId.get(id)?.first_step ?? 0;
  for (const list of children.values()) list.sort((a, b) => born(a) - born(b));

  const entry = new Set(visible.filter((s) => s.id === root || s.origin === "launch" || moved.has(s.id)).map((s) => s.id));
  const orphan = new Set(visible.filter((s) => !entry.has(s.id) && !parent.has(s.id)).map((s) => s.id));
  const byBirth = (a: Screen, b: Screen) => a.first_step - b.first_step;
  const roots = [
    ...(root && ids.has(root) ? [root] : []),
    ...visible.filter((s) => s.id !== root && entry.has(s.id)).sort(byBirth).map((s) => s.id),
    ...visible.filter((s) => orphan.has(s.id)).sort(byBirth).map((s) => s.id),
  ];

  const depth = new Map<string, number>();
  const order: string[] = [];
  const seen = new Set<string>();
  const walk = (id: string, d: number) => {
    if (seen.has(id)) return; // defensive: reach paths never cycle, but don't trust input blindly
    seen.add(id);
    depth.set(id, d);
    order.push(id);
    for (const c of children.get(id) ?? []) walk(c, d + 1);
  };
  for (const r of roots) walk(r, 0);

  return { root, roots, entry, orphan, parent, children, depth, via, order };
}

/**
 * Tidy tree: leaves take consecutive slots on the cross axis, parents sit centred on their children, and depth
 * runs along the main axis. Slots are sized to the largest card so columns stay straight; each card is centred in
 * its slot, so mixed phone/tablet/landscape screenshots still line up. Returns top-left positions.
 */
export function tidyLayout(
  tree: DiscoveryTree,
  sizeOf: (id: string) => { w: number; h: number },
  dir: "LR" | "TB",
): Map<string, { x: number; y: number }> {
  const ids = [...tree.depth.keys()];
  const maxW = Math.max(1, ...ids.map((id) => sizeOf(id).w));
  const maxH = Math.max(1, ...ids.map((id) => sizeOf(id).h));
  const mainStep = dir === "LR" ? maxW + 90 : maxH + 64;
  const crossStep = dir === "LR" ? maxH + 24 : maxW + 24;
  const pos = new Map<string, { x: number; y: number }>();
  let cursor = 0;
  const seen = new Set<string>();

  const place = (id: string, d: number): number => {
    seen.add(id);
    const kids = (tree.children.get(id) ?? []).filter((k) => !seen.has(k));
    let cross: number;
    if (!kids.length) {
      cross = cursor;
      cursor += crossStep;
    } else {
      const cs = kids.map((k) => place(k, d + 1));
      cross = (cs[0] + cs[cs.length - 1]) / 2;
    }
    const { w, h } = sizeOf(id);
    const main = d * mainStep;
    pos.set(id, dir === "LR" ? { x: main + (maxW - w) / 2, y: cross + (maxH - h) / 2 } : { x: cross + (maxW - w) / 2, y: main + (maxH - h) / 2 });
    return cross;
  };
  for (const r of tree.roots) {
    if (seen.has(r)) continue;
    place(r, 0);
    cursor += crossStep * 0.6; // breathing room between separate trees
  }
  return pos;
}

export interface Lane {
  hub: string;
  label: string; // why this is a section
  items: { id: string; rel: number }[]; // pre-order within the lane; rel = depth below the hub
}

/**
 * Storyboard lanes: one per app section. A section starts at the launch screen, at each screen reached from it
 * directly, and at each destination of a bottom-nav or tab tap. Every other screen belongs to the nearest
 * section above it in the discovery tree.
 */
export function storyLanes(tree: DiscoveryTree): Lane[] {
  const isHub = (id: string) => {
    if (tree.entry.has(id) || !tree.parent.has(id)) return true;
    if (tree.parent.get(id) === tree.root) return true;
    const k = tree.via.get(id)?.kind;
    return k === "nav" || k === "tab";
  };
  const laneOf = (id: string) => {
    for (let cur: string | undefined = id; cur; cur = tree.parent.get(cur)) if (isHub(cur)) return cur;
    return id;
  };

  const lanes = new Map<string, Lane>();
  for (const id of tree.order) {
    const hub = laneOf(id);
    if (!lanes.has(hub)) {
      const v = tree.via.get(hub);
      const label =
        hub === tree.root
          ? "Launch"
          : tree.entry.has(hub)
            ? "Also a start screen"
            : tree.orphan.has(hub)
              ? "No recorded path"
            : v?.kind === "nav"
              ? `Bottom nav · ${v.label}`
              : v?.kind === "tab"
                ? `Tab · ${v.label}`
                : `From launch · ${v?.label ?? ""}`;
      lanes.set(hub, { hub, label, items: [] });
    }
    lanes.get(hub)!.items.push({ id, rel: (tree.depth.get(id) ?? 0) - (tree.depth.get(hub) ?? 0) });
  }
  return [...lanes.values()];
}
