# AppScreenMap — Plan

> Point it at a build and an emulator. It walks the app screen by screen, records every
> screen and transition, and produces a navigable map you browse in a web app.

## 1. Goal

A developer gives us **an app build** (APK, later IPA/.app) and **a running emulator/simulator**.
AppScreenMap then, with no app-specific code:

1. Installs and launches the app.
2. Explores the UI automatically — tap, scroll, type, go back — screen by screen.
3. Identifies each unique **screen** and records every **transition** between screens.
4. Recognizes UI **patterns** (lists, tabs, bottom nav, forms, dialogs, login, webviews).
5. Saves screenshots, view hierarchies and the full graph as plain files (`map.json`).
6. Generates outputs others can use: **Maestro flows** to reach every screen,
   Mermaid diagrams, and visual-diff reports between two builds.
7. Shows it all in a **web app**: an interactive screen graph, screen gallery, per-screen
   detail with tappable element overlays, path-from-launch, and a visual compare view.

Who uses it:

| Who | How |
|---|---|
| QA / automation engineers | Start from generated Maestro flows and stable selectors instead of writing them by hand |
| New team members / PMs | Browse an unfamiliar app's structure without installing it |
| Visual testing | Compare screenshots of the same screens between two builds |
| Devs | Catch crashes, dead-end screens, and unreachable activities |

## 2. Prior art (what we borrow)

| Tool | Approach | What we take from it |
|---|---|---|
| [DroidBot](https://github.com/honeynet/droidbot) | Python + ADB; builds a UI Transition Graph (UTG), DFS/BFS exploration, HTML viewer | UTG model, state hashing from the view tree, restart + replay to backtrack |
| [Fastbot (ByteDance)](https://github.com/bytedance/Fastbot_Android) | Model-based, saves the state graph, reuses the model across runs | Persisting the model and reusing it between runs |
| [APE](https://github.com/tianxiaogu/ape) | Adjusts state abstraction while it runs | Merging near-duplicate states by similarity instead of exact hash |
| [Firebase Robo test](https://firebase.google.com/docs/test-lab/android/robo-ux-test) | Cloud crawler; crawl graph + screenshots; robo scripts for login | Pre-filled inputs (credentials), auto-handling of system dialogs |
| [Maestro](https://github.com/mobile-dev-inc/maestro) | YAML flows, `id` / text selectors | **Export format** for the paths we find |
| [AppCrawler](https://github.com/seveniruby/AppCrawler) | Appium-based traversal with blacklists | Blocked-action list (logout, delete, pay) |
| [GoalExplorer](https://github.com/resess/GoalExplorer) / [SceneDroid](https://github.com/SceneDroid/SceneDroid) | Static analysis + dynamic exploration; fine-grained "scene" graphs | Future: seed exploration from the manifest's activity list |
| [AppAgent](https://github.com/TencentQQGYLab/AppAgent), [Screenmap](https://www.everydev.ai/tools/screenmap), Android UI Analyser | LLM agents explore and save replayable paths | Future: an optional LLM "brain" for semantic screen names and smarter input |

**How AppScreenMap differs:** it's deterministic and needs no LLM (an LLM is optional
later); it produces a portable `map.json` plus a polished web viewer; patterns and
visual diffs are built in; and automation output (Maestro) is part of the product.

## 3. Architecture

```
┌────────────────────────── developer machine ──────────────────────────┐
│                                                                        │
│  appscreenmap crawl --apk app.apk                                      │
│        │                                                               │
│  ┌─────▼──────┐   ┌────────────┐   ┌────────────┐   ┌──────────────┐   │
│  │  Driver     │──▶│  Analyzer  │──▶│  Explorer   │──▶│  RunStore     │   │
│  │ (ADB today; │   │ hierarchy →│   │ DFS + back- │   │ runs/<id>/    │   │
│  │  XCUITest / │   │ elements,  │   │ tracking,   │   │  map.json     │   │
│  │  u2 later)  │◀──│ signature, │◀──│ autofill,   │   │  screens/*.png│   │
│  └─────────────┘   │ patterns   │   │ safety      │   │  flows/*.yaml │   │
│        ▲           └────────────┘   └────────────┘   └──────┬───────┘   │
│        │ adb                                                │          │
│  ┌─────┴─────┐                                 ┌────────────▼────────┐ │
│  │ Emulator  │                                 │ Web viewer (React)   │ │
│  └───────────┘                                 │ appscreenmap serve   │ │
│                                                └─────────────────────┘ │
└────────────────────────────────────────────────────────────────────────┘
```

### Components

| Component | Language | Job |
|---|---|---|
| `driver` | Python | Wraps ADB: install, launch, dump the hierarchy, screenshot, tap/swipe/type/back, foreground activity. Behind an interface so iOS (XCUITest/`idb`) and faster backends (uiautomator2) can be added. |
| `apkinfo` | Python | `aapt2`: package, version, label, launch activity, **declared activities** (used for coverage). |
| `analyzer` | Python | Turns a hierarchy XML into: actionable elements, a stable **screen signature**, a token set for similarity, a title, and detected **patterns**. |
| `explorer` | Python | The crawl loop: choose an action → perform → observe → match or register the screen → record the edge. Backtracks with graph paths, falling back to restart + replay. Handles permission dialogs, leaving the app, crashes. |
| `store` | Python | Writes `runs/<run-id>/` as it goes (map.json is updated live so the viewer can follow a crawl in progress). |
| `export` | Python | Maestro flows (one per screen), Mermaid graph. |
| `visual` | Python | Perceptual hash and pixel diff between two runs; status bar masked. |
| `web` | React + TS + Vite + React Flow | The viewer. Static: reads `runs/index.json` and `runs/<project>/<run-id>/map.json`. |

**Why Python + ADB for v1:** no setup on the device, works on any emulator or real device
and on any Android version that has `uiautomator`. Measured on the dev emulator (Android 17):
hierarchy dump ≈ 2.0 s, screenshot ≈ 0.15 s, so about 3 s per step. A uiautomator2 backend
(≈0.3 s dumps) is the planned speed upgrade.

## 4. Core algorithms

### 4.1 Screen identity (the hard part)

A "screen" has to survive dynamic content (clocks, counters, feeds) and still tell apart
screens that share an activity (Compose / single-activity apps, Settings sub-pages).

Signature = `sha1(activity + sorted(token set))`, where the tokens are:

- **Structure tokens** `S:<class>|<resource-id>` for every node.
- **Text tokens** `T:<normalized text>` / `D:<content-desc>`, only for nodes that are
  **not** repeated list items and **not** editable. Normalizing lowercases the text,
  replaces digits with `#` (`10:15` → `##:##`), and truncates to 40 chars.
- **Repeated list items** are detected by subtree shape (class + id skeleton): 2+ siblings
  with the same shape inside a scroll container, or 3+ anywhere. Their text is excluded,
  so a feed with new content is still the same screen.

Matching a new observation:

1. Exact signature match → same screen.
2. Otherwise compute Jaccard similarity of the token set against known screens with the
   same activity + package; ≥ `similarity` (default 0.80) → same screen (newly seen
   elements are merged in).
3. Otherwise → a new screen.

### 4.2 Elements and actions

An element is actionable if it is visible, enabled, and either clickable, long-clickable,
checkable, scrollable, or an EditText. It is skipped if it covers ≥ 90% of the screen
(click-away backgrounds).

- **Label** = own text → content-desc → hint → descendant text → resource-id name.
- **Kind**: `nav` (bottom bar), `tab`, `button`, `list_item`, `toggle`, `input`, `scroll`,
  `up` (Navigate up), `back` (system, one per screen).
- **Stable key**: the resource-id if it's unique on the screen; otherwise kind + class + label;
  list items are keyed by `group + label`.
- **Pattern cap**: explore at most `max_list_items` (default 2) items per list group;
  the rest are marked `skipped: pattern` ("all items in this list lead to the same detail screen").
- **Priority**: nav → tab → button → scroll → list_item → toggle → long-click → up → back.

### 4.3 Exploration loop (greedy DFS with backtracking)

```
restart app → observe → register root
while within budget (steps, minutes):
    handle system UI: permission dialog → allow; crash dialog → record + close; other app → back/relaunch
    autofill empty inputs on this screen (rules from config: email/password/phone/…)
    action = highest-priority pending action on current screen (depth < max_depth)
    if action:
        perform → settle → observe → identify screen → record transition
    else:
        target = nearest screen (BFS over the known graph) that still has pending actions
        go there along graph edges; if that diverges → force-stop, relaunch, replay target.reach_path
        two failed attempts → mark the target's remaining actions "unreachable"
stop when nothing is pending → write exports
```

- **Scroll** is one compound action: swipe up to `max_scrolls` times, merging new elements
  into the same screen (tagged with `scroll_depth`), then scroll back. Elements found below
  the fold are later reached with scroll-and-search (in Maestro: `scrollUntilVisible`).
- **Autofill** runs whenever we arrive at a screen with empty fields, during both
  exploration and replay, so paths through a login form still work. The filled values are
  stored on the screen and emitted in the Maestro flows.
- **Safety**: elements whose label matches `blocked_text` (logout, delete, pay, purchase,
  uninstall, call, …) are never tapped. This is configurable.
- **Leaving the app**: recorded as an edge to an external pseudo-screen (`x:<package>`),
  e.g. "Privacy policy → opens Chrome". Then press back, or relaunch if back doesn't return.
- **Crashes**: detected from the system "keeps stopping" dialog; we store a `crash` edge
  plus the crash logcat buffer.

### 4.4 Patterns recorded per screen

`list`, `tabs`, `bottom_nav`, `form`, `login` (form with a password field), `dialog`,
`drawer`, `webview`, `scrollable`, `empty` (no actions), `dead_end` (only back).
Across the whole app: hub screens (bottom-nav destinations), max depth, and activity coverage.

## 5. Output format (`runs/<run-id>/`)

```
runs/
  index.json                      # all runs (for the viewer)
  <pkg>-<yyyymmdd-hhmmss>/
    map.json                      # the source of truth (schema below)
    trace.jsonl                   # one line per step
    screens/s001.png  s001.jpg (thumb)  s001.xml
    flows/s001.yaml               # Maestro flow: launch → … → assert screen
    map.mmd                       # Mermaid flowchart
    crashes/                      # logcat for each crash
    diff/<baseline-run>/diff.json + *.png   # from `appscreenmap diff`
```

`map.json` (schema v1, abbreviated):

```jsonc
{
  "schema": 1,
  "run":   { "id", "status": "running|done|failed", "started_at", "finished_at", "steps",
             "app": { "package", "label", "version", "launch_activity", "activities": [] },
             "device": { "serial", "model", "android", "width", "height" }, "config": {} },
  "screens": [{
     "id": "s003", "kind": "app|external|crash", "title", "activity", "signature",
     "patterns": ["list","bottom_nav"], "depth": 2, "visits": 5,
     "screenshot": "screens/s003.png", "thumb": "screens/s003.jpg",
     "reach_path": [{ "screen": "s001", "key", "action": "click", "label", "selector": {} }],
     "autofill": [{ "key", "label", "value" }],
     "elements": [{ "id", "key", "kind", "label", "rid", "class", "bounds": [x1,y1,x2,y2],
                    "action", "status": "done|pending|blocked|skipped|unreachable|failed",
                    "effect": "new_screen|known_screen|same_screen|left_app|crash",
                    "target": "s004", "scroll_depth": 0 }]
  }],
  "transitions": [{ "id", "from", "to", "key", "action", "label", "count", "step" }],
  "events": [{ "step", "type": "crash|permission|restart|nav_failed", "detail" }],
  "stats": { "screens", "transitions", "activities_visited", "activities_declared", "crashes" }
}
```

## 6. Web viewer

React + TypeScript + Vite, with React Flow (`@xyflow/react`) and dagre for the graph layout.
No backend: in dev it reads `runs/` through a Vite middleware; in production
`appscreenmap serve` serves the built viewer plus `runs/`.

| View | What it shows |
|---|---|
| **Runs** | Every run: app, version, device, date, screens / transitions / crashes |
| **Map** | Graph of screenshot cards, edges labeled with the action, left-to-right or top-to-bottom layout, filter by activity/pattern, highlight path from launch. Live-updates while a crawl runs. |
| **Screens** | Gallery grid; search by title/text/id; pattern chips |
| **Screen detail** | Screenshot with element overlays (colored by status; click an overlay to jump to its target screen), element table, in/out transitions, step-by-step path from launch, Maestro flow with a copy button, raw XML |
| **Compare** | Baseline vs. candidate vs. diff image for each matched screen; new and missing screens |
| **Insights** | Activity coverage, dead ends, crashes, blocked actions, depth histogram |

## 7. CLI

```bash
appscreenmap doctor                                 # check adb, device, aapt2
appscreenmap crawl --apk app.apk                    # install + crawl
appscreenmap crawl --package com.example.app        # app already installed
      [--serial emulator-5554] [--config appscreenmap.toml] [--max-steps 300]
      [--max-minutes 30] [--clear-data] [--out runs]
appscreenmap export runs/<project>/<run-id>         # regenerate Maestro flows + Mermaid
appscreenmap diff runs/<baseline> runs/<candidate>  # visual + text diff between builds
appscreenmap verify runs/<baseline> [--apk new.apk] # replay every path on a new build; exit 1 if one broke
      [--fail-on-change] [--update-baselines] [--screen s005] [--no-clear-data]
appscreenmap mcp [--runs runs] [--run <run-id>]     # MCP server over stdio for coding agents
appscreenmap serve [--runs runs] [--port 8765]      # open the web viewer
```

Config (`appscreenmap.toml`): budgets, similarity, list cap, blocked text, input rules
(regex → value, e.g. test-account credentials as `${ENV}` placeholders), whether to explore toggles /
long-press.

## 8. Roadmap

| Phase | Scope | Status |
|---|---|---|
| **0. Plan + scaffold** | This doc, repo layout, MIT license, CI-ready tooling | ✅ |
| **1. Android MVP** | ADB driver, analyzer, explorer, live map.json, Maestro + Mermaid export, visual diff, web viewer (runs, map, gallery, detail, compare), WCAG 2.2 checks + report, navigation load times | ✅ crawler · viewer in progress |
| 2. Robustness | uiautomator2 backend (5× faster), WebView handling, better dialog/IME handling, model reuse to resume a crawl, `--from-run` to recrawl only changed screens | |
| 3. iOS | **After Android is solid.** Simulator driver via XCUITest (WebDriverAgent) or `idb`; same map format and viewer | |
| 4. Intelligence | Optional LLM step: semantic screen names, smarter form inputs, goal-directed exploration ("reach checkout") | |
| 5. Team | Docker image + GitHub Action, `appscreenmap publish` to a static site, Appium/Espresso page-object export | |
| 6. Localisation | Crawl in several locales (incl. pseudo-locales), match screens across locales, l10n review in the viewer (untranslated text, truncation, overflow, RTL mirroring), side-by-side locale gallery, context screenshots for translators. Depends only on phase 1, so it can ship before 3–5. See §8.1 | |
| 7. Agents & CI | MCP server (the map as agent memory), `appscreenmap verify` (replay every reach path on a new build, CI exit codes, baselines), secrets as `${ENV}` placeholders, text-aware visual diff. See §8.2 | ✅ crawler (`verify` on sample-app, same build: 8 passed, 3 skipped as state-dependent, exit 0) |
| 8. Performance & conditions | Perfetto traces for slow transitions, crawl screen recordings, emulator network profiles, condition matrix (landscape, dark mode, denied permissions, display size), keyboard/D-pad reachability crawl. See §8.2 | |

### 8.1 Localisation support (planned)

**Goal:** for an app that ships in several languages, answer "does every screen work in every language we
ship?" without writing a test per locale.

**Which languages.** `apkinfo` reads the languages the app actually ships from the APK
(`aapt2 dump badging` → `locales: 'de' 'fr' 'ar' …`). It records them in `run.app.locales`, and the viewer
shows that list even before any locale is crawled. `--locales all` means "every language the app ships", and
`--locales app+pseudo` adds the pseudo-locales.

**Running locales.** `appscreenmap crawl --locales en-US,de-DE,ar-EG,ja-JP` (or `--locale` for one) switches
the app's language before launch with the per-app language API
(`adb shell cmd locale set-app-locales <pkg> --locales de-DE`, Android 13+). Older devices fall back to
changing the system locale, which needs a rooted emulator. Android's built-in pseudo-locales come almost free and
catch most layout bugs before real translations exist:
`en-XA` (accented text, ~30–40% longer) and `ar-XB` (right-to-left). They need a debuggable build with
`pseudoLocalesEnabled`.

**One map, many locales.** Text tokens change with the language, so exploring each locale from scratch would
produce maps that don't line up. Instead, the first locale is explored normally. Every other locale **replays** the
base map: it walks each screen's `reach_path` with locale-independent selectors (resource-id, then position), then
captures that screen's screenshot and hierarchy. Screen identity falls back to structure tokens plus the reach
path. Screens a locale can't reach are reported, not silently skipped.

```
runs/<project>/<run-id>/
  map.json                     # base locale (unchanged schema)
  locales/<locale>/screens/s001.png  s001.xml
  locales/<locale>/l10n.json   # per-screen findings for that locale
```

**l10n review (viewer, alongside the Accessibility tab).** Checks run on each locale's hierarchy and screenshot,
compared with the base locale. Triage decisions go in `notes.json` like a11y ones.

| Check | How |
|---|---|
| Untranslated text | Same string as the base locale on a translated screen (ignoring numbers, brand names, an allowlist) |
| Truncation | Text ending in `…`, or text bounds clipped by the parent's bounds |
| Overflow / overlap | Sibling text bounds that intersect, or that extend past the screen edge |
| RTL mirroring | In `ar`/`he`/`ar-XB`, navigation and back controls should swap sides relative to the base locale |
| Placeholders leaking | `%s`, `{0}`, `@string/…` or raw keys visible on screen |
| Missing glyphs | Replacement characters (`\uFFFD`) in the hierarchy text: a font can't render the script |
| Coverage gaps | Languages the APK declares but a locale run shows mostly base-language text: likely an incomplete translation |

**Viewer.** A "Localisation" tab per run with a language × screen matrix: each cell shows the finding count,
and clicking a cell opens that screen in that language. The table is one row per language: screens reached,
untranslated %, truncations, RTL issues, review progress. Every screen gets a locale switcher and a side-by-side
gallery of the screen in all languages (reusing the Compare layout). Findings export to Markdown or CSV per language
for translators and developers.

**Outputs.** Per-screen "context screenshots" with each string's bounds, exportable as a zip for translation
tools (Crowdin, Lokalise, Phrase), so translators see where a string appears. Maestro flows stay locale-safe by
preferring resource-id selectors; flows that can only use text selectors are flagged.

**Open questions:** how to detect strings that are hard-coded rather than coming from resources (only possible with
the APK's resource table, via `aapt2 dump resources`); and whether to translate the viewer UI itself (low priority).

### 8.2 Ideas from Argent

[Argent](https://github.com/software-mansion/argent) (Software Mansion, Apache-2.0 core) is an MCP toolkit
that gives a coding agent hands on iOS/Android/TV/Electron apps: ~80 tools for driving the UI, recorded
flows, visual regression, React and native profiling, and network logs
([docs](https://docs.swmansion.com/argent/docs/fundamentals/getting-started)). It is **interactive**: an
agent does one task at a time. AppScreenMap is **autonomous and whole-app**: it maps every screen and reports
on all of them. They complement each other. What to adopt:

| Argent does | What it teaches us | Plan | Priority |
|---|---|---|---|
| MCP server: the agent calls tools | Agents need the map, not just screenshots | `appscreenmap mcp`: `list_screens`, `get_screen` (elements, a11y, perf), `route` (steps to a screen), `go_to_screen` (drive the device there), `where_am_i` (match the live screen to the map), `crawl`/`crawl_status`, `a11y_findings`, `perf_summary`. The map becomes agent memory, so nothing is re-explored. | ✅ (+ `list_runs`, `find_screens`, `screenshot`; optional `mcp` extra, SDK 2.x) |
| Flows: record once, replay in CI with exit codes, failed step gets a screenshot, `--update-baselines` | Our reach paths are flows already | `appscreenmap verify runs/<base> [--apk new.apk]`: replay every screen's reach path on a new build, check screen identity, snapshot each step against the base run, exit non-zero on broken paths. Fragments with a prerequisite = paths starting from a known screen. | ✅ (`--fail-on-change`, `--update-baselines`; fragments: next) |
| Secrets as placeholders filled from the environment, never in agent context | We write typed values into map.json, Maestro flows and the trace | `[inputs] password = "${APP_PASSWORD}"`: resolved at type time, stored as the placeholder everywhere (Maestro reads `${VAR}` too). | ✅ |
| Visual regression with OCR/font awareness: text appeared/disappeared/moved/restyled, regions marked brighter/darker, element-scoped snapshots, status bar removed | Pixel diff alone is noisy | Text-aware diff from the **hierarchy** (exact strings and bounds, so no OCR needed): per-element added/removed/moved/changed, plus pixel regions with direction. Element-scoped compare by element key. | ✅ text + regions. Next: element-scoped compare; "restyled" needs style data the hierarchy lacks |
| `await-screen-idle`, `await-ui-element` (no screenshot loops) | Same idea as our gfxinfo settle | ✅ done (frame-counter settle). Next: wait for a specific element via the on-device helper. | ✅ / P2 |
| Android helper instrumentation app resolves selectors on the device | The 2 s `uiautomator dump` is our bottleneck | On-device agent driver (Phase 2): fast tree, element waits, batched actions (`run-sequence`). | P2 |
| Native profiler on Android = Perfetto (hangs with a jank reason, CPU, GC) | Frame counts tell *that* a screen is slow, not *why* | When a transition exceeds the budget, replay it under `perfetto` (gfx/view/am/sched) and attach the trace, top jank reasons and a ui.perfetto.dev link to perf.json. | P2 |
| Screen recording (h264) | Video shows transitions and loading states a screenshot misses | Record the crawl in `screenrecord` segments; per-transition clips in the viewer; clips attached to failed `verify` steps. | P2 |
| Network logs (JS `fetch` layer on Android; read-only, no throttling) | Load time needs a "why" too | Emulator network profiles (`adb emu network speed/delay`) for load times under 3G/edge; correlate slow loads with requests where the app logs them. | P2 |
| Device controls: rotate, permissions grant/deny/reset, fold, D-pad | Conditions reveal different screens and bugs | Condition matrix per run: landscape (WCAG 1.3.4/1.4.10), dark mode (`cmd uimode night yes`), denied permissions (error states), display size, font scale (✅). | P2 |
| TV D-pad, focus-driven navigation | Focus reachability is an accessibility signal | Keyboard/D-pad-only crawl: which elements can focus reach, and in what order → evidence for WCAG 2.1.1/2.4.3/2.4.7. | P3 |
| Component source lookup (file, line) for profiling fixes | Findings should point at code | `--src <repo>`: link resource ids, Compose testTags and strings to source files, so a11y/perf findings show where to fix. | P3 |
| Normalized 0–1 coordinates | Portable across screen sizes | Store normalized bounds alongside pixels in map.json; point taps in exports already use %. | P3 |

Not adopting: Lens design variants (a different product), TV/Electron targets (out of scope for now), and
telemetry (AppScreenMap sends nothing; keep it that way).

## 9. Known limits (v1)

- About 3 s per step with plain `uiautomator dump`; a 300-step crawl takes ~15 min.
- Canvas/game UIs and custom-drawn views expose no hierarchy, so they can't be explored
  (the screenshot is still captured).
- WebView content is only as visible as its accessibility tree.
- Screen identity is heuristic. Tune `similarity`; occasional over-splitting or merging is expected.
- Apps that check for root/emulator, or that need OTP/2FA, need a dev build or test hooks.
