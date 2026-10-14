// Terminal colours, read from the design tokens (packages/design-tokens/tokens.css) so the CLI and the dashboard share
// one palette (Ghost dark × Xcode blue). Bun inlines the file at build time, so the compiled binary carries it.
import css from "@appscreenmap/design-tokens/tokens.css" with { type: "text" };

/** `--name: value;` declarations, comments dropped. */
export function parseTokens(source: string): Map<string, string> {
  const out = new Map<string, string>();
  for (const m of source.replace(/\/\*[\s\S]*?\*\//g, "").matchAll(/--([\w-]+)\s*:\s*([^;]+);/g)) {
    out.set(m[1]!, m[2]!.trim());
  }
  return out;
}

/** A token's final value, following `var(--other)` references. */
export function resolveToken(tokens: Map<string, string>, name: string, depth = 0): string {
  const value = tokens.get(name);
  if (value === undefined) throw new Error(`design token --${name} not found`);
  const ref = value.match(/^var\(--([\w-]+)\)$/);
  if (ref && depth < 10) return resolveToken(tokens, ref[1]!, depth + 1);
  return value;
}

const tokens = parseTokens(css);
const token = (name: string) => resolveToken(tokens, name);

// Same rules as the dashboard: blue only for what you can act on (keys, commands, the selection); status colours
// always come with a word or glyph.
export const C = {
  text: token("text"),
  dim: token("dim"),
  faint: token("faint"),
  accent: token("accent"),
  good: token("good"),
  warn: token("warn"),
  bad: token("bad"),
  line: token("line-hi"),
} as const;
