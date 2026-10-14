import { useCallback, useSyncExternalStore } from "react";
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

interface Doc {
  notes: RunNotes;
  a11y: RunTriage;
}

/** file: saved in runs/<run>/notes.json · browser: server is read-only, kept in localStorage */
export type NotesMode = "loading" | "file" | "browser";

interface State extends Doc {
  mode: NotesMode;
  saving: boolean;
}

const SAVE_DELAY_MS = 500;

class NotesStore {
  state: State = { notes: {}, a11y: {}, mode: "loading", saving: false };
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
    const hasPending = Object.keys(pending.notes ?? {}).length + Object.keys(pending.a11y ?? {}).length > 0;
    this.set({
      notes: mergeNewest(fromFile.notes ?? {}, pending.notes ?? {}),
      a11y: mergeNewest(fromFile.a11y ?? {}, pending.a11y ?? {}),
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
    const doc: Doc = { notes: this.state.notes, a11y: this.state.a11y };
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
  return { ...state, update, triage };
}

function mergeNewest<T extends { updated: string }>(a: Record<string, T>, b: Record<string, T>): Record<string, T> {
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
