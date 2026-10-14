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
| 3. iOS | **After Android is solid.** Simulator driver (`driver_ios.py`: `simctl` + `idb`, started Oct 2026), same map format and viewer. sample-app is the iOS sample. See §8.3 | 🚧 `crawl --platform ios` works on a simulator (sample-app); perf, permissions, iOS a11y rules next |
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

### 8.3 iOS (started)

**Sample: sample-app.** It has a real SwiftUI iOS target (`iosApp/` in the sample-app repo, KMP shared core), builds
for the simulator with `xcodebuild -sdk iphonesimulator`, and is the owner's own code, so every issue the crawl finds can
be fixed at the source and re-crawled to prove the tool works. No separate "Playground iOS" for now. A simulator needs a
`.app` from an iphonesimulator build: an `.ipa` is device-signed and won't run there (the driver says so).

**How it drives a simulator.** `simctl` boots, installs, launches, terminates, screenshots and grants permissions; `idb`
(`idb_companion` + the `fb-idb` client) reads the accessibility tree and sends taps, swipes and text, which `simctl` can't
do. `ios_hierarchy.py` translates idb's tree into the uiautomator-style XML the analyzer already reads (class names the
analyzer keys on, `resource-id` from the accessibility identifier, `bounds` in points, off-screen nodes dropped), so the
explorer, exporters and viewer work unchanged. Measured: tree dump 0.5 s (Android: ~2 s). Coordinates are points; the
screenshot is native pixels and the viewer scales by ratio, as it does between Android densities.

**Done:** driver, translator, `doctor` checks, `crawl --platform ios --app X.app`, 14 tests (a real sample-app tree recorded
as `packages/drivers/tests/fixtures/`), and live crawls of sample-app on an iPhone 17 simulator: 7 screens, 15 transitions, 43 steps in 86 s,
Maestro flows and the a11y audit written, then "nothing left to explore" (the tab bar is invisible to the tree; see below).
How the Android-shaped explorer maps onto iOS:
- *App lock.* No scriptable pinning on iOS, so the explorer enforces it: any tree whose owning process (matched by pid
  against `launchctl`) is not the app is an external screen, and an empty tree (in-app browser, system sheet) is reported as
  `ios.external`; either way the crawl restarts the app, never presses Back into another app. Observed: a link that opened
  Safari was recorded as `x:com.apple.mobilesafari` and the crawl restarted.
- *Back.* iOS has no Back key; `back()` is the edge swipe, used only inside the app.
- *Data.* `--clear-data` empties the app's data container (no reinstall); the simulator-wide keychain is left alone.
- *Text size.* `--font-scale 2.0` sets Dynamic Type to `accessibility-large` (the WCAG 1.4.4 crawl).
- *Crashes.* A report newer than the crawl's mark in `~/Library/Logs/DiagnosticReports/<Executable>*.ips` is read as the
  crash log (first line `Process: <bundle>,` so the explorer's check works unchanged).
**Not yet:** load times (no frame counters wired; the Performance audit says so), system permission alerts (SpringBoard
runs them outside the app's tree; `simctl privacy grant all` covers the common ones), physical devices, a crash *dialog*
(iOS has none), and the iOS-specific accessibility rules (VoiceOver names, 44 pt targets per Apple HIG, Dynamic Type at the
largest size) beside WCAG.

**What the first look at sample-app found** (to fix in the app, then re-crawl to confirm):
1. *Floating bottom bar has no accessibility.* `Shell/FloatingBar.swift` draws four icon buttons (Home, Following, Saved,
   player) with no label, trait or identifier: they are absent from the accessibility tree, so VoiceOver can't reach them
   and the crawler can't tab between sections.
2. *Settings "×" close button is unlabeled*, so it's missing from the tree too: nothing to tap to leave the screen.
3. *No accessibility identifiers anywhere* (0 in `iosApp/`; 3 labels): no stable ids for screen identity or Maestro `id:` selectors.
4. *No heading traits.* 0 `.isHeader` in `iosApp/`: section titles (VOICE, NOTION, APPEARANCE) are plain text for the
   VoiceOver Headings rotor. Plus 23 touch targets under 44 pt on Home alone.
5. *Cards open an in-app browser* (SFSafariViewController): its content is out of process, so the tree is one node.
   Expected, but the crawler must record it as leaving the app.
6. *Crawler side, fixed:* "Erase everything on this device" (Settings → Reset) wasn't in the default `blocked_text`; added
   `erase`, `wipe`, `reset all/app/data/device`, `clear data`, with a test.

### 8.4 Security audit: depth (planned)

The rule catalogue is set up (`packages/security/src/appscreenmap/security/rules.json`, 14 rules, documented in the `security-rules` skill; the
workflow is the `security-audit` skill). Every rule is `planned`, so the Insights Security page says "not set up" and lists
them. This section is how the scanner goes deeper than a manifest check, from two kinds of evidence.

**Build analysis** reads the artifact and never runs it, so it works in CI on any build, with no device:

| Layer | Android (APK/AAB) | iOS (.app/.ipa) | Output |
|---|---|---|---|
| Identity and config | `aapt2 dump xmltree` / `badging`: exported components, intent filters (deep links, `autoVerify`), permissions, `debuggable`, `allowBackup`, `usesCleartextTraffic`, network security config | `Info.plist`: ATS exceptions, URL schemes, usage-description strings; entitlements (`get-task-allow`, keychain groups, associated domains) | `manifest.json` |
| Signing | `apksigner verify --print-certs`: scheme v2/v3, debug or expired certificate | `codesign -d --entitlements :-`, provisioning profile type (development vs distribution) | `signing.json` |
| Code | `jadx -d out`: the static rules (secrets, WebView bridge, TLS validation, weak crypto, logging); `apkanalyzer` for dex/method counts, R8 mapping present or not | `strings`, `otool -L` (linked frameworks), `otool -hv` (PIE), symbol checks for stack canaries and ARC | `findings` with file and line |
| Native and bundled files | `.so` libraries (stripped? hardening flags), assets and `res/raw` with keys, certificates, databases | embedded frameworks and their versions, bundled plists, `.p12`/`.pem` files | `inventory.json` |
| Dependencies | library list from dex packages and `META-INF`; match versions against a vulnerability database (OSV) | frameworks and Swift packages from the bundle | `sbom.json` + advisories |
| Store hygiene | target/min SDK, Data safety vs the SDKs found | privacy manifest, required-reason APIs, SDK signatures | feeds *Store readiness* |

**Crawl-driven analysis** needs the app running, and the crawl is what makes it deep: it reaches the screens, flows and states
a static scan can't, while recording everything it passes through.

| Signal | How the crawl gets it | Finding |
|---|---|---|
| Data at rest | after the crawl, read the data container (Android `run-as` on debuggable builds; iOS `simctl get_app_container … data`): `shared_prefs`, databases, plists, plain files | `secrets-at-rest` |
| Network seen | route the device through a local proxy (emulator `-http-proxy`, simulator system proxy) while crawling; record hosts, schemes, TLS version, certificate errors | `cleartext-observed`, `no-cert-pinning`, plus a "who does this app talk to" list (first-party vs third-party hosts, a privacy signal) |
| Logs during the run | tail `logcat` / the simulator's unified log for the whole crawl and scan for tokens, passwords, personal fields | `sensitive-logging` (dynamic confirmation of the static rule) |
| Sensitive screens | every screen with a password, OTP or payment field: was the screenshot capturable? On Android a screen with `FLAG_SECURE` returns black from `screencap`; a clear capture means the screen can be recorded or shown in Recents | new rule `no-secure-flag` |
| Reachable surface | for each exported activity and deep link in the manifest, launch it from the crawl's root state (`am start`, `simctl openurl`) with no extras and with malformed input; record where it lands (a post-login screen without logging in, a crash) | `exported-component` becomes confirmed, new rule `deeplink-crash` |
| WebViews | record the URLs a WebView loads and whether the host is first-party; screens that render remote HTML | `webview-js-interface` becomes confirmed or dismissed |
| Permissions timeline | which runtime permissions were requested on which screen, and whether the crawl was still useful when each was denied | privacy review, `permission-before-use` candidate |
| Crashes and ANRs | already recorded (`crashes/`); a crash from untrusted input is a finding, not just a stability number | feeds *Stability* and `deeplink-crash` |
| Stored credentials | the values the crawler typed are placeholders in `map.json`; assert none of the real values appear in any saved file (hierarchy XML, logs, screenshots metadata) | a self-check, never a finding about the app |

**How they combine.** A finding carries its evidence: a static match is a *candidate*, a crawl observation *confirms* or
*dismisses* it ("`addJavascriptInterface` found" + "WebView loaded only `https://app.example`" = low risk). Output goes to
`runs/<project>/<run>/security/` (`manifest.json`, `signing.json`, `sbom.json`, `network.jsonl`, `evidence/`) and a summary
`audits/security.json`, so the viewer's page, `report` and the MCP tools read one file.

**Build order, cheapest first:**
1. Manifest and Info.plist rules from `apkinfo.py`'s aapt2 calls and a plist read (6 rules; needs no device).
2. `secrets-at-rest` from the data container the drivers already resolve; logs-during-crawl scan.
3. Signing, SBOM and dependency advisories (OSV) from the build.
4. jadx static rules with fixture tests (`hardcoded-secret`, TLS, WebView, crypto, logging).
5. Proxy-observed network and `no-secure-flag` during a crawl; reachable-surface checks (exported components, deep links).
6. frida for what the proxy can't see (certificate pinning, in-process hooks): last, because it needs a prepared target.

**Tools to evaluate before building our own:** MobSF (static + dynamic mobile scanner, could be driven for a second
opinion), semgrep rules for Android and Swift, OSV-Scanner for dependencies, mitmproxy for the proxy step, `apkanalyzer` and
`apksigner` from the Android SDK. Prefer small direct checks we can test with fixtures over wrapping a large tool.

**Rules:** only official sources back a rule (`security_rules.py` rejects any other host); a scan that skipped a category must
say so in `summary` and `metrics`, never read as a pass; findings never include a secret's value or exploit steps. Only run
against builds you own or are authorised to test (`security-audit` skill).

## 9. Todo

Next features, first batch. Unchecked means not started; the open questions need a decision before design.

- [ ] **Run history and versions.** Several runs of one app should read as a history, with the latest shown
  first. Open: how runs group (by package, by version, by device), and whether the viewer defaults to the
  newest run per project with older ones behind a history list. Touches `runs/index.json` and the Runs view
  (`apps/viewer/`).
- [ ] **Adaptive UI review and guidelines.** Check how screens adapt across window sizes and
  orientations (phone, tablet, foldable; compact / medium / expanded width classes) against Android's
  adaptive-layout guidance. Likely builds on the condition matrix in §8.2 (landscape, display size).
  Open: which guidelines to encode as checks, and whether findings sit with the Accessibility tab or get
  their own.
- [x] **Better Insights.** ✅ viewer: Insights is now an audit framework (`apps/viewer/src/insights/`). Every audit uses
  one report shape: score, metrics, declarative charts, findings with severity, platform, deadline and official
  refs. Any tool can add or replace an audit by writing `audits/<id>.json` into the run folder (`docs/MAP_SCHEMA.md`).
  Built from real run data: crawl coverage, stability, accessibility (a11y.json), performance (perf.json).
  Overview: an audit card per audit, findings by audit, a store/platform deadline timeline, run history (small
  multiples) and the device/OS strip. Official sources live in one catalogue (`apps/viewer/src/insights/sources.ts`).
- [ ] **Audits that still show sample data** (labelled "sample data" in the viewer; "Show sample audits" hides them):
  - **Adaptive UI.** Real today: manifest orientation locks and the crawl's window class. Next: crawl at 600
    and 840 dp (resizable emulator or tablet AVD), then check layouts per window size class.
  - **Platform changes.** Each year's Android behavior changes (now Android 17, API 37) and iOS device changes,
    matched against what the app uses (manifest permissions, APIs it references).
  - **Store readiness.** Read target/min SDK from the APK (`aapt2`), check Google Play's target API deadline
    and App Store build SDK and screenshot requirements. Crawl screenshots can seed store screenshots.
  - **Security.** Rules and skills are set up (§8.4); next is the scanner. `appscreenmap security <run>`: jadx static scan (secrets, WebView, reflection), manifest
    review (exported components, cleartext, backup), frida dynamic checks (pinning, root detection).
  - Each one ships by writing `audits/<id>.json` from the crawler; the viewer's sample builder is then deleted.
  - Yearly upkeep: after each Android / iOS release and store policy update, refresh `sources.ts` and the
    platform and store checks.
- [ ] **Device and OS details.** Show where each run and each screenshot was captured: model, manufacturer,
  Android version and SDK, resolution, density, font scale. ✅ crawler: `run.device` now records device type
  (emulator / physical), display name, brand, AVD name, form factor, OS build and vendor skin, hardware,
  display in dp and window class, the settings that change what an app shows, WebView and Play services
  (`device.py`, documented in `docs/MAP_SCHEMA.md`); `report` prints it with device caveats. Open: a Device
  section in the viewer (`apps/viewer/`), and per-screenshot capture once locale or condition runs exist (one run,
  several captures).
- [ ] **Versions and flows per app** (designed: canvas "AppScreenMap redesign", boards *App · versions + compare*
  and *App · flows + crawl rules*). An app page with a version timeline (newest first, runs under each version,
  deltas between runs) and a version compare (screens added / removed / changed, metric deltas, per flow).
  Flows: auto-detected by default (the entry flow before the home screen, then one per top-level destination,
  each the discovery subtree under it) plus your own (start → end screen, path found from the map). Each flow
  can carry a crawl rule: `explore` (default) | `first` | `must-reach` | `skip`, saved as `[[flows]]` in
  `appscreenmap.toml`. A new `app-flows` skill documents detection, definitions and the rule format.
- [ ] **Run flows as automation with Maestro, and replay them from the dashboard** (next, after flows).
  Decision: **Maestro runs the flows; AppScreenMap writes and reads them.** Maestro already gives us a runner for
  Android emulators/devices and iOS simulators, assertions (`assertVisible`, `assertNotVisible`), env inputs
  (`-e KEY=…`), JUnit output for CI and Maestro Studio, and the flows stay usable without AppScreenMap (no lock-in).
  Our own `Replayer` stays for crawling and `verify`'s screen-identity checks, which need the map.
  1. **Fix the export first.** Flows tap by resource id even when the id isn't unique on the screen: on Playground's
     Profile all 9 rows are `profile_row`, so the flow to Feedback taps the first row (Account settings), not Help.
     Use id + text when the id repeats (`tapOn: { id: "profile_row", text: "Help" }`), with a regression test.
  2. **Flow → Maestro YAML.** Each flow (auto or yours) exports to `flows/flow-<slug>.yaml`: launch, reach the start
     screen, every step to the end, an `assertVisible` + `takeScreenshot` per screen, `${ENV}` inputs. Optional
     extra assertions per flow (text visible, element enabled) set in the viewer or `[[flows]]`.
  3. **Run and read back.** `appscreenmap run-flow <run> --flow "Report a problem" [--serial …]` shells out to
     `maestro test` (JUnit + debug output into `flowruns/<id>/`), then matches each step's screenshot and hierarchy
     to map screens and writes `flowruns/<id>/flowrun.json` (expected vs. actual screen, pass / fail / changed,
     timings), documented in `docs/MAP_SCHEMA.md`. `doctor` checks that Maestro is installed.
  4. **CI.** Teams can run `maestro test flows/` directly; `verify --flows` runs every `must-reach` flow on a new
     build and exits 1 on a break. Ties into versions: a flows × versions pass/fail matrix on the app page.
  5. **Dashboard.** *Watch*: play a finished flow run like Crawl replay (expected vs. actual screenshot per step,
     where it diverged). *Run on device*: a button that asks `appscreenmap serve` to run `maestro test` on the
     connected device and follows `flowrun.json` live. New local endpoint (`POST /api/flowruns`), off unless
     `serve --allow-device`, localhost only, one run per device, with a confirm step (it taps a real device).
  6. **Agents.** MCP tools `list_flows`, `run_flow`, `flow_status`.
  Open: emulators only for dashboard-triggered runs, or physical devices too.

## 10. Known limits (v1)

- About 3 s per step with plain `uiautomator dump`; a 300-step crawl takes ~15 min.
- Canvas/game UIs and custom-drawn views expose no hierarchy, so they can't be explored
  (the screenshot is still captured).
- WebView content is only as visible as its accessibility tree.
- Screen identity is heuristic. Tune `similarity`; occasional over-splitting or merging is expected.
- Apps that check for root/emulator, or that need OTP/2FA, need a dev build or test hooks.
