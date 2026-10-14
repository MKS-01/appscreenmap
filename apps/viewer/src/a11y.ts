import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { runFile } from "./api";
import type { AppMapData, Screen } from "./types";

// Accessibility review: checks modelled on Android Accessibility Scanner, run in the browser from what the crawl
// already saved — each screen's uiautomator hierarchy (screens/*.xml) and screenshot. Nothing app-specific.
// These are automated hints, not a WCAG audit: they find likely problems for a person to triage.

export type Severity = "error" | "warning" | "info";
export type RuleId = "label-missing" | "field-unlabeled" | "field-desc" | "touch-target" | "contrast" | "duplicate-label" | "redundant-desc";

export const RULES: Record<RuleId, { title: string; severity: Severity; why: string; fix: string }> = {
  "label-missing": {
    title: "Missing label",
    severity: "error",
    why: "A tappable item has no text or content description, so TalkBack can only announce its type (e.g. “Button”).",
    fix: "Set android:contentDescription (or Modifier.semantics { contentDescription = … } in Compose).",
  },
  "field-unlabeled": {
    title: "Unlabeled text field",
    severity: "error",
    why: "An editable field has no hint or label, so screen-reader users don't know what to type.",
    fix: "Give it a hint, or a visible label with android:labelFor pointing at the field.",
  },
  "field-desc": {
    title: "Text field uses contentDescription",
    severity: "warning",
    why: "A contentDescription on an EditText replaces what TalkBack reads for the typed text.",
    fix: "Remove the contentDescription; use a hint or labelFor instead.",
  },
  "touch-target": {
    title: "Small touch target",
    severity: "warning",
    why: "Below Android's 48×48 dp guideline: hard to hit for people with motor impairments. (WCAG 2.2 AA 2.5.8 is 24×24 dp with a spacing exception; the crawler's WCAG report checks that.)",
    fix: "Increase the view's size or padding, or use a TouchDelegate / minimumInteractiveComponentSize.",
  },
  contrast: {
    title: "Low text contrast",
    severity: "warning",
    why: "WCAG 1.4.3 asks for 4.5:1 for normal text and 3:1 for large text (≥18pt ≈ 24 dp, or ≥14pt bold ≈ 18.7 dp). Estimated from screenshot pixels.",
    fix: "Darken or lighten the text or background colour until the ratio passes.",
  },
  "duplicate-label": {
    title: "Duplicate description",
    severity: "info",
    why: "Several controls on one screen announce the same description, so they're indistinguishable by ear.",
    fix: "Make each description specific, e.g. “Delete alarm 7:00 AM” instead of “Delete”.",
  },
  "redundant-desc": {
    title: "Redundant wording in description",
    severity: "info",
    why: "TalkBack already announces the role; words like “button” or “image” in the description are read twice.",
    fix: "Drop the role word from the description.",
  },
};

// ── platform ────────────────────────────────────────────────────────────────

export type Platform = "android" | "ios";
export const platformOf = (map: AppMapData): Platform => (map.run.device.platform === "ios" ? "ios" : "android");
/** The crawled platform of the run being viewed; set once in the run shell. */
export const PlatformCtx = createContext<Platform>("android");

/** Minimum touch target in dp/pt: Android's Material guideline is 48 dp, Apple's HIG is 44 pt. */
export const TARGET_MIN: Record<Platform, number> = { android: 48, ios: 44 };

// What reads differently on iOS: the screen reader is VoiceOver, the code is Swift, the guideline is Apple's.
const IOS: Partial<Record<RuleId, { title?: string; why?: string; fix?: string }>> = {
  "label-missing": {
    why: "A tappable item has no accessibility label, so VoiceOver can only announce its role (“Button”).",
    fix: "SwiftUI: .accessibilityLabel(\"Save\"). UIKit: set accessibilityLabel. Icon-only buttons need one.",
  },
  "field-unlabeled": {
    why: "A text field has no label or placeholder, so VoiceOver users don't know what to type.",
    fix: "Give the field a label (TextField(\"Email\", text: …)) or .accessibilityLabel.",
  },
  "field-desc": {
    why: "An accessibilityLabel on a text field can replace what VoiceOver reads for the typed text.",
    fix: "Remove the label override; use the field's own title or placeholder, and accessibilityHint for extra context.",
  },
  "touch-target": {
    why: "Below Apple's 44×44 pt guideline: hard to hit for people with motor impairments. (WCAG 2.2 AA 2.5.8 is 24×24 with a spacing exception; the crawler's WCAG report checks that.)",
    fix: "Add padding or .frame(minWidth: 44, minHeight: 44) with .contentShape(Rectangle()) so the whole area is tappable.",
  },
  "redundant-desc": {
    why: "VoiceOver already announces the trait (“button”, “image”); repeating it in the label reads it twice.",
    fix: "Drop the role word from the accessibility label.",
  },
};

/** The rule catalogue worded for a platform. */
export function rulesFor(platform: Platform): typeof RULES {
  if (platform !== "ios") return RULES;
  return Object.fromEntries(Object.entries(RULES).map(([id, r]) => [id, { ...r, ...IOS[id as RuleId] }])) as typeof RULES;
}
export const useRules = () => rulesFor(useContext(PlatformCtx));

export const SEVERITY_COLOR: Record<Severity, string> = {
  error: "var(--st-blocked)",
  warning: "var(--st-pending)",
  info: "var(--st-unreachable)",
};

export interface A11yIssue {
  key: string; // stable across reloads; used to store triage decisions
  screen: string;
  rule: RuleId;
  severity: Severity;
  label: string; // what the element is, for humans
  detail: string;
  bounds: [number, number, number, number];
  rid: string;
  cls: string;
}

export type TriageStatus = "open" | "confirmed" | "wontfix" | "false_positive";
export const TRIAGE_LABEL: Record<TriageStatus, string> = {
  open: "Not reviewed",
  confirmed: "Needs fix",
  wontfix: "Won't fix",
  false_positive: "False positive",
};

// ── hierarchy ───────────────────────────────────────────────────────────────

interface HNode {
  cls: string;
  rid: string;
  pkg: string;
  text: string;
  desc: string;
  hint: string;
  clickable: boolean;
  focusable: boolean;
  enabled: boolean;
  scrollable: boolean;
  password: boolean;
  bounds: [number, number, number, number];
  parent: HNode | null;
  children: HNode[];
}

const BOUNDS_RE = /\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]/;

function parseHierarchy(xml: string): HNode[] {
  const doc = new DOMParser().parseFromString(xml, "text/xml");
  const out: HNode[] = [];
  const walk = (el: Element, parent: HNode | null) => {
    const a = (k: string) => el.getAttribute(k) ?? "";
    const m = BOUNDS_RE.exec(a("bounds"));
    const node: HNode = {
      cls: a("class"),
      rid: a("resource-id"),
      pkg: a("package"),
      text: a("text").trim(),
      desc: a("content-desc").trim(),
      hint: a("hint").trim(),
      clickable: a("clickable") === "true" || a("long-clickable") === "true",
      focusable: a("focusable") === "true",
      enabled: a("enabled") !== "false",
      scrollable: a("scrollable") === "true",
      password: a("password") === "true",
      bounds: m ? [+m[1], +m[2], +m[3], +m[4]] : [0, 0, 0, 0],
      parent,
      children: [],
    };
    parent?.children.push(node);
    out.push(node);
    for (const c of Array.from(el.children)) if (c.tagName === "node") walk(c, node);
  };
  for (const c of Array.from(doc.documentElement?.children ?? [])) if (c.tagName === "node") walk(c, null);
  return out;
}

const isEditable = (n: HNode) => /EditText|TextField|AutoCompleteTextView/.test(n.cls);
const w = (n: HNode) => n.bounds[2] - n.bounds[0];
const h = (n: HNode) => n.bounds[3] - n.bounds[1];
const shortCls = (c: string) => c.replace(/^.*\./, "");
const ancestors = function* (n: HNode) {
  for (let p = n.parent; p; p = p.parent) yield p;
};

/** What TalkBack would announce: own text/description, else the text of its non-actionable descendants. */
function accessibleName(n: HNode): string {
  if (n.desc) return n.desc;
  if (n.text) return n.text;
  const parts: string[] = [];
  const visit = (c: HNode) => {
    if (c.clickable && c !== n) return; // a separately focusable child is announced on its own
    if (c.desc || c.text) parts.push(c.desc || c.text);
    else c.children.forEach(visit);
  };
  n.children.forEach(visit);
  return parts.join(" ").trim();
}

/** Pixels per dp. Exact when the crawler records device.density (dpi); otherwise estimated from screen width. */
export function densityFor(map: AppMapData): { scale: number; exact: boolean } {
  const dpi = Number((map.run.device as Record<string, unknown>).density);
  if (dpi > 0) return { scale: dpi / 160, exact: true };
  const width = map.run.device.width || 1080;
  return { scale: width / 411, exact: false }; // most phones are ~411 dp wide
}

// ── rules ───────────────────────────────────────────────────────────────────

function structuralIssues(screen: Screen, nodes: HNode[], dp: number, platform: Platform): A11yIssue[] {
  const min = TARGET_MIN[platform];
  const unit = platform === "ios" ? "pt" : "dp";
  const W = screen.width || 1080;
  const H = screen.height || 2400;
  const issues: A11yIssue[] = [];
  const add = (rule: RuleId, n: HNode, label: string, detail: string, severity = RULES[rule].severity) =>
    issues.push({
      key: `${screen.id}::${rule}::${n.rid || shortCls(n.cls)}::${label}::${n.bounds[0]},${n.bounds[1]}`,
      screen: screen.id,
      rule,
      severity,
      label,
      detail,
      bounds: n.bounds,
      rid: n.rid,
      cls: n.cls,
    });

  const own = (n: HNode) => !screen.package || !n.pkg || n.pkg === screen.package;
  const onScreen = (n: HNode) => w(n) > 0 && h(n) > 0 && n.bounds[2] > 0 && n.bounds[3] > 0 && n.bounds[0] < W && n.bounds[1] < H;
  const backdrop = (n: HNode) => w(n) * h(n) >= 0.9 * W * H;
  const name = (n: HNode) => accessibleName(n) || n.rid.replace(/^.*\//, "") || shortCls(n.cls);

  const descGroups = new Map<string, HNode[]>();

  for (const n of nodes) {
    if (!own(n) || !onScreen(n)) continue;

    if (isEditable(n)) {
      if (n.desc) add("field-desc", n, n.desc, `contentDescription “${n.desc}” on ${shortCls(n.cls)}`);
      else if (!n.hint && !n.text) add("field-unlabeled", n, n.rid.replace(/^.*\//, "") || "text field", "No hint, text or label");
      continue;
    }

    if (!n.clickable || backdrop(n)) continue;

    if (!accessibleName(n)) add("label-missing", n, n.rid.replace(/^.*\//, "") || shortCls(n.cls), `Tappable ${shortCls(n.cls)} with nothing to announce`);

    // Touch target: skip views clipped by a scroll container edge, and views inside a big enough tappable parent.
    const wdp = w(n) / dp;
    const hdp = h(n) / dp;
    if (n.enabled && (wdp < min - 0.5 || hdp < min - 0.5)) {
      const clipped = [...ancestors(n)].some(
        (a) => a.scrollable && (n.bounds[0] <= a.bounds[0] || n.bounds[1] <= a.bounds[1] || n.bounds[2] >= a.bounds[2] || n.bounds[3] >= a.bounds[3]),
      );
      const coveredByParent = [...ancestors(n)].some((a) => a.clickable && !backdrop(a) && w(a) / dp >= min && h(a) / dp >= min);
      if (!clipped && !coveredByParent) add("touch-target", n, name(n), `${Math.round(wdp)}×${Math.round(hdp)} ${unit} (${platform === "ios" ? "Apple HIG" : "Android guideline"} ${min}×${min})`);
    }

    if (n.desc) {
      if (/\b(button|image|icon|picture|graphic|tap|click)\b/i.test(n.desc)) add("redundant-desc", n, n.desc, `“${n.desc}”`);
      const k = n.desc.toLowerCase();
      descGroups.set(k, [...(descGroups.get(k) ?? []), n]);
    }
  }

  for (const group of descGroups.values())
    if (group.length > 1) add("duplicate-label", group[0], group[0].desc, `${group.length} controls are all announced as “${group[0].desc}”`);

  return issues;
}

// ── contrast (from screenshot pixels) ───────────────────────────────────────

const lin = (c: number) => {
  const s = c / 255;
  return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
};
const luminance = (r: number, g: number, b: number) => 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
export const contrastRatio = (l1: number, l2: number) => (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);

/**
 * Background = the dominant colour. Text = the 90th-percentile most-contrasting pixel among those that clearly
 * differ from the background. Percentiles rather than colour-bin sizes, because thin glyphs in a wide box cover
 * very few pixels and would otherwise lose to borders and dividers.
 */
function sampleContrast(data: Uint8ClampedArray): number | null {
  const total = data.length / 4;
  const bins = new Map<number, number>();
  for (let i = 0; i < data.length; i += 4) {
    const k = ((data[i] >> 4) << 8) | ((data[i + 1] >> 4) << 4) | (data[i + 2] >> 4);
    bins.set(k, (bins.get(k) ?? 0) + 1);
  }
  let bgKey = -1;
  let bgN = 0;
  for (const [k, n] of bins) if (n > bgN) [bgKey, bgN] = [k, n];
  if (bgN < total * 0.3) return null; // busy background (photo, gradient): can't tell reliably

  let r = 0;
  let g = 0;
  let b = 0;
  for (let i = 0; i < data.length; i += 4) {
    if ((((data[i] >> 4) << 8) | ((data[i + 1] >> 4) << 4) | (data[i + 2] >> 4)) !== bgKey) continue;
    r += data[i];
    g += data[i + 1];
    b += data[i + 2];
  }
  const lb = luminance(r / bgN, g / bgN, b / bgN);

  const fg: number[] = [];
  for (let i = 0; i < data.length; i += 4) {
    const ratio = contrastRatio(lb, luminance(data[i], data[i + 1], data[i + 2]));
    if (ratio >= 1.5) fg.push(ratio);
  }
  if (fg.length < Math.max(8, total * 0.002)) return null; // no visible text
  fg.sort((x, y) => y - x);
  return fg[Math.floor(fg.length / 10)];
}

async function contrastIssues(run: string, screen: Screen, nodes: HNode[], dp: number): Promise<A11yIssue[]> {
  if (!screen.screenshot) return [];
  const img = new Image();
  img.src = runFile(run, screen.screenshot);
  await img.decode();
  const canvas = document.createElement("canvas");
  canvas.width = img.naturalWidth;
  canvas.height = img.naturalHeight;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  if (!ctx) return [];
  ctx.drawImage(img, 0, 0);
  const sx = img.naturalWidth / (screen.width || img.naturalWidth);
  const sy = img.naturalHeight / (screen.height || img.naturalHeight);
  const statusBar = 24 * dp; // the system status bar isn't the app's text

  const issues: A11yIssue[] = [];
  for (const n of nodes) {
    if (!n.text || n.password || n.children.some((c) => c.text)) continue;
    if (screen.package && n.pkg && n.pkg !== screen.package) continue;
    const [x1, y1, x2, y2] = n.bounds;
    if (y2 <= statusBar || h(n) / dp < 8 || w(n) / dp < 8) continue;
    // Inset to skip borders and outlines drawn at the view's edges.
    const inset = Math.max(2, Math.floor(0.1 * Math.min((x2 - x1) * sx, (y2 - y1) * sy)));
    const x = Math.max(0, Math.floor(x1 * sx) + inset);
    const y = Math.max(0, Math.floor(y1 * sy) + inset);
    const cw = Math.min(canvas.width - x, Math.floor((x2 - x1) * sx) - 2 * inset);
    const ch = Math.min(canvas.height - y, Math.floor((y2 - y1) * sy) - 2 * inset);
    if (cw < 4 || ch < 4) continue;
    const ratio = sampleContrast(ctx.getImageData(x, y, cw, ch).data);
    if (ratio == null || ratio >= 4.5) continue;
    const label = n.text.length > 60 ? n.text.slice(0, 57) + "…" : n.text;
    issues.push({
      key: `${screen.id}::contrast::${n.rid || shortCls(n.cls)}::${label}::${x1},${y1}`,
      screen: screen.id,
      rule: "contrast",
      severity: ratio < 3 ? "error" : "warning",
      label,
      detail: `≈${ratio.toFixed(1)}:1 ${ratio < 3 ? "(fails even for large text)" : "(OK only for large text)"}`,
      bounds: n.bounds,
      rid: n.rid,
      cls: n.cls,
    });
  }
  return issues;
}

// ── running it ──────────────────────────────────────────────────────────────

const cache = new Map<string, Promise<A11yIssue[]>>();

export function analyzeScreen(run: string, screen: Screen, dp: number, platform: Platform = "android"): Promise<A11yIssue[]> {
  const id = `${run}/${screen.id}/${screen.hierarchy}/${dp}/${platform}`;
  let p = cache.get(id);
  if (!p) {
    p = (async () => {
      if (screen.kind !== "app" || !screen.hierarchy) return [];
      const r = await fetch(runFile(run, screen.hierarchy), { cache: "no-store" });
      if (!r.ok) return [];
      const nodes = parseHierarchy(await r.text());
      const structural = structuralIssues(screen, nodes, dp, platform);
      const contrast = await contrastIssues(run, screen, nodes, dp).catch(() => []);
      return [...structural, ...contrast];
    })();
    p.catch(() => cache.delete(id));
    cache.set(id, p);
  }
  return p;
}

/** Analyze every app screen in a run (a few at a time); results fill in as they finish. */
export function useA11y(run: string, map: AppMapData, only?: string) {
  const { scale } = densityFor(map);
  const platform = platformOf(map);
  const screens = useMemo(() => map.screens.filter((s) => s.kind === "app" && (!only || s.id === only)), [map, only]);
  const [results, setResults] = useState<Record<string, A11yIssue[]>>({});

  useEffect(() => {
    let alive = true;
    const queue = [...screens];
    const worker = async () => {
      for (let s = queue.shift(); s && alive; s = queue.shift()) {
        const issues = await analyzeScreen(run, s, scale, platform).catch(() => [] as A11yIssue[]);
        if (alive) setResults((r) => ({ ...r, [s!.id]: issues }));
      }
    };
    void Promise.all([worker(), worker(), worker()]);
    return () => {
      alive = false;
    };
  }, [run, screens, scale, platform]);

  const issues = useMemo(() => screens.flatMap((s) => results[s.id] ?? []), [screens, results]);
  return { issues, done: screens.filter((s) => results[s.id]).length, total: screens.length };
}
