---
name: web-ui
description: Design and build UI in the AppScreenMap web viewer (web/) — new views, components, layout or styling changes, motion, icons, polish passes — following the viewer's design system (web/DESIGN.md, tokens in web/src/tokens.css, live reference at #/design) and Emil Kowalski's design-engineering approach. Use for any visual or interaction change in web/, "make it look better", "add icons", "make it interactive", or a UI review of the viewer.
---

# Viewer UI work

The viewer is React + TypeScript + Vite in `web/`, run with **Bun** (never npm). It has no backend: it reads
`runs/` as static files, plus a single `PUT` for `notes.json`. The crawler (`src/`) belongs to another workstream.
Don't edit it for UI work. If the UI needs new data, ask for a `map.json` field (see `docs/MAP_SCHEMA.md`).

## 1. Load the design context first

1. Invoke the **`emil-design-eng`** skill: motion decision framework, easing, press feedback, review table
   format. Also use **`animate`** to build a specific animation, or **`improve-animations`** to audit existing motion.
2. Read **`web/DESIGN.md`**: principles, tokens, components, motion and accessibility rules, checklist.
3. Open **`#/design`** in the running viewer to see the current tokens and components rendered.

## 2. Build with the system

- **Tokens only.** Colours, radii, curves, durations come from `web/src/tokens.css` (`var(--…)`). Adding a
  token means adding it to `tokens.css`, `DESIGN.md` and `#/design` (`src/views/DesignSystem.tsx`).
- **Reuse components** (`.panel`, `.btn`, `.chip`, `.seg`, `Stat`, `StatusBadge`, `.tbl`, `.effect`, `Icon`,
  `.sec-title`, `.stage-swap`, `.stagger`) before inventing. A pattern used twice goes into the system.
- **Icons:** `web/src/components/Icon.tsx` only (Lucide-style inline SVG; paste new shapes into `PATHS`).
  No icon fonts, no new icon dependencies.
- **Motion:** answer "should this animate?" first. Frequent views (map, tables, filters) get colour/opacity
  only; press feedback `scale(0.97)`; explanatory pages may use `.stage-swap` and `.stagger`. Custom curves
  (`--ease-out`), name the transitioned properties (never `all`), hover effects inside
  `@media (hover: hover) and (pointer: fine)`, and extend the `prefers-reduced-motion` block when you add movement.
- **Data:** address runs by `runKey(row)` (index `path`); personal UI state via `useStored`
  (`src/storage.ts`); shared user data via `src/notes.ts`. No direct `localStorage` in views.
- **Accessibility:** real `button`/`a` elements, `aria-pressed`/`aria-selected` on toggles and tabs, labels on
  icon-only controls, status never colour-only, visible `:focus-visible`.

## 3. Verify like a user

```bash
cd web && bun run build                      # tsc + vite; must pass
# serve real or copied runs (don't write notes into runs you don't own)
uv run appscreenmap serve --runs <runs-dir> --no-open --port 8795 &
bun ../.claude/skills/web-ui/scripts/shot.ts --base http://127.0.0.1:8795/ --out <scratchpad> \
    "#/" "#/how" "#/r/<project>%2F<run-id>/map"            # light + dark, 1400 + 390 px
bun ../.claude/skills/web-ui/scripts/shot.ts ... --reduced-motion --themes dark --widths 1400
```

Then **look at every screenshot** (Read the PNGs). Check: nothing clipped or overflowing at 390px, both
themes readable, empty and loading states, real data with long titles.

> Don't use `chrome --headless --screenshot` for animated pages. It runs on virtual time, so CSS animations
> stay at frame 0 and animated panels look empty. `shot.ts` drives Chrome over CDP and waits in real time.

For interactions (clicks, typing, triage), drive the page over CDP the same way: `Runtime.evaluate` to click,
then assert on the DOM or on files written. A test that only looks at a static screenshot hasn't tested behaviour.

## 4. Report

Summarise visible changes with a Before / After / Why table (the `emil-design-eng` review format), and list what
you verified (themes, widths, reduced motion, keyboard). If you changed tokens or components, say that
`DESIGN.md` and `#/design` were updated too.
