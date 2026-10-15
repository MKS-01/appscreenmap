// Ratchet for typography: counts raw (non-token) type values in the viewer CSS and fails when the count rises.
//   bun .claude/skills/design-system/scripts/type-guard.ts            check against type-baseline.json
//   bun .claude/skills/design-system/scripts/type-guard.ts --update   write the current counts as the new baseline
//   bun .claude/skills/design-system/scripts/type-guard.ts --list     also print every raw value with its line
// Tokens live in packages/design-tokens/tokens.css; new code uses var(--text-*), var(--weight-*), var(--leading-*), var(--tracking-*).

const root = new URL("../../../../", import.meta.url);
const files = ["apps/viewer/src/styles.css"];
const props = ["font-size", "font-weight", "line-height", "letter-spacing"] as const;
const baselineFile = new URL("type-baseline.json", import.meta.url);

const args = Bun.argv.slice(2);
const list = args.includes("--list");
const counts: Record<string, Record<string, number>> = {};
const rawLines: string[] = [];

for (const f of files) {
  const text = await Bun.file(new URL(f, root)).text();
  counts[f] = Object.fromEntries(props.map((p) => [p, 0]));
  text.split("\n").forEach((line, i) => {
    for (const p of props) {
      const m = new RegExp(`(?:^|[\\s{;])${p}:\\s*([^;}]+)`).exec(line);
      if (!m) continue;
      const v = m[1].trim();
      if (v.startsWith("var(") || v === "inherit" || v === "normal" || v === "0") continue; // a token, or no value of its own
      counts[f][p]++;
      if (list) rawLines.push(`${f}:${i + 1}  ${p}: ${v}`);
    }
  });
}
if (list) console.log(rawLines.join("\n"));

if (args.includes("--update")) {
  await Bun.write(baselineFile, JSON.stringify(counts, null, 2) + "\n");
  console.log("baseline updated:", JSON.stringify(counts));
  process.exit(0);
}

const base = JSON.parse(await Bun.file(baselineFile).text()) as typeof counts;
let bad = 0;
for (const f of files) {
  for (const p of props) {
    const [now, was] = [counts[f][p], base[f]?.[p] ?? 0];
    const mark = now > was ? "RAISED" : now < was ? "lower (run --update)" : "ok";
    console.log(`${f}  ${p.padEnd(14)} raw ${String(now).padStart(3)}  baseline ${String(was).padStart(3)}  ${mark}`);
    if (now > was) bad++;
  }
}
if (bad) console.error("\nUse the type tokens (var(--text-*), --weight-*, --leading-*, --tracking-*) instead of raw values. See the design-system skill.");
process.exit(bad ? 1 : 0);
