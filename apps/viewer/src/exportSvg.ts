// Draw the Map view as one SVG file: the same positions, links and labels as on screen, with full-size
// screenshots embedded, so it opens in any browser and imports into Figma. Plain attributes and drawn arrowheads
// only (no CSS, no markers): design tools import those unevenly.
import { getBezierPath, getSmoothStepPath, Position } from "@xyflow/react";
import { runFile } from "./api";
import type { Screen } from "./types";

export interface Card {
  id: string;
  title: string;
  kind: Screen["kind"];
  x: number;
  y: number;
  w: number;
  h: number; // whole card, header included
  img: number; // screenshot height
  data: string | null; // screenshot as a data URI
  sub?: string; // storyboard: how the screen was reached
  star?: boolean;
}
export interface Link {
  from: string;
  to: string;
  label?: string;
  discovery: boolean;
}
export interface Head {
  title: string;
  subtitle: string;
}
export interface StoryLane {
  title: string;
  label: string;
  cards: Omit<Card, "x" | "y">[];
}

const THEME = { bg: "#ffffff", card: "#f6f7f9", line: "#c9ced6", text: "#1a1d23", dim: "#646b78", accent: "#0a62c9", edge: "#8a92a0", faint: "#b4bac4" };
const FONT = "Geist, Inter, Helvetica, Arial, sans-serif";
const MONO = "Geist Mono, Menlo, Consolas, monospace";
// Font sizes mirror the --text-* tokens in packages/design-tokens/tokens.css (an SVG file cannot use CSS variables).
const TEXT = { "2xs": 8, xs: 11, sm: 12, lg: 16, "2xl": 26 };
export const HDR_H = 14;
const MARGIN = 80;
const HEAD_H = 70;

const esc = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
const slug = (s: string) => s.replace(/[^A-Za-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 40);
const clip = (s: string, max: number) => (s.length > max ? s.slice(0, Math.max(1, max - 1)) + "…" : s);

function arrowHead(x: number, y: number, dx: number, dy: number, color: string, size = 9): string {
  const len = Math.hypot(dx, dy) || 1;
  const [ux, uy] = [dx / len, dy / len];
  const [bx, by] = [x - ux * size, y - uy * size];
  const [px, py] = [(-uy * size) / 2.2, (ux * size) / 2.2];
  return `<path d="M${x.toFixed(1)} ${y.toFixed(1)} L${(bx + px).toFixed(1)} ${(by + py).toFixed(1)} L${(bx - px).toFixed(1)} ${(by - py).toFixed(1)} Z" fill="${color}"/>`;
}

function card(c: Card, badge: string, withHeader: boolean): string {
  const ext = c.kind !== "app";
  const top = withHeader ? HDR_H : 0;
  const parts = [`<g id="${esc(`${c.id}-${slug(c.title)}`.replace(/-$/, ""))}">`];
  parts.push(
    `<rect x="${c.x}" y="${c.y}" width="${c.w}" height="${c.h}" rx="10" fill="${THEME.card}" stroke="${THEME.line}" stroke-width="1.2"${ext ? ' stroke-dasharray="6 5"' : ""}/>`,
  );
  if (withHeader) {
    const chars = Math.max(6, Math.floor((c.w - 40) / 4.9));
    parts.push(
      `<text x="${c.x + 8}" y="${c.y + 11}" font-family="${esc(FONT)}" font-size="${TEXT["2xs"]}" font-weight="600" fill="${THEME.text}">${esc(clip(c.star ? `★ ${c.title}` : c.title, chars))}</text>`,
      `<text x="${c.x + c.w - 8}" y="${c.y + 11}" text-anchor="end" font-family="${esc(MONO)}" font-size="${TEXT["2xs"]}" fill="${THEME.accent}">${esc(badge)}</text>`,
    );
  }
  // Flow cards: the 1.5px border sits outside the header and the screenshot, as in the viewer.
  const [ix, iy, iw] = withHeader ? [c.x + 1.5, c.y + 1.5 + top, c.w - 3] : [c.x + 8, c.y + 8, c.w - 16];
  if (c.data) {
    parts.push(
      `<clipPath id="clip-${esc(c.id)}"><rect x="${ix}" y="${iy}" width="${iw}" height="${c.img}" rx="${withHeader ? 0 : 6}"/></clipPath>`,
      `<image x="${ix}" y="${iy}" width="${iw}" height="${c.img}" preserveAspectRatio="xMidYMin slice" clip-path="url(#clip-${esc(c.id)})" xlink:href="${c.data}"/>`,
    );
  } else {
    parts.push(
      `<rect x="${ix}" y="${iy}" width="${iw}" height="${c.img}" fill="none" stroke="${THEME.line}" stroke-dasharray="4 4"/>`,
      `<text x="${ix + iw / 2}" y="${iy + c.img / 2}" text-anchor="middle" font-family="${esc(FONT)}" font-size="${TEXT.xs}" fill="${THEME.dim}">${ext ? "left the app" : "no screenshot"}</text>`,
    );
  }
  parts.push("</g>");
  return parts.join("");
}

function frame(head: Head, width: number, height: number, body: string): string {
  return [
    `<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">`,
    `<title>${esc(head.title)}</title>`,
    `<rect width="${width}" height="${height}" fill="${THEME.bg}"/>`,
    `<text x="${MARGIN}" y="${MARGIN - 8}" font-family="${esc(FONT)}" font-size="${TEXT["2xl"]}" font-weight="600" fill="${THEME.text}">${esc(head.title)}</text>`,
    `<text x="${MARGIN}" y="${MARGIN + 18}" font-family="${esc(MONO)}" font-size="${TEXT.sm}" fill="${THEME.dim}">${esc(head.subtitle)}</text>`,
    body,
    "</svg>\n",
  ].join("\n");
}

/** Tree or Graph: the cards exactly where the viewer has them, and the links it draws. */
export function flowSvg(cards: Card[], links: Link[], dir: "LR" | "TB", variant: "tree" | "graph", head: Head): string {
  if (!cards.length) throw new Error("This run has no screens to draw.");
  const minX = Math.min(...cards.map((c) => c.x));
  const minY = Math.min(...cards.map((c) => c.y));
  const placed = cards.map((c) => ({ ...c, x: Math.round(c.x - minX + MARGIN), y: Math.round(c.y - minY + MARGIN + HEAD_H) }));
  const byId = new Map(placed.map((c) => [c.id, c]));
  const [sp, tp] = dir === "LR" ? [Position.Right, Position.Left] : [Position.Bottom, Position.Top];
  const edges = links
    .map((l) => {
      const a = byId.get(l.from);
      const b = byId.get(l.to);
      if (!a || !b) return "";
      const [sx, sy] = dir === "LR" ? [a.x + a.w, a.y + a.h / 2] : [a.x + a.w / 2, a.y + a.h];
      const [tx, ty] = dir === "LR" ? [b.x, b.y + b.h / 2] : [b.x + b.w / 2, b.y];
      const args = { sourceX: sx, sourceY: sy, sourcePosition: sp, targetX: tx, targetY: ty, targetPosition: tp };
      const [d, lx, ly] = variant === "tree" ? getSmoothStepPath({ ...args, borderRadius: 12 }) : getBezierPath(args);
      const color = l.discovery ? THEME.edge : THEME.faint;
      let out = `<path d="${d}" fill="none" stroke="${color}" stroke-width="${l.discovery ? 1.6 : 1.1}"${l.discovery ? "" : ' stroke-dasharray="4 4"'}/>`;
      out += dir === "LR" ? arrowHead(tx, ty, 1, 0, color) : arrowHead(tx, ty, 0, 1, color);
      if (l.label) {
        const text = clip(l.label, 28);
        const w = text.length * 6.2 + 12;
        out += `<rect x="${(lx - w / 2).toFixed(1)}" y="${(ly - 10).toFixed(1)}" width="${w.toFixed(1)}" height="20" rx="5" fill="${THEME.bg}" stroke="${THEME.line}"/>`;
        out += `<text x="${lx.toFixed(1)}" y="${(ly + 4).toFixed(1)}" text-anchor="middle" font-family="${esc(FONT)}" font-size="${TEXT.xs}" fill="${THEME.dim}">${esc(text)}</text>`;
      }
      return out;
    })
    .join("");
  const width = Math.ceil(Math.max(...placed.map((c) => c.x + c.w)) + MARGIN);
  const height = Math.ceil(Math.max(...placed.map((c) => c.y + c.h)) + MARGIN);
  const body = `<g id="links">${edges}</g><g id="screens">${placed.map((c) => card(c, c.kind === "app" ? c.id : "ext", true)).join("")}</g>`;
  return frame(head, width, height, body);
}

/** Storyboard: one band per app section, cards in rows, no lines. */
export function storySvg(lanes: StoryLane[], head: Head, rowWidth = 1500): string {
  if (!lanes.length) throw new Error("This run has no screens to draw.");
  let y = MARGIN + HEAD_H;
  let maxX = rowWidth;
  const parts: string[] = [];
  for (const lane of lanes) {
    parts.push(
      `<text x="${MARGIN}" y="${y + 16}" font-family="${esc(FONT)}" font-size="${TEXT.lg}" font-weight="600" fill="${THEME.text}">${esc(lane.title)}</text>`,
      `<text x="${MARGIN + 12 + lane.title.length * 8.6}" y="${y + 16}" font-family="${esc(MONO)}" font-size="${TEXT.xs}" fill="${THEME.dim}">${esc(`${lane.label} · ${lane.cards.length} screens`)}</text>`,
    );
    y += 34;
    let x = MARGIN;
    let rowH = 0;
    for (const c of lane.cards) {
      const h = c.img + 16 + 46; // image, padding, two text lines
      if (x > MARGIN && x + c.w > MARGIN + rowWidth) {
        x = MARGIN;
        y += rowH + 24;
        rowH = 0;
      }
      const placed: Card = { ...c, x, y, h };
      parts.push(card(placed, c.id, false));
      const chars = Math.max(8, Math.floor(c.w / 6.4));
      parts.push(
        `<text x="${x + 8}" y="${y + 16 + c.img + 16}" font-family="${esc(FONT)}" font-size="${TEXT.sm}" font-weight="600" fill="${THEME.text}">${esc(clip(c.star ? `★ ${c.title}` : c.title, chars))}</text>`,
        `<text x="${x + 8}" y="${y + 16 + c.img + 33}" font-family="${esc(MONO)}" font-size="${TEXT.xs}" fill="${THEME.dim}">${esc(clip(`${c.id}${c.sub ? " " + c.sub : ""}`, chars + 2))}</text>`,
      );
      x += c.w + 24;
      maxX = Math.max(maxX, x - 24 - MARGIN);
      rowH = Math.max(rowH, h);
    }
    y += rowH + 56;
  }
  return frame(head, Math.ceil(maxX + 2 * MARGIN), Math.ceil(y), `<g id="screens">${parts.join("")}</g>`);
}

async function toDataUri(url: string): Promise<string | null> {
  try {
    const r = await fetch(url, { cache: "no-store" });
    if (!r.ok) return null;
    const blob = await r.blob();
    return await new Promise<string | null>((resolve) => {
      const fr = new FileReader();
      fr.onload = () => resolve(typeof fr.result === "string" ? fr.result : null);
      fr.onerror = () => resolve(null);
      fr.readAsDataURL(blob);
    });
  } catch {
    return null;
  }
}

/** Full-size screenshots (the small thumbnail if the full one is missing), a few at a time. */
export async function loadShots(run: string, screens: Screen[]): Promise<Map<string, string>> {
  const out = new Map<string, string>();
  const todo = screens.filter((s) => s.kind === "app" && (s.screenshot || s.thumb));
  let next = 0;
  const worker = async () => {
    while (next < todo.length) {
      const s = todo[next++];
      const data = (s.screenshot && (await toDataUri(runFile(run, s.screenshot)))) || (s.thumb && (await toDataUri(runFile(run, s.thumb))));
      if (data) out.set(s.id, data);
    }
  };
  await Promise.all(Array.from({ length: 4 }, worker));
  return out;
}

export function downloadText(name: string, text: string, type = "image/svg+xml") {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
