import { useCallback, useEffect, useState } from "react";

// Browser-local viewer state: preferences and map layouts, plus a fallback copy of notes when the server is
// read-only (see notes.ts). Crawl data never goes here: it lives in runs/ on disk and is far too big for
// localStorage (~5 MB, no images).
// Every access is guarded: private windows, blocked site data, or a full quota just mean nothing is remembered.

const PREFIX = "appscreenmap:v1:";
const SAME_TAB_EVENT = "appscreenmap-storage";

export const keys = {
  mapPrefs: "prefs:map",
  screensPrefs: "prefs:screens",
  detailPrefs: "prefs:detail",
  a11yPrefs: "prefs:a11y",
  positions: (run: string, dir: string) => `run:${run}:positions:${dir}`,
  notesFallback: (run: string) => `run:${run}:notes`,
};

export function read<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(PREFIX + key);
    return raw == null ? fallback : (JSON.parse(raw) as T);
  } catch {
    return fallback;
  }
}

export function write<T>(key: string, value: T): boolean {
  try {
    localStorage.setItem(PREFIX + key, JSON.stringify(value));
  } catch {
    return false; // quota exceeded or storage unavailable
  }
  window.dispatchEvent(new CustomEvent(SAME_TAB_EVENT, { detail: key }));
  return true;
}

export function remove(key: string): void {
  try {
    localStorage.removeItem(PREFIX + key);
  } catch {
    return;
  }
  window.dispatchEvent(new CustomEvent(SAME_TAB_EVENT, { detail: key }));
}

/** All keys this viewer owns, without the prefix. */
export function listKeys(): string[] {
  try {
    return Object.keys(localStorage)
      .filter((k) => k.startsWith(PREFIX))
      .map((k) => k.slice(PREFIX.length));
  } catch {
    return [];
  }
}

/** Approximate bytes used by this viewer (UTF-16, so 2 bytes per char). */
export function usage(): number {
  try {
    return listKeys().reduce((n, k) => n + 2 * (k.length + PREFIX.length + (localStorage.getItem(PREFIX + k)?.length ?? 0)), 0);
  } catch {
    return 0;
  }
}

/** Remove preferences and layouts. Notes waiting to be synced to disk (browser fallback) are kept. */
export function clearAll(): void {
  for (const k of listKeys()) if (!/^run:.*:notes$/.test(k)) remove(k);
}

/**
 * useState backed by localStorage. Stays in sync across components in this tab and across other tabs.
 * Values are merged over `fallback` when both are plain objects, so new preference fields get their defaults.
 */
export function useStored<T>(key: string, fallback: T): [T, (v: T | ((prev: T) => T)) => void] {
  const load = useCallback(() => {
    const v = read<T>(key, fallback);
    return isPlainObject(fallback) && isPlainObject(v) ? ({ ...fallback, ...v } as T) : v;
    // eslint-disable-next-line react-hooks/exhaustive-deps -- fallback is a default, not a dependency
  }, [key]);

  const [value, setValue] = useState<T>(load);

  useEffect(() => {
    setValue(load());
    const onSameTab = (e: Event) => (e as CustomEvent<string>).detail === key && setValue(load());
    const onOtherTab = (e: StorageEvent) => (e.key === null || e.key === PREFIX + key) && setValue(load());
    window.addEventListener(SAME_TAB_EVENT, onSameTab);
    window.addEventListener("storage", onOtherTab);
    return () => {
      window.removeEventListener(SAME_TAB_EVENT, onSameTab);
      window.removeEventListener("storage", onOtherTab);
    };
  }, [key, load]);

  const set = useCallback(
    (v: T | ((prev: T) => T)) => {
      const next = typeof v === "function" ? (v as (p: T) => T)(load()) : v;
      setValue(next);
      write(key, next);
    },
    [key, load],
  );

  return [value, set];
}

const isPlainObject = (v: unknown): v is Record<string, unknown> => !!v && typeof v === "object" && !Array.isArray(v);
