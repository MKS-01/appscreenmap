---
name: design-system
description: AppScreenMap's token system (packages/design-tokens/tokens.css): Ghost dark × Xcode blue, Geist type, the mobile icon language, which surfaces use the tokens, and how to change a value safely. Use before touching any colour, type, spacing, radius or motion value anywhere in the repo (web viewer, HTML reports), when adding a new surface that draws UI, or when asked to align, retheme or "centralise" the design.
---

# AppScreenMap design system

One look for everything AppScreenMap draws: the web viewer today, the crawler's HTML reports next. This skill owns
**the tokens and the rules behind them**. `web-ui` owns how the viewer is built with them (components, motion,
verification), and `apps/viewer/DESIGN.md` is the viewer's component reference.

## Where it lives

| File | What |
|---|---|
| `packages/design-tokens/tokens.css` | **The single source.** Primitives (`--gray-*`, `--blue-*`, …) and semantic tokens. Nothing else defines a colour, size or curve. |
| `apps/viewer/src/tokens.css` | The viewer's entry: `@import "@appscreenmap/design-tokens/tokens.css"` (a Bun workspace package) plus legacy aliases (below). |
| `apps/viewer/src/main.tsx` | Loads the fonts: `@fontsource-variable/geist` and `geist-mono` (self-hosted, OFL, no network at runtime). |
| `#/design` (`apps/viewer/src/views/DesignSystem.tsx`) | Live reference rendered from the real CSS. |
| `scripts/contrast.ts` (this skill) | Contrast check for every text and status token on every surface. |

Mockups the system was designed from: the canvas "AppScreenMap redesign"
(https://claude.ai/artifact/4SFYfivAGfxggUnZyrvKKq): Insights overview, an audit page, phone width, foundations.

### Who uses the tokens

| Surface | Status |
|---|---|
| Web viewer (`apps/viewer/`) | **Adopted.** Every value comes from `packages/design-tokens/tokens.css`. Old token names still work through aliases. |
| WCAG report (`a11y-report.html`, `packages/a11y/src/appscreenmap/a11y/report.py`) | **Not yet.** It has its own light/dark palette inline (`--bg #f7f7f5`, `--accent #3d5afe`, …). To adopt: read `packages/design-tokens/tokens.css` at report time and inline it, and ship the file in the wheel (hatch `force-include` `packages/design-tokens/tokens.css` → `appscreenmap/design/tokens.css`). That's crawler-side work, so coordinate with that workstream. |
| Terminal CLI (`apps/cli/`) | **Adopted.** `src/theme.ts` reads `tokens.css` at build time (`text`, `dim`, `faint`, `accent`, `good`, `warn`, `bad`, `line-hi`); same rules: blue only for what you can act on; status is an uppercase word (OK, WARN, FAILING, NOT RUN), never a dot or glyph; plain bold wordmark (`APPSCREEN` + blue `MAP`), no block lettering; a dim label column like the dashboard's field labels. |
| Exported Markdown, Maestro flows, Mermaid | No styling. Nothing to adopt. |

## The look, in five rules

1. **Dark only.** Ghost dark surfaces (`--bg #0a0a0a`, `--panel #121212`, `--panel-2 #181818`). There is no light
   theme, so don't add `prefers-color-scheme` rules. The app's own screenshots are the most colourful thing on screen, and the chrome stays out of their way.
2. **Hairlines separate, colour means something.** `--line` between rows and sections, `--line-hi` for control
   borders and device frames. No filled colour cards, no shadows on resting surfaces (`--shadow: none`);
   `--shadow-lg` only for things that float (popovers, sheets, a dragged map node).
3. **Xcode blue is for what you can act on.** `--accent #4da3ff`: links, focus, selection, the one primary
   button per view, "today" markers. Never a status, never decoration, never a big fill. A filled accent button
   uses `--on-accent` (dark text, 7.5:1), not white.
4. **Status never stands alone.** `--good` / `--warn` / `--bad` / `--info` always come with a word ("Failing"), a
   mono label (`● ERROR`) or a glyph (met / due / blocked / not checked). Element outcomes map onto them
   (`--st-*`), severities too (`--sev-*`). Sample data gets the dashed amber `SAMPLE` tag.
5. **Built around the phone.** Screens always show at their real aspect ratio in a device frame (`--radius-lg`,
   `--line-hi` border, 3–4 px inset), never cropped. Icons are drawn around mobile: phone, foldable, adaptive, tap,
   swipe, crash (phone + bolt), store, OS update, Android, iOS. Platform is always visible: Android / iOS chips
   and switches, "iOS · not crawled" stated honestly.

## Type

**Geist** for UI text, **Geist Mono** for ids, numbers, code, kickers and data labels.

| Token | Size | Use |
|---|---|---|
| `--text-3xl` | 28–34 | One page headline (a plain question beats a label: "Is Playground ready to ship?") |
| `--text-2xl` | 26 | View title (h1) |
| `--text-xl` | 19 | Section title (h2), weight 600, `--tracking-tight` |
| `--text-lg` | 16 | Card titles |
| `--text-md` | 14 | Body |
| `--text-base` | 13 | Secondary body, table cells, summaries in `--dim` |
| `--text-sm` | 12 | Meta, captions |
| `--text-2xs` | 8 | Diagram labels only (map card title bars, SVG export): drawn at overview zoom, never running text |
| `--text-xs` | 11 | Mono kickers (`UPPERCASE`, `--tracking-label`), tags, axis labels |

Big numbers use proportional figures; `tabular-nums` only in aligned columns.

`bun .claude/skills/design-system/scripts/type-guard.ts` counts raw `font-size`, `font-weight`, `line-height` and `letter-spacing` values in the viewer CSS and fails when the count rises above `type-baseline.json`: new code uses the tokens, and the baseline only goes down (`--update` after a migration).

## Values

```
surfaces  --bg #0a0a0a   --panel #121212   --panel-2 #181818   --line #232323   --line-hi #333333
text      --text #f0f0f0 (17.4:1)   --dim #a3a3a3 (7.8:1)   --faint #8a8a8a (5.7:1)
accent    --accent #4da3ff (7.5:1)  --accent-hi #6cb4ff   --accent-08/-14/-28 (washes)   --on-accent #0a0a0a
status    --good #5dd17a   --warn #e6c35a   --bad #ff5d5d   --info #a78bfa   (+ -14 tints)   failed #ff9a52
radius    4 tags/meters · 8 buttons/inputs/cards · 12 device frames/sheets · pill only for dots
space     4 · 8 · 12 · 16 · 24 · 32 · 48
motion    --ease-out (0.23,1,0.32,1) · press 120ms scale(0.97) · fast 150ms · ui 220ms
touch     --hit-min 44px on phones
```

## Changing a token

1. Edit `packages/design-tokens/tokens.css` only. Change the primitive if the hue changes; change the semantic mapping if
   the role changes.
2. `bun .claude/skills/design-system/scripts/contrast.ts`. It must print "All pairs pass" (text ≥ 4.5:1 on
   `--bg`, `--panel` and `--panel-2`). It already caught `--faint #808080` at 4.47:1 on `--panel-2`; that's why it's `#8a8a8a`.
3. `cd apps/viewer && bun run build`, then screenshot with the `web-ui` skill's `shot.ts` (dark, 1400 and 390).
4. Update the Values block above, `apps/viewer/DESIGN.md`'s token table and `#/design` if a token was added or renamed.
5. Grep for hard-coded colours you may have just orphaned:
   `grep -nE "#[0-9a-fA-F]{3,8}\b|rgba?\(" apps/viewer/src -r` should only show `packages/design-tokens/tokens.css` values and alpha masks.

## Legacy aliases (migrate, then delete)

`apps/viewer/src/tokens.css` maps the pre-Ghost names onto the new ones so ~200 older rules kept working through the
switch: `--border` → `--line`, `--muted` → `--dim`, `--accent-soft` → `--accent-14`, `--accent-text` →
`--accent`, `--mono` → `--font-mono`, `--radius` → `--radius-md`. New code uses the new names. When you touch a
rule, migrate it; when `grep -r "var(--muted" apps/viewer/src` finds nothing, delete that alias.

## Decisions (Oct 2026), in the owner's words

- **Source of the look:** the owner's centralised design system on claude.ai/design (the "Ghost" theme of the
  readback system). Reading it needs `/design-login`, then `DesignSync` `get_project` / `list_files` / `get_file`
  (project `a62fa764-2f7b-4b6b-beae-1d6e70f641da`). Until then, the Ghost values came from mksbrew's git
  history (`sites/readback/style.css` at `46cb054`: `#0a0a0a`, `#121212`, `#232323`, `#333333`, `#f0f0f0`, `#4da3ff`).
  Check new values against the real system once it's readable.
- **Accent:** *"for main theme we can use the xcode blue?? or nearby blue"*, so Ghost's own Xcode blue `#4da3ff`.
  (mksbrew's sites use terracotta; AppScreenMap does not.)
- **Theme:** asked dark-first + light vs dark only, the owner picked **"Dark only"**.
- **Fonts:** *"try new fonts"* (not mksbrew's IBM Plex Mono / Martian Mono). Geist + Geist Mono: a pair drawn
  together, good tabular figures for dense data, OFL, self-hosted.
- **Insights:** *"insight is blunder not upto the marks"*. The coloured score cards, thick bars and all-red
  "Failing" labels were replaced by a hairline ledger sorted by urgency, a store/platform calendar, and honest
  status words ("Partial" for a budget-capped crawl, "Blocked" for a store gate). See the mockup canvas.
- **Approved:** *"this look overall good. lets revamp everything around the same"*.
- **Project mark:** D, "stacked screens": a filled `--accent` tile (radius 8 on a 32 grid) holding two dark
  phone screens, the back one at 45 % opacity. `Logo` in `apps/viewer/src/components/common.tsx`, favicon in
  `apps/viewer/index.html` (hex mirrors of `--accent` / `--bg`, since a favicon can't read CSS variables). Chosen from four
  options on the canvas's "Logo options" board. The owner first picked C ("phone with a route"), then changed to
  *"D looks more better"* before it shipped. Solid shapes only: a mark must read at 16 px.

## Rejected: don't re-propose

- A light theme, or following the OS theme (owner chose dark only).
- Blue-to-purple gradients (the old run-card app tile). They're decoration, and a cliché.
- One filled, coloured card per audit with a big score (the first Insights). Too loud, and every card read "Failing".
- The system font stack (`-apple-system, Inter, Roboto`) as the brand face.
- A thin-stroke mark (a phone outline with three node dots on an `--accent-14` tile): *"fix the project icon..
  new one looks bad"*. Strokes and dots disappear at 16–26 px.
