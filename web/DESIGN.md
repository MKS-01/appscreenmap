# Viewer design system

The rules for every UI change in `web/`. Live reference: open the viewer at **`#/design`**, which renders
these tokens and components from the real CSS. Motion and interaction follow Emil Kowalski's design-engineering
approach (the `emil-design-eng` skill): invisible details done right, motion only with a purpose.

## Principles

1. **Data first.** This is a tool for reading maps, screenshots and findings. Chrome stays quiet: neutral
   surfaces, one accent, colour reserved for meaning (status, severity, selection).
2. **Show the real thing.** Prefer the app's own screenshots and real run data over illustrations. Explanations
   use the latest run when one exists (see How it works).
3. **Every pixel earns its place, both themes.** Light and dark are equal; check both. No hard-coded colours.
4. **Fast beats fancy.** Views people use all day (map, screens, detail, tables) get almost no motion. Rarely
   seen pages (How it works, empty states) may use explanatory motion.
5. **Accessible by default.** Keyboard reachable, visible focus, labelled icons, `prefers-reduced-motion`
   respected. We ship an accessibility reviewer; the viewer must pass its own bar.

## Tokens (`src/tokens.css`)

The only place raw colours, curves and radii are defined. Components use `var(--…)`.

| Group | Tokens | Use |
|---|---|---|
| Surfaces | `--bg`, `--panel`, `--panel-2`, `--border` | Page, cards/bars, insets/code/hover, hairlines |
| Text | `--text`, `--muted`, `--faint` | Primary, secondary, tertiary (ids, hints) |
| Accent | `--accent`, `--accent-soft`, `--accent-text` | Primary action/focus, selected background, links/selected text |
| Status | `--st-done`, `--st-pending`, `--st-blocked`, `--st-skipped`, `--st-failed`, `--st-unreachable` | Element outcomes. Severities reuse them: error = blocked, warning = pending, info = unreachable |
| Elevation | `--shadow`, `--shadow-lg` | Resting cards; popovers, selected map nodes, hover lift |
| Space | `--space-1…7` (4, 8, 12, 16, 24, 32, 52 px) | Gaps and padding |
| Type | `--text-xs…2xl` (11.5, 12.5, 14, 16, 20 px, clamp display) | Font sizes |
| Radius | `--radius-sm` 6, `--radius-md` 10, `--radius-lg` 14, `--radius-pill` | Inputs/rows, cards, stages, chips |
| Motion | `--ease-out`, `--ease-in-out`, `--dur-press` 160ms, `--dur-fast` 150ms, `--dur-ui` 220ms | See Motion |

Older rules still use raw px for space and type. Use the tokens in new code, and migrate a rule when you touch it.
Dark mode overrides tokens only, under `@media (prefers-color-scheme: dark)`. A component never needs its own
dark rule.

## Type

System UI stack; `--mono` for ids (`.sid`), code, commands and aligned numbers (`font-variant-numeric:
tabular-nums` for stats). Scale: display (`.how-title`, `.hero-title`) → `h1` 22/650 → `h2` 16/620 → `h3`
13 uppercase eyebrow → body 14/1.5 → `.small` 12 → `.faint` hints. Sentence case everywhere.

## Layout

- Pages: `.page` (max 1280, 20px gutter, 16 on phones); prose-heavy pages ≤ 1080.
- Shell: top bar (52px) → run tabs → `.main` (the only scroll container). Map view is full-bleed.
- Grids: `auto-fill, minmax(…)`, so they collapse naturally; breakpoints at 900px and 520px only.
- No horizontal page scroll at 390px wide. Long things (`.filmstrip`, tab bars) scroll inside themselves.

## Components (`src/styles.css`, `src/components/`)

| Component | Class / file | Notes |
|---|---|---|
| Card | `.panel` (+ `.panel-pad`) | Border + `--shadow`. Hover tint only if the whole card is a link |
| Button | `.btn`, `.btn.primary` | One primary per view region. Icon + label, never icon-only without `aria-label` |
| Segmented | `.seg` | 2–4 mutually exclusive options; `aria-pressed` on buttons |
| Chip | `.chip`, `button.chip`, `.chip.on` | Filters and patterns. Toggle chips set `aria-pressed` |
| Status badge | `StatusBadge` | Run status; `running` pulses (reduced motion: static) |
| Effect label | `.effect.<effect>` | Outcome of a step: new / known / same / left app / crash |
| Dot | `.dot` + `statusColor()` | Never the only signal: always paired with a text label |
| Stat | `Stat`, `.stats` | Big number + label. Warning values in `--st-blocked` |
| Table | `.tbl`, `tr.hover`, `tr.sel` | Sticky header; row hover syncs with screenshot overlays |
| Tabs | `.tabs` / `.tab` | Run-level navigation; in-panel tabs use the same classes |
| Overlay box | `.ov` (ScreenDetail `Shot`) | Boxes on screenshots; colour = status or severity; focusable when actionable |
| Icon | `components/Icon.tsx` | See Icons |
| Section title | `.sec-title` (How it works) | Icon tile + kicker + h2 + one-line lede |
| Stepper / stage | `.loop-step`, `.loop-stage` | Explanatory walkthroughs only |
| Explorer | `.explorer` | List/detail picker for reference content |
| Mini phone | `.mini-phone` | Screenshot in a device frame for explanations (not for data views) |
| Map node | `.snode` (MapView) | One-line 22px header (title + id) over the **whole** screenshot at the device's aspect (`shotBox`). `.root` green, `.orphan` dashed amber (no recorded path), `.ext` dashed |
| Storyboard | `.story`, `.lane`, `.story-card` | Sections as content-sized panels that wrap; cards show "via <tap>" and a +depth badge |
| Charts | `insights/charts.tsx`: `Bars`, `Columns`, `Split`, `Chart` | See Charts. No chart library |
| Meter | `Meter`, `.meter` | 0–100 score; fill = tone, track = same hue at 16% |
| Audit card | `.audit-card` (Insights) | Whole card is a link; dashed + transparent when the audit hasn't run |
| Sample tag | `SampleTag`, `.sample-tag` | Dashed amber chip on any placeholder data (report, chart, metric or finding) |
| Sub-nav | `.audit-nav` | Underlined link row inside a tab (Insights audits); scrolls sideways on phones |

Reuse before inventing. If a new pattern appears twice, add it here and to `#/design`.

## Map layouts

All three Map variants (Tree, Graph, Storyboard; `mapLayout.ts`) are built on the **discovery tree**: each
screen's parent is the screen it was first reached from. Screens with `origin: "launch"` are extra roots
(start screens); `origin: "unknown"` ones are shown as "no recorded path". Discovery edges are always drawn. Every other transition
is an "extra link": dashed, and shown only for the selected screen unless "All links" is on. Positions depend only
on the tree, so toggling links never moves cards. Edge labels are off by default and appear on the selected path.

## Screenshots

Never crop a screenshot to a fixed shape. Size it with `shotBox(screen, area)` (`util.ts`): the box keeps the
screen's own `width`/`height` ratio, so phones, tablets, foldables and landscape all look right, and a roughly
constant area keeps cards comparable. Use `aspect-ratio: W / H` in CSS for fluid layouts (gallery, storyboard).
The Map's direction defaults to **Auto**: top-down for portrait screens, left-to-right for landscape.

## Colour rules

- Accent means "interactive or selected". Don't use it for decoration beyond the hero/stage glows.
- Status colours mean status. Don't reuse them for categories (use `.token.tk-*` style tints for categories).
- Text on colour: use `color-mix(in srgb, var(--x) 12–14%, transparent)` backgrounds with the full colour as
  text (see `.effect`, `.verdict`). Check contrast ≥ 4.5:1 in both themes.

## Charts

Insights charts follow the `dataviz` skill: pick the form first, colour last.

- **Forms:** `Bars` for ranked items (one row each, value at the tip, optional budget line), `Columns` for ordered
  categories (depth, size class, runs over time; `highlight` greys all but one), `Split` for parts of one whole.
  A single number is a `Stat`, not a chart. Two measures with different scales → small multiples, never two axes.
- **Colour:** one series = `--accent`. Status tones (`good`/`warn`/`bad`/`info` → `--st-done`/`--st-pending`/
  `--st-blocked`/`--st-unreachable`) only when the value really is good or bad, and the chart then shows a legend
  word for each tone. Severities use the same mapping: error = bad, warning = warn, info = info.
- **Marks:** bars ≤ 10–12 px thick with a 4 px rounded data end and a square baseline; 2 px gaps between stacked
  parts; hairline solid axes. Text stays in text tokens, never the data colour.
- **Labels:** every value is printed (tooltips only repeat it), so nothing is hover-only. Long labels ellipsize
  inside their column; values never wrap.
- **Data:** audits describe charts declaratively (`AuditChart` in `insights/types.ts`, `audits/<id>.json` in
  docs/MAP_SCHEMA.md), so a new tool adds charts without viewer code.

## Icons

`components/Icon.tsx`: Lucide-style 24×24 strokes, 1.8 stroke width, `currentColor`. Sizes 13–14 inline with
text, 15–16 in lists, 18–20 in tiles. Decorative by default (`aria-hidden`); pass `label` when the icon is the
only content. To add one, paste the Lucide shape (ISC licence) into `PATHS` and show it on `#/design`. No icon
fonts, no new icon dependency.

## Motion

Decide in this order (from `emil-design-eng`): **should it animate → why → easing → duration**.

| Situation | Rule |
|---|---|
| Used tens of times a day (tabs, filters, table rows, map) | No motion beyond colour/opacity transitions (≤ 150ms) |
| Press feedback on anything clickable | `transform: scale(0.97)` on `:active`, `160ms var(--ease-out)` |
| Content swap in an explanatory view | `.stage-swap`: fade + 6px rise + 2px blur, 260ms `--ease-out` |
| Several items entering together | `.stagger` with `--i`, 45ms apart, ≤ ~12 items |
| Hover lift | Only inside `@media (hover: hover) and (pointer: fine)` |
| Keyboard-triggered actions | Never animated |

- Easing: `--ease-out` for enter/feedback, `--ease-in-out` for on-screen movement, `linear` only for progress.
  Never `ease-in` on UI. UI durations stay under 300ms.
- Transitions name their properties. **Never `transition: all`.** Animate `transform` and `opacity`; colours
  are fine; never animate layout (`width`, `height`, `top`, margins).
- Use transitions for anything that can be retriggered; keyframes only for one-shot entries and loops (progress
  bar, tap ripple, live dot).
- Nothing enters from `scale(0)`; start ≥ 0.95 with opacity.
- `prefers-reduced-motion: reduce`: keep fades, drop movement, ripples, pulses and press scaling (block at the end
  of `styles.css`). Auto-advancing walkthroughs start paused.

## Accessibility

- Focus: global `:focus-visible` ring (2px accent). Never remove outlines without a replacement.
- Every interactive element is a `button` or `a`. Overlays and cards that act like buttons get `role`,
  `tabIndex` and Enter/Space handling.
- Icon-only controls get `aria-label`; toggle buttons get `aria-pressed`; tab sets use `role="tablist"`,
  `aria-selected`, `aria-controls`.
- Status is never colour-only (dot + word; severity has `.sr-only` text).
- Live text (save status, progress) uses `aria-live="polite"`.
- Touch targets in phone layouts: aim for 44px.

## Data and state

- Crawl data comes only from `runs/` (see `api.ts`). Address runs by index `path` (`runKey`), never by bare id.
- Personal view state goes through `storage.ts` (`useStored`), and every access is guarded. Shared/durable user
  data (notes, triage) goes through `notes.ts` to `notes.json`. Never call `localStorage` directly from a view.

## Checklist before shipping a UI change

1. `bun run build` passes (tsc + vite).
2. Screenshots at 1400px and 390px, light **and** dark, captured over CDP after a real wait (the
   `web-ui` skill has the script; headless `--screenshot` freezes animations at frame 0 and shows empty panels).
3. Keyboard: Tab through the change; focus is visible and order makes sense.
4. Reduced motion: emulate it and confirm nothing moves that shouldn't.
5. New component or token → update this file and `#/design`.
