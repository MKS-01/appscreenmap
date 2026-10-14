# AppScreenMap web viewer

React + TypeScript + Vite, with React Flow (`@xyflow/react`) and dagre for the graph layout. There's no backend:
the viewer reads `runs/index.json` and `runs/<id>/…` as static files, and polls `map.json` / `trace.jsonl`
every 2 s while a run's status is `running`, so you can watch a crawl build its map.

The project uses [Bun](https://bun.sh) as package manager and runtime (`bun.lock`); scripts run Vite and tsc with
`bun --bun`.

```bash
bun install
bun run dev      # http://localhost:5173 — serves ../runs at /runs (override with APPSCREENMAP_RUNS=path)
bun run build    # → web/dist, which `appscreenmap serve` picks up
```

| Route | View |
|---|---|
| `#/` | Runs |
| `#/how` | How it works: the crawl pipeline, and what to do with a map once you have one |
| `#/r/<run>/map` | Screen map in three layouts: Tree (default), Graph, Storyboard (`?layout=tree\|graph\|story`). Click a screen to highlight its path from launch; double-click to open it. `?focus=<screen>` preselects one |
| `#/r/<run>/screens` | Gallery with search over titles, element text and resource-ids |
| `#/r/<run>/s/<screen>` | Screenshot with element overlays colored by status, element table, transitions, path from launch, Maestro flow, raw XML |
| `#/r/<run>/replay` | Crawl replay: steps through `trace.jsonl` with before/after screens and why each step happened. `?screen=<id>` jumps to its discovery |
| `#/r/<run>/insights` | Coverage, dead ends, hubs, blocked / untried / failed actions, depth, run events |
| `#/r/<run>/a11y` | Accessibility review: Scanner-style checks on every screen, triage, Markdown/CSV export |
| `#/r/<run>/a11y/report` | The crawler's WCAG 2.2 report (`a11y-report.html`) shown inside the viewer in a sandboxed frame, with Download HTML and Open in new tab. Shown only when the run has a report |
| `#/r/<run>/compare[/<base>]` | Visual diff against a baseline run (from `appscreenmap diff`) |

`<run>` is the run's folder under `runs/`: `<project>/<run-id>` (URL-encoded), or `<run-id>` for legacy runs. Old
id-only links redirect.

## What's saved where

| Data | Where | Why |
|---|---|---|
| Crawl output | `runs/<project>/<run-id>/` | Source of truth, written by the crawler |
| Stars, screen notes, a11y triage | `runs/…/notes.json` via `PUT` to `appscreenmap serve` or the dev server | Travels with the run, survives browser resets, can be committed |
| View prefs, dragged map layouts | `localStorage` (`appscreenmap:v1:*`) | Personal to one browser, fine to lose |

On a read-only host the `PUT` fails, so notes stay in localStorage and sync to `notes.json` the next time a save succeeds.

## Accessibility checks (`src/a11y.ts`)

These run in the browser from each screen's hierarchy XML and screenshot: missing labels, unlabeled text fields, text fields
using contentDescription, touch targets under 48×48 dp, low text contrast (estimated from pixels), duplicate
descriptions, and role words in descriptions. Sizes use `run.device.density` when the crawler records it; otherwise
density is estimated from screen width. They're hints for a person to triage, not a WCAG audit.

**UI changes:** follow [`DESIGN.md`](DESIGN.md) (tokens in `src/tokens.css`, live reference at `#/design`) and the
project skill `.claude/skills/web-ui`.

Contributing and the full project README are in the [repo root](../README.md). Types in `src/types.ts` mirror `map.json` schema 1 (`packages/core/src/appscreenmap/core/model.py`); update both together.
