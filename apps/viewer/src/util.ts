import type { AppMapData, ElementStatus, Screen } from "./types";

export const STATUSES: ElementStatus[] = ["done", "pending", "blocked", "skipped", "failed", "unreachable"];

export const STATUS_HELP: Record<ElementStatus, string> = {
  done: "tapped during the crawl",
  pending: "found but not tried (budget ran out)",
  blocked: "matches blocked_text — never tapped",
  skipped: "list pattern cap — similar items explored instead",
  failed: "couldn't be found when the crawler went to tap it",
  unreachable: "screen couldn't be navigated back to",
};

export const statusColor = (s: string) => `var(--st-${s})`;

export const shortActivity = (a: string | null | undefined) => (a ? a.replace(/^.*\./, "") : "—");

export function fmtDuration(s: number | null | undefined): string {
  if (s == null) return "—";
  if (s < 60) return `${Math.round(s)}s`;
  const m = Math.floor(s / 60);
  return m < 60 ? `${m}m ${Math.round(s % 60)}s` : `${Math.floor(m / 60)}h ${m % 60}m`;
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export const plural = (n: number, w: string) => `${n} ${w}${n === 1 ? "" : "s"}`;

/** The screen the crawl launched into: depth 0, first seen. */
export function rootScreen(m: AppMapData): Screen | undefined {
  return m.screens.filter((s) => s.kind === "app").sort((a, b) => a.depth - b.depth || a.first_step - b.first_step)[0];
}

/** Ordered list of screen ids along a screen's reach path, ending at the screen itself. */
export function pathScreens(s: Screen): string[] {
  return [...s.reach_path.map((p) => p.screen), s.id];
}

export const screenMap = (m: AppMapData) => new Map(m.screens.map((s) => [s.id, s]));

/**
 * Display box for a screenshot that keeps the device's real aspect ratio (phone, tablet, landscape, foldable).
 * Area stays roughly constant, so a tall phone gets a narrow card and a landscape tablet a wide, short one.
 */
export function shotBox(
  s: { width?: number; height?: number } | undefined,
  area = 32000,
  min = 96,
  max = 280,
): { w: number; h: number; ratio: number } {
  const W = s?.width || 1080;
  const H = s?.height || 2400;
  const ratio = H / W;
  const w = Math.round(Math.min(max, Math.max(min, Math.sqrt(area / ratio))));
  return { w, h: Math.round(w * ratio), ratio };
}
