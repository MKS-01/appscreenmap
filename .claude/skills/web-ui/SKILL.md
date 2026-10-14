---
name: web-ui
description: Design and build UI in the AppScreenMap web viewer (apps/viewer/) — new views, components, layout or styling changes, motion, icons, polish passes — following the design-system skill (tokens in packages/design-tokens/tokens.css: Ghost dark × Xcode blue, Geist), apps/viewer/DESIGN.md, the live reference at #/design, and Emil Kowalski's design-engineering approach. Use for any visual or interaction change in apps/viewer/, "make it look better", "add icons", "make it interactive", or a UI review of the viewer.
---

# Viewer UI work

The viewer is React + TypeScript + Vite in `apps/viewer/`, run with **Bun** (never npm). It has no backend: it reads
`runs/` as static files, plus a single `PUT` for `notes.json`. The crawler (`src/`) belongs to another workstream.
Don't edit it for UI work. If the UI needs new data, ask for a `map.json` field (see `docs/MAP_SCHEMA.md`).

## 1. Load the design context first

1. Invoke the **`design-system`** skill: the tokens, the five rules (dark only, hairlines, Xcode blue only for
   actions, status never alone, built around the phone), type, icons, and what was rejected.
2. Invoke the **`emil-design-eng`** skill: motion decision framework, easing, press feedback, review table
   format. Also use **`animate`** to build a specific animation, or **`improve-animations`** to audit existing motion.
3. Read **`apps/viewer/DESIGN.md`**: principles, components, motion and accessibility rules, checklist.
4. Open **`#/design`** in the running viewer to see the current tokens and components rendered.

## 2. Build with the system

- **Tokens only.** Colours, radii, curves, durations come from `packages/design-tokens/tokens.css` (`var(--…)`), never a hex in a
  view or in `styles.css`. Use the semantic names (`--line`, `--dim`, `--accent-14`, `--font-mono`), not the legacy
  aliases in `apps/viewer/src/tokens.css`. Adding or changing a token follows the `design-system` skill (contrast check
  included), then `DESIGN.md` and `#/design` (`src/views/DesignSystem.tsx`).
- **Reuse components** (`.panel`, `.btn`, `.chip`, `.seg`, `Stat`, `StatusBadge`, `.tbl`, `.effect`, `Icon`,
  `.sec-title`, `.stage-swap`, `.stagger`) before inventing. A pattern used twice goes into the system.
- **Icons:** `apps/viewer/src/components/Icon.tsx` only (Lucide-style inline SVG; paste new shapes into `PATHS`).
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
cd apps/viewer && bun run build                      # tsc + vite; must pass
# serve real or copied runs (don't write notes into runs you don't own)
uv run appscreenmap-engine serve --runs <runs-dir> --no-open --port 8795 &
bun ../../.claude/skills/web-ui/scripts/shot.ts --base http://127.0.0.1:8795/ --out <scratchpad> \
    "#/" "#/how" "#/r/<project>%2F<run-id>/map" --themes dark   # 1400 + 390 px
bun ../../.claude/skills/web-ui/scripts/shot.ts ... --reduced-motion --themes dark --widths 1400
```

Then **look at every screenshot** (Read the PNGs). Check: nothing clipped or overflowing at 390px, empty and
loading states, real data with long titles. The viewer is dark only, so pass `--themes dark`.

Also run the **scroll check** after any layout change. The app scrolls inside `.main`, so the *document* must never scroll:

```bash
bun ../../.claude/skills/web-ui/scripts/scroll-check.ts --base http://127.0.0.1:8795/     # exit 1 + the page, if one is flagged
```

It flags a page whose document is taller than the window (an absolutely positioned element escaped the scroll container, which
shows as empty space when you scroll past the end), content wider than the container, and empty space after the last element.

> Don't use `chrome --headless --screenshot` for animated pages. It runs on virtual time, so CSS animations
> stay at frame 0 and animated panels look empty. `shot.ts` drives Chrome over CDP and waits in real time.

For interactions (clicks, typing, triage), drive the page over CDP the same way: `Runtime.evaluate` to click,
then assert on the DOM or on files written. A test that only looks at a static screenshot hasn't tested behaviour.

## 4. Report

Summarise visible changes with a Before / After / Why table (the `emil-design-eng` review format), and list what
you verified (themes, widths, reduced motion, keyboard). If you changed tokens or components, say that
`DESIGN.md` and `#/design` were updated too.
