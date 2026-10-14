// Checks the WCAG contrast of every text/status token against every surface in packages/design-tokens/tokens.css.
// Run after changing any colour:   bun .claude/skills/design-system/scripts/contrast.ts
// Exit 1 when a required pair falls below its minimum.

const file = new URL("../../../../packages/design-tokens/tokens.css", import.meta.url);
const css = await Bun.file(file).text();

const raw = new Map<string, string>();
for (const m of css.matchAll(/--([a-z0-9-]+):\s*([^;]+);/g)) raw.set(m[1], m[2].trim());

function resolve(name: string, seen = new Set<string>()): string | null {
  const v = raw.get(name);
  if (!v || seen.has(name)) return null;
  const ref = /^var\(--([a-z0-9-]+)\)$/.exec(v);
  if (ref) return resolve(ref[1], new Set([...seen, name]));
  return /^#[0-9a-f]{6}$/i.test(v) ? v : null;
}

const lum = (hex: string) => {
  const c = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((x) => (x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4));
  return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
};
const ratio = (a: string, b: string) => {
  const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p);
  return (x + 0.05) / (y + 0.05);
};

const surfaces = ["bg", "panel", "panel-2"];
// [token, minimum]: 4.5 for text; 3 for status marks and focus rings that always come with a word.
const checks: [string, number][] = [
  ["text", 4.5],
  ["dim", 4.5],
  ["faint", 4.5],
  ["accent", 4.5],
  ["accent-hi", 4.5],
  ["good", 4.5],
  ["warn", 4.5],
  ["bad", 4.5],
  ["info", 4.5],
  ["st-failed", 3],
  ["st-skipped", 3],
];

let fails = 0;
const rows: Record<string, string | number>[] = [];
for (const [tok, min] of checks) {
  const fg = resolve(tok);
  if (!fg) {
    console.error(`--${tok}: not a hex colour after resolving var() chains`);
    fails++;
    continue;
  }
  const row: Record<string, string | number> = { token: `--${tok}`, value: fg, min };
  for (const s of surfaces) {
    const r = ratio(fg, resolve(s)!);
    row[s] = `${r.toFixed(1)}${r < min ? " ✗" : ""}`;
    if (r < min) fails++;
  }
  rows.push(row);
}
const onAccent = ratio(resolve("on-accent")!, resolve("accent")!);
rows.push({ token: "--on-accent on --accent", value: resolve("on-accent")!, min: 4.5, bg: `${onAccent.toFixed(1)}${onAccent < 4.5 ? " ✗" : ""}` });
if (onAccent < 4.5) fails++;

console.table(rows);
console.log(fails ? `${fails} pair(s) below minimum` : "All pairs pass.");
process.exit(fails ? 1 : 0);
