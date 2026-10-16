import { useEffect, useRef, useState } from "react";
import { Icon, type IconName } from "../components/Icon";
import { editCount, emptyEdits, type CommentTag, type MapComment, type TreeEdits } from "../notes";
import type { Screen } from "../types";

// Editing the map: a floating toolbar (select, comment, add, move under, rename, delete), Figma-style comment pins
// with threads, and a list of what was changed. Everything is saved in notes.json; map.json is never touched.

export type Tool = "select" | "comment" | "add" | "move" | "rename" | "delete";

export const TOOLS: { id: Tool; label: string; key: string; icon: IconName; hint: string }[] = [
  { id: "select", label: "Select", key: "V", icon: "cursor", hint: "Click a screen to light up its path" },
  { id: "comment", label: "Comment", key: "C", icon: "message", hint: "Click anywhere to drop a pin; on a screen it follows that screen" },
  { id: "add", label: "Add", key: "A", icon: "plus", hint: "Click a screen to add a planned screen under it (empty space: a new root)" },
  { id: "move", label: "Move under", key: "M", icon: "reparent", hint: "Click the screen to move, then its new parent (empty space: its own root)" },
  { id: "rename", label: "Rename", key: "R", icon: "pencil", hint: "Click a screen to rename it, or a link to relabel it" },
  { id: "delete", label: "Remove", key: "⌫", icon: "trash", hint: "Click a screen to take it out of the tree (children move up)" },
];

export const TAGS: { id: CommentTag; label: string }[] = [
  { id: "bug", label: "Bug" },
  { id: "flow", label: "Flow" },
  { id: "copy", label: "Copy" },
  { id: "question", label: "Question" },
];

export interface Viewport {
  x: number;
  y: number;
  zoom: number;
}
export interface Point {
  x: number;
  y: number;
}
export const toCanvas = (vp: Viewport, p: Point): Point => ({ x: p.x * vp.zoom + vp.x, y: p.y * vp.zoom + vp.y });

/** Where the pin is in flow space: a point, or an offset from its screen's card. */
export function pinPoint(c: { x: number; y: number; screen?: string }, nodePos: (id: string) => Point | undefined): Point | null {
  if (!c.screen) return { x: c.x, y: c.y };
  const n = nodePos(c.screen);
  return n ? { x: n.x + c.x, y: n.y + c.y } : null;
}

// ── tree edits (pure: each returns the edits with one change made) ───────────

export const newScreenId = () => `n-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 4)}`;

const without = <T,>(rec: Record<string, T>, id: string): Record<string, T> => {
  const out = { ...rec };
  delete out[id];
  return out;
};

/** A planned screen: a step the flow should have that the crawl has not found. Drawn dashed, with no screenshot. */
export function plannedScreens(edits: TreeEdits, like: Screen | undefined): Screen[] {
  return Object.entries(edits.added).map(([id, a], i) => ({
    id,
    kind: "app",
    title: edits.titles[id] ?? a.title,
    activity: null,
    package: null,
    signature: "",
    patterns: [],
    depth: 0,
    visits: 0,
    first_step: 1e9 + i, // after every crawled sibling, in the order they were added
    origin: "action",
    width: like?.width ?? 1080,
    height: like?.height ?? 2400,
    screenshot: null,
    thumb: null,
    hierarchy: null,
    reach_path: [],
    autofill: [],
    tokens: [],
    elements: [],
    planned: true,
  }));
}

export const addPlanned = (e: TreeEdits, id: string, parent: string | null, title = "New screen"): TreeEdits => ({
  ...e,
  added: { ...e.added, [id]: { title, parent, created: new Date().toISOString() } },
});

/** Take a screen out of the tree. A planned one is dropped outright; whatever hung under it moves up to its parent. */
export function removeIn(e: TreeEdits, id: string): TreeEdits {
  const planned = e.added[id];
  if (!planned) return { ...e, deleted: [...new Set([...e.deleted, id])] };
  const up = e.parents[id] !== undefined ? e.parents[id] : planned.parent;
  const added = Object.fromEntries(Object.entries(without(e.added, id)).map(([k, a]) => [k, a.parent === id ? { ...a, parent: up } : a]));
  const parents = Object.fromEntries(Object.entries(without(e.parents, id)).map(([k, p]) => [k, p === id ? up : p]));
  return { ...e, added, parents, titles: without(e.titles, id), labels: without(e.labels, id) };
}

export const moveIn = (e: TreeEdits, id: string, parent: string | null): TreeEdits =>
  e.added[id]
    ? { ...e, added: { ...e.added, [id]: { ...e.added[id], parent } }, parents: without(e.parents, id) }
    : { ...e, parents: { ...e.parents, [id]: parent } };

/** Rename a screen; an empty name, or its crawled one, drops the rename. */
export function renameIn(e: TreeEdits, id: string, title: string, original: string): TreeEdits {
  if (e.added[id]) return title ? { ...e, added: { ...e.added, [id]: { ...e.added[id], title } } } : e;
  return title && title !== original ? { ...e, titles: { ...e.titles, [id]: title } } : { ...e, titles: without(e.titles, id) };
}

/** Relabel the tree link into `id`; empty puts back the crawled label. */
export const labelIn = (e: TreeEdits, id: string, label: string): TreeEdits =>
  label ? { ...e, labels: { ...e.labels, [id]: label } } : { ...e, labels: without(e.labels, id) };

type EditKind = "titles" | "deleted" | "parents" | "added" | "labels";
function revertIn(e: TreeEdits, kind: EditKind, id: string): TreeEdits {
  if (kind === "deleted") return { ...e, deleted: e.deleted.filter((x) => x !== id) };
  if (kind === "added") return removeIn(e, id);
  return { ...e, [kind]: without(e[kind], id) };
}

// ── toolbar ──────────────────────────────────────────────────────────────────

export function EditToolbar({
  tool,
  setTool,
  edits,
  canUndo,
  onUndo,
  showPins,
  setShowPins,
  openCount,
  titleOf,
  onChange,
}: {
  tool: Tool;
  setTool: (t: Tool) => void;
  edits: TreeEdits;
  canUndo: boolean;
  onUndo: () => void;
  showPins: boolean;
  setShowPins: (v: boolean) => void;
  openCount: number;
  titleOf: (id: string) => string;
  onChange: (change: (e: TreeEdits) => TreeEdits) => void;
}) {
  const [listOpen, setListOpen] = useState(false);
  const n = editCount(edits);
  const hint = TOOLS.find((t) => t.id === tool)?.hint;
  const onRevert = (kind: EditKind, id: string) => onChange((e) => revertIn(e, kind, id));
  return (
    <div className="edit-bar" role="toolbar" aria-label="Edit the map" onClick={(e) => e.stopPropagation()}>
      <div className="edit-bar-row">
        <div className="edit-tools" role="group" aria-label="Tools">
          {TOOLS.map((t) => (
            <button
              key={t.id}
              className={`edit-tool ${tool === t.id ? "on" : ""}`}
              aria-pressed={tool === t.id}
              title={`${t.label} (${t.key})`}
              onClick={() => setTool(t.id)}
            >
              <Icon name={t.icon} size={15} />
              <span className="edit-tool-label">{t.label}</span>
              <kbd>{t.key}</kbd>
            </button>
          ))}
        </div>
        <span className="edit-sep" aria-hidden="true" />
        <button className="edit-tool" title="Undo (⌘Z)" aria-label="Undo" disabled={!canUndo} onClick={onUndo}>
          <Icon name="undo" size={15} />
        </button>
        <button
          className={`edit-tool ${listOpen ? "on" : ""}`}
          aria-expanded={listOpen}
          disabled={n === 0}
          title="Changes made to the tree"
          onClick={() => setListOpen((o) => !o)}
        >
          Edits <span className="edit-count">{n}</span>
        </button>
        <button
          className={`edit-tool ${showPins ? "on" : ""}`}
          aria-pressed={showPins}
          title={showPins ? "Hide comment pins" : "Show comment pins"}
          onClick={() => setShowPins(!showPins)}
        >
          <Icon name="message" size={15} /> <span className="edit-count">{openCount}</span>
          <span className="sr-only"> open comments</span>
        </button>
      </div>
      {tool !== "select" && <div className="edit-hint">{hint}</div>}
      {listOpen && n > 0 && (
        <div className="edit-list panel">
          {Object.entries(edits.added).map(([id, a]) => (
            <div className="edit-item" key={`a${id}`}>
              <span>
                <b>{a.title}</b> added <span className="muted">{a.parent ? `under ${a.parent}` : "as a root"}</span>
              </span>
              <button className="btn small" onClick={() => onRevert("added", id)}>Remove</button>
            </div>
          ))}
          {Object.entries(edits.titles)
            .filter(([id]) => !edits.added[id])
            .map(([id, t]) => (
            <div className="edit-item" key={`t${id}`}>
              <span>
                <b>{id}</b> renamed <span className="muted">{t}</span>
              </span>
              <button className="btn small" onClick={() => onRevert("titles", id)}>Revert</button>
            </div>
            ))}
          {edits.deleted.map((id) => (
            <div className="edit-item" key={`d${id}`}>
              <span>
                <b>{id}</b> removed <span className="muted">{titleOf(id)}</span>
              </span>
              <button className="btn small" onClick={() => onRevert("deleted", id)}>Restore</button>
            </div>
          ))}
          {Object.entries(edits.labels).map(([id, l]) => (
            <div className="edit-item" key={`l${id}`}>
              <span>
                link into <b>{id}</b> <span className="muted">“{l}”</span>
              </span>
              <button className="btn small" onClick={() => onRevert("labels", id)}>Revert</button>
            </div>
          ))}
          {Object.entries(edits.parents).map(([id, p]) => (
            <div className="edit-item" key={`p${id}`}>
              <span>
                <b>{id}</b> moved <span className="muted">{p ? `under ${p}` : "to its own root"}</span>
              </span>
              <button className="btn small" onClick={() => onRevert("parents", id)}>Revert</button>
            </div>
          ))}
          <button className="btn small edit-reset" onClick={() => (onChange(emptyEdits), setListOpen(false))}>Reset all edits</button>
        </div>
      )}
    </div>
  );
}

// ── comment pins and threads ─────────────────────────────────────────────────

export interface Draft {
  x: number;
  y: number;
  screen?: string;
}

const TAG_CLASS: Record<CommentTag, string> = { bug: "bad", flow: "accent", copy: "warn", question: "info" };

function TagChips({ value, onChange }: { value: CommentTag; onChange: (t: CommentTag) => void }) {
  return (
    <div className="cm-tags" role="group" aria-label="Tag">
      {TAGS.map((t) => (
        <button key={t.id} className={`cm-tag ${TAG_CLASS[t.id]} ${value === t.id ? "on" : ""}`} aria-pressed={value === t.id} onClick={() => onChange(t.id)}>
          {t.label}
        </button>
      ))}
    </div>
  );
}

function Popover({ at, size, children, label }: { at: Point; size: Point; children: React.ReactNode; label: string }) {
  const W = 288;
  const left = at.x + 22 + W > size.x ? Math.max(8, at.x - 14 - W) : at.x + 22;
  const top = Math.min(Math.max(8, at.y - 14), Math.max(8, size.y - 340));
  return (
    <div className="cm-pop panel" style={{ left, top, width: W }} role="dialog" aria-label={label} onClick={(e) => e.stopPropagation()} onPointerDown={(e) => e.stopPropagation()}>
      {children}
    </div>
  );
}

export function Composer({ at, size, onPost, onCancel, anchor }: { at: Point; size: Point; onPost: (text: string, tag: CommentTag) => void; onCancel: () => void; anchor?: string }) {
  const [text, setText] = useState("");
  const [tag, setTag] = useState<CommentTag>("flow");
  const ref = useRef<HTMLTextAreaElement>(null);
  useEffect(() => ref.current?.focus(), []);
  const post = () => text.trim() && onPost(text.trim(), tag);
  return (
    <Popover at={at} size={size} label="New comment">
      <div className="cm-head">
        <span className="kicker">New comment{anchor ? ` on ${anchor}` : ""}</span>
      </div>
      <TagChips value={tag} onChange={(t) => (setTag(t), ref.current?.focus())} />
      <textarea
        ref={ref}
        className="cm-input"
        rows={3}
        placeholder="What should change here?"
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) (e.preventDefault(), post());
          if (e.key === "Escape") onCancel();
        }}
      />
      <div className="cm-actions">
        <button className="btn small" onClick={onCancel}>Cancel</button>
        <button className="btn small primary" disabled={!text.trim()} onClick={post}>Comment</button>
      </div>
    </Popover>
  );
}

export function Thread({
  comment,
  at,
  size,
  onUpdate,
  onReply,
  onDelete,
  onClose,
}: {
  comment: MapComment;
  at: Point;
  size: Point;
  onUpdate: (patch: Partial<MapComment>) => void;
  onReply: (text: string) => void;
  onDelete: () => void;
  onClose: () => void;
}) {
  const [reply, setReply] = useState("");
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(comment.text);
  const resolved = comment.status === "resolved";
  return (
    <Popover at={at} size={size} label="Comment thread">
      <div className="cm-head">
        <span className={`cm-status ${resolved ? "good" : ""}`}>{resolved ? "Resolved" : "Open"}</span>
        <span className="cm-head-actions">
          <button className="btn icon-only" title={resolved ? "Reopen" : "Resolve"} aria-label={resolved ? "Reopen" : "Resolve"} onClick={() => onUpdate({ status: resolved ? "open" : "resolved" })}>
            <Icon name="check" size={15} />
          </button>
          <button className="btn icon-only" title="Delete comment" aria-label="Delete comment" onClick={onDelete}>
            <Icon name="trash" size={15} />
          </button>
          <button className="btn icon-only" title="Close" aria-label="Close" onClick={onClose}>
            <Icon name="x" size={15} />
          </button>
        </span>
      </div>
      <TagChips value={comment.tag} onChange={(t) => onUpdate({ tag: t })} />
      {editing ? (
        <>
          <textarea className="cm-input" rows={3} value={draft} onChange={(e) => setDraft(e.target.value)} autoFocus />
          <div className="cm-actions">
            <button className="btn small" onClick={() => (setDraft(comment.text), setEditing(false))}>Cancel</button>
            <button className="btn small primary" disabled={!draft.trim()} onClick={() => (onUpdate({ text: draft.trim() }), setEditing(false))}>Save</button>
          </div>
        </>
      ) : (
        <p className="cm-text" onDoubleClick={() => setEditing(true)} title="Double-click to edit">
          {comment.text}
        </p>
      )}
      {comment.replies.map((r, i) => (
        <p className="cm-reply" key={i}>
          {r.text}
        </p>
      ))}
      <input
        className="cm-input cm-reply-input"
        placeholder="Reply…"
        value={reply}
        onChange={(e) => setReply(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && reply.trim()) (onReply(reply), setReply(""));
          if (e.key === "Escape") onClose();
        }}
      />
    </Popover>
  );
}

export function Pin({
  n,
  comment,
  at,
  active,
  onToggle,
  onDragEnd,
  zoom,
}: {
  n: number;
  comment: MapComment;
  at: Point;
  active: boolean;
  onToggle: () => void;
  onDragEnd: (dx: number, dy: number) => void; // in flow units
  zoom: number;
}) {
  const [drag, setDrag] = useState<Point | null>(null);
  const start = useRef<Point | null>(null);
  const resolved = comment.status === "resolved";
  return (
    <button
      className={`cm-pin ${TAG_CLASS[comment.tag]} ${active ? "active" : ""} ${resolved ? "resolved" : ""}`}
      style={{ left: at.x + (drag?.x ?? 0), top: at.y + (drag?.y ?? 0) }}
      aria-label={`Comment ${n}, ${comment.tag}, ${resolved ? "resolved" : "open"}: ${comment.text}`}
      aria-expanded={active}
      title={`${comment.tag} · ${resolved ? "resolved" : "open"}`}
      onClick={(e) => {
        e.stopPropagation();
        if (e.detail === 0) onToggle(); // Enter / Space: pointer clicks toggle on pointer up
      }}
      onPointerCancel={() => ((start.current = null), setDrag(null))}
      onPointerDown={(e) => {
        e.stopPropagation();
        start.current = { x: e.clientX, y: e.clientY };
        e.currentTarget.setPointerCapture(e.pointerId);
      }}
      onPointerMove={(e) => {
        if (!start.current) return;
        const d = { x: e.clientX - start.current.x, y: e.clientY - start.current.y };
        if (drag || Math.hypot(d.x, d.y) > 4) setDrag(d);
      }}
      onPointerUp={() => {
        if (!start.current) return;
        if (drag) onDragEnd(drag.x / zoom, drag.y / zoom);
        else onToggle();
        start.current = null;
        setDrag(null);
      }}
    >
      {resolved ? <Icon name="check" size={13} /> : n}
    </button>
  );
}
