import { useCallback, useMemo, useSyncExternalStore } from "react";
import { runFile } from "./api";
import { keys, read, remove, write } from "./storage";

// Stars and notes people add to screens. Saved to runs/<run>/notes.json through `appscreenmap serve` (or the
// dev server) so they live next to the map: they survive browser resets, are shared by everyone viewing the
// same runs/ folder, and can be committed. On a read-only host the PUT fails and notes are kept in
// localStorage instead, then pushed to the file the next time saving works.

export interface ScreenNote {
  star?: boolean;
  note?: string;
  updated: string;
}
export type RunNotes = Record<string, ScreenNote>;

/** A reviewer's decision on one accessibility finding, keyed by A11yIssue.key. */
export interface A11yTriage {
  status: "confirmed" | "wontfix" | "false_positive";
  note?: string;
  updated: string;
}
export type RunTriage = Record<string, A11yTriage>;
/** "open" clears a decision (unless it still has a note). */
export interface TriagePatch {
  status?: A11yTriage["status"] | "open";
  note?: string;
}

export type CommentTag = "bug" | "flow" | "copy" | "question";

/** A Figma-style pin on the map. With `screen`, x/y are an offset from that card's top-left, so the pin follows it. */
export interface MapComment {
  id: string;
  x: number;
  y: number;
  screen?: string;
  tag: CommentTag;
  status: "open" | "resolved";
  text: string;
  replies: { text: string; created: string }[];
  created: string;
  updated: string;
}
export type RunComments = Record<string, MapComment>;

/** A screen added in the viewer that the crawl has not found (yet): a step the flow should have. */
export interface PlannedScreen {
  title: string;
  parent: string | null; // null: a root of its own
  created: string;
}

/** Changes to the tree made in the viewer, kept apart from map.json (which stays the crawler's output). */
export interface TreeEdits {
  titles: Record<string, string>; // screen id → name
  deleted: string[]; // screens taken out of the tree (their children move up)
  parents: Record<string, string | null>; // screen id → new parent (null: a root of its own)
  added: Record<string, PlannedScreen>; // planned screens, ids "n-…"
  labels: Record<string, string>; // screen id → label of the link into it from its tree parent
}
export const emptyEdits = (): TreeEdits => ({ titles: {}, deleted: [], parents: {}, added: {}, labels: {} });
const NO_EDITS: TreeEdits = emptyEdits();
export const editCount = (e: TreeEdits) =>
  Object.keys(e.titles).length + e.deleted.length + Object.keys(e.parents).length + Object.keys(e.added).length + Object.keys(e.labels).length;

interface Doc {
  notes: RunNotes;
  a11y: RunTriage;
  comments: RunComments;
  edits: TreeEdits;
}

/** file: saved in runs/<run>/notes.json · browser: server is read-only, kept in localStorage */
export type NotesMode = "loading" | "file" | "browser";

interface State extends Doc {
  mode: NotesMode;
  saving: boolean;
}

const SAVE_DELAY_MS = 500;

class NotesStore {
  state: State = { notes: {}, a11y: {}, comments: {}, edits: NO_EDITS, mode: "loading", saving: false };
  private history: TreeEdits[] = []; // edits before each change, for undo (this session only)
  private listeners = new Set<() => void>();
  private timer: ReturnType<typeof setTimeout> | undefined;
  private url: string;

  constructor(private run: string) {
    this.url = runFile(run, "notes.json");
    void this.load();
  }

  subscribe = (fn: () => void) => {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  };

  private set(patch: Partial<State>) {
    this.state = { ...this.state, ...patch };
    this.listeners.forEach((fn) => fn());
  }

  private async load() {
    let fromFile: Partial<Doc> = {};
    try {
      const r = await fetch(this.url, { cache: "no-store" });
      if (r.ok) fromFile = (await r.json()) as Partial<Doc>;
    } catch {
      // no notes file yet, or offline: start empty
    }
    const pending = read<Partial<Doc>>(keys.notesFallback(this.run), {});
    const hasPending =
      Object.keys(pending.notes ?? {}).length +
        Object.keys(pending.a11y ?? {}).length +
        Object.keys(pending.comments ?? {}).length +
        (pending.edits ? editCount({ ...NO_EDITS, ...pending.edits }) : 0) >
      0;
    this.set({
      notes: mergeNewest(fromFile.notes ?? {}, pending.notes ?? {}),
      a11y: mergeNewest(fromFile.a11y ?? {}, pending.a11y ?? {}),
      comments: mergeNewest(fromFile.comments ?? {}, pending.comments ?? {}),
      edits: { ...NO_EDITS, ...(pending.edits && editCount({ ...NO_EDITS, ...pending.edits }) ? pending.edits : fromFile.edits) },
      mode: hasPending ? "browser" : "file",
    });
    if (hasPending) await this.persist(); // push edits made while the server was read-only
  }

  update(sid: string, patch: Partial<Omit<ScreenNote, "updated">>) {
    const next = { ...this.state.notes };
    const merged = { ...next[sid], ...patch, updated: new Date().toISOString() };
    if (!merged.star && !merged.note?.trim()) delete next[sid];
    else next[sid] = merged;
    this.set({ notes: next });
    this.schedule();
  }

  triage(key: string, patch: TriagePatch) {
    const next = { ...this.state.a11y };
    const merged: TriagePatch & { updated: string } = {
      ...next[key],
      ...patch,
      updated: new Date().toISOString(),
    };
    if (merged.status === "open" || !merged.status) {
      if (merged.note?.trim()) next[key] = { ...merged, status: "confirmed" };
      else delete next[key];
    } else next[key] = merged as A11yTriage;
    this.set({ a11y: next });
    this.schedule();
  }

  // ── comments ──
  addComment(c: Omit<MapComment, "id" | "created" | "updated" | "replies" | "status">): string {
    const now = new Date().toISOString();
    const id = `c${Date.now().toString(36)}${Math.random().toString(36).slice(2, 5)}`;
    this.set({ comments: { ...this.state.comments, [id]: { ...c, id, status: "open", replies: [], created: now, updated: now } } });
    this.schedule();
    return id;
  }

  updateComment(id: string, patch: Partial<Omit<MapComment, "id" | "created" | "updated">>) {
    const cur = this.state.comments[id];
    if (!cur) return;
    this.set({ comments: { ...this.state.comments, [id]: { ...cur, ...patch, updated: new Date().toISOString() } } });
    this.schedule();
  }

  replyComment(id: string, text: string) {
    const cur = this.state.comments[id];
    if (!cur || !text.trim()) return;
    this.updateComment(id, { replies: [...cur.replies, { text: text.trim(), created: new Date().toISOString() }] });
  }

  /** Put back a deleted comment (undo). */
  restoreComment(c: MapComment) {
    this.set({ comments: { ...this.state.comments, [c.id]: c } });
    this.schedule();
  }

  deleteComment(id: string) {
    const next = { ...this.state.comments };
    delete next[id];
    this.set({ comments: next });
    this.schedule();
  }

  // ── tree edits ──
  edit(change: (e: TreeEdits) => TreeEdits) {
    const before = this.state.edits;
    const after = change(structuredClone(before));
    if (JSON.stringify(after) === JSON.stringify(before)) return;
    this.history.push(before);
    this.set({ edits: after });
    this.schedule();
  }

  canUndo() {
    return this.history.length > 0;
  }

  undoEdit() {
    const prev = this.history.pop();
    if (!prev) return;
    this.set({ edits: prev });
    this.schedule();
  }

  private schedule() {
    this.set({ saving: true });
    clearTimeout(this.timer);
    this.timer = setTimeout(() => void this.persist(), SAVE_DELAY_MS);
  }

  /** Save now; used on page hide so a debounced edit isn't lost. */
  flush() {
    if (!this.state.saving) return;
    clearTimeout(this.timer);
    void this.persist(true);
  }

  private async persist(keepalive = false) {
    const doc: Doc = {
      notes: this.state.notes,
      a11y: this.state.a11y,
      comments: this.state.comments,
      edits: this.state.edits,
    };
    const body = JSON.stringify({ appscreenmap_notes: 1, run: this.run, ...doc });
    try {
      const r = await fetch(this.url, { method: "PUT", headers: { "Content-Type": "application/json" }, body, keepalive });
      if (!r.ok) throw new Error(String(r.status));
      remove(keys.notesFallback(this.run));
      this.set({ mode: "file", saving: false });
    } catch {
      write(keys.notesFallback(this.run), doc);
      this.set({ mode: "browser", saving: false });
    }
  }
}

const stores = new Map<string, NotesStore>();
const storeFor = (run: string) => {
  let s = stores.get(run);
  if (!s) stores.set(run, (s = new NotesStore(run)));
  return s;
};

if (typeof window !== "undefined")
  window.addEventListener("pagehide", () => stores.forEach((s) => s.flush()));

export function useNotes(run: string) {
  const store = storeFor(run);
  const state = useSyncExternalStore(store.subscribe, () => store.state);
  const update = useCallback((sid: string, patch: Partial<Omit<ScreenNote, "updated">>) => store.update(sid, patch), [store]);
  const triage = useCallback((key: string, patch: TriagePatch) => store.triage(key, patch), [store]);
  const actions = useMemo(
    () => ({
      addComment: store.addComment.bind(store),
      updateComment: store.updateComment.bind(store),
      replyComment: store.replyComment.bind(store),
      deleteComment: store.deleteComment.bind(store),
      restoreComment: store.restoreComment.bind(store),
      edit: store.edit.bind(store),
      undoEdit: store.undoEdit.bind(store),
      canUndo: store.canUndo.bind(store),
    }),
    [store],
  );
  return { ...state, update, triage, ...actions };
}

function mergeNewest<T extends { updated: string }>(a: Record<string, T> = {}, b: Record<string, T> = {}): Record<string, T> {
  const out = { ...a };
  for (const [sid, n] of Object.entries(b)) if (!out[sid] || (n.updated ?? "") > (out[sid].updated ?? "")) out[sid] = n;
  return out;
}

export function notesStatus(mode: NotesMode, saving: boolean, run: string): string {
  if (mode === "loading") return "Loading notes…";
  if (saving) return "Saving…";
  if (mode === "file") return `Saved to runs/${run}/notes.json`;
  return "Saved in this browser only. This server is read-only; run `appscreenmap serve` to save to disk.";
}
