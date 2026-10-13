<p align="center">
  <img src="docs/media/appscreenmap-mark.svg" alt="AppScreenMap" width="96" height="96">
</p>

<h1 align="center">AppScreenMap</h1>

<p align="center">
  <strong>Every screen of your app, mapped by an agent, not by hand.</strong><br>
  Point it at a build and an emulator or simulator. It taps through the app on its own and gives you<br>
  a map of every screen, how to reach it, tests that jump straight there, and an audit of each one.
</p>

<p align="center">
  <a href="https://github.com/MKS-01/appscreenmap/actions/workflows/crawler.yml"><img src="https://github.com/MKS-01/appscreenmap/actions/workflows/crawler.yml/badge.svg" alt="Crawler CI"></a>
  <a href="https://github.com/MKS-01/appscreenmap/actions/workflows/web.yml"><img src="https://github.com/MKS-01/appscreenmap/actions/workflows/web.yml/badge.svg" alt="Web viewer CI"></a>
  <img src="https://img.shields.io/badge/Android-0a0a0a?style=flat-square&logo=android&logoColor=white" alt="Android">
  <img src="https://img.shields.io/badge/iOS_Simulator_(beta)-0a0a0a?style=flat-square&logo=apple&logoColor=white" alt="iOS Simulator, beta">
  <img src="https://img.shields.io/badge/Python_3.11+-0a0a0a?style=flat-square&logo=python&logoColor=white" alt="Python 3.11 and up">
  <a href="https://maestro.mobile.dev"><img src="https://img.shields.io/badge/Maestro_flows-4da3ff?style=flat-square" alt="Exports Maestro flows"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/MIT-0a0a0a?style=flat-square" alt="MIT License"></a>
</p>

<p align="center">
  <a href="#why-appscreenmap">Why</a> &nbsp;·&nbsp;
  <a href="#getting-started">Run it</a> &nbsp;·&nbsp;
  <a href="#web-viewer">Viewer</a> &nbsp;·&nbsp;
  <a href="#commands">Commands</a> &nbsp;·&nbsp;
  <a href="#how-it-works">How it works</a> &nbsp;·&nbsp;
  <a href="docs/MAP_SCHEMA.md">Map format</a>
</p>

<p align="center"><sub>Deterministic crawler, no model calls. Plain files out. Early alpha.</sub></p>

---

AppScreenMap installs your app, taps through it (buttons, tabs, lists, scrolling, forms) and writes down
what it finds: every screen, every transition between them, and the UI patterns on each. Ask a coding agent
to run it and it checks the result, tunes and re-crawls when something looks off, then leaves you a
browsable map, test flows, and accessibility and performance findings.

<p align="center">
  <img src="docs/media/map-tree.png" alt="The viewer's Tree map of DuskRead: each screen shown whole, under the screen it was found from, connected by the taps that led there">
</p>

## Why AppScreenMap

Knowing what's in a mobile app is still manual work: someone taps through every screen to take screenshots,
writes a test per path, runs an accessibility scanner screen by screen, profiles the slow bits, and does it all
again for the next release. **One crawl does all of it, in one package.** Every answer comes from the same map:

| You want to know | Usually | With AppScreenMap |
|---|---|---|
| What screens does the app have, and how do you reach each one? | Tap around, screenshot, draw a flow chart | A map of every screen, with its screenshot, hierarchy, patterns and the taps that lead there |
| Can tests reach every screen? | Write a flow per screen by hand | A [Maestro](https://maestro.mobile.dev) flow per screen, generated |
| Did the new build break or change anything? | Manual regression pass | `verify` replays every path (CI exit codes); `diff` shows changed pixels and text |
| Is it accessible? | A scanner, one screen at a time | A WCAG 2.2 report across every screen, with fixes, screenshots and triage |
| Which screens are slow or janky? | A profiler session per suspect | Load time, jank and cold start for every navigation |
| How does an agent learn the app? | It explores again, every session | It asks the map over MCP: "how do I reach Settings?" |

And it stays practical:

- **Deterministic, local, no model calls.** Same build and settings give the same map, so a regression is a
  diff, not noise. It runs on your machine with no cloud service.
- **Plain files.** `map.json` plus images: read them in the viewer, your scripts, CI, or an agent.
- **Safe by default.** The crawl stays inside the app, never taps log out, delete or pay, and test passwords
  can be `${ENV}` placeholders that never reach the output.
- **Agent-ready.** Ask a coding agent to "map my app and review it": the repo ships [skills](.claude/skills/)
  so it knows how to crawl, review the result, audit the app and tune the crawler.
- **Android and iOS, one format.** The same explorer, map, viewer and reports for an Android emulator or device
  and the iOS Simulator.

## Getting started

```bash
git clone https://github.com/MKS-01/appscreenmap && cd appscreenmap
uv sync
uv run appscreenmap doctor                       # checks adb, devices, simulators, idb, aapt2, viewer build
uv run appscreenmap crawl --apk path/to/app.apk  # Android: install + map
uv run appscreenmap serve                        # browse the result
```

Already installed? `crawl --package com.example.app --clear-data` maps it from a clean first-run state.
Or have your agent do it: *"Map my app on the emulator and review the map."*

**iOS Simulator (beta).** Build the app for the simulator (`xcodebuild -sdk iphonesimulator`; an `.ipa` is
device-signed and won't run there), boot a simulator, then:

```bash
uv run appscreenmap crawl --platform ios --app path/to/YourApp.app --clear-data   # runs go to runs/<app>-ios/
```

| | |
|---|---|
| **Python** | 3.11 or newer, with [uv](https://docs.astral.sh/uv/) |
| **Android** | Platform-tools (`adb`) and a running emulator or USB device |
| **iOS** | macOS with Xcode, a booted simulator, and [idb](https://fbidb.io): `brew install facebook/fb/idb-companion` and `uv tool install fb-idb` |
| **Optional** | `aapt2` (build-tools) for activity coverage; [Bun](https://bun.sh) to rebuild the viewer; [Maestro](https://maestro.mobile.dev) to run the flows |

A crawl looks like this:

```
🗺  mapping DuskRead 1.2.0 on sdk_gphone16k_arm64 → runs/duskread/duskread-20261013-015149
  ↻ restart app (start)
  ★ new screen s001: 'DuskRead' [MainActivity] form
  ⌨ filled 1 field(s): EditText
[  2] s001 · click 'Get started'
  ★ new screen s002: 'Hello, test' [MainActivity] list,bottom_nav
…
✔ nothing left to explore
✔ 11 screens, 36 transitions, 0 crashes, 95 steps in 350s
```

### Platform support

| | Android (emulator or device) | iOS Simulator (beta) |
|---|---|---|
| Map, screenshots, patterns, form filling | ✅ | ✅ from the accessibility tree |
| Stays inside the app | ✅ lock task pinning | ✅ enforced by the explorer (restarts the app if it leaves) |
| Maestro flows, `diff`, `report`, viewer, MCP map queries | ✅ | ✅ |
| WCAG 2.2 checks and report | ✅ | ✅ (iOS-specific rules next) |
| Resize-text crawl (`--font-scale 2.0`) | ✅ font scale | ✅ Dynamic Type |
| Crash capture | ✅ logcat | ✅ DiagnosticReports |
| Load time, jank, cold start | ✅ | not yet |
| `verify` on a new build, MCP `where_am_i` / `go_to_screen` | ✅ | not yet |

On iOS the crawler sees what VoiceOver sees: a control with no accessibility label isn't in the tree, so it
can't be tapped, and that is itself a finding. Setup and debugging: the
[`ios-simulator` skill](.claude/skills/ios-simulator/SKILL.md); status: [roadmap §8.3](docs/PLAN.md#83-ios-started).

### Sample apps

The samples in [`samples/`](samples/) ship with their crawl results committed, so the viewer works straight
after a clone: the **Playground**, built so every screen triggers a known feature (with v1 and v2 builds for
release comparisons), and **DuskRead**, a real Kotlin Multiplatform app, crawled on Android (Compose) and on
the iOS Simulator (SwiftUI).

```bash
uv run appscreenmap serve      # browse the committed sample maps
samples/demo.sh                # re-run every scenario (~25 min; includes iOS when a simulator is booted)
samples/demo.sh ios            # only DuskRead on the iOS Simulator (builds the .app on first use)
```

## Web viewer

`appscreenmap serve` opens a viewer for your `runs/` folder. It has no backend and updates live while a
crawl runs.

<p align="center">
  <img src="docs/media/home.png" alt="The viewer's home page: totals across all runs, a prompt to ask your agent to map an app, and a card per app with a strip of its screens, the latest run's stats and links to each view">
</p>

- **Map** in three layouts (Tree, Graph, Storyboard), each screen shown whole at the device's shape. Click one
  to light up its path from launch.
- **Screens**: search titles, element text and resource-ids; per-screen detail with tappable element
  overlays, transitions, the Maestro flow and the raw hierarchy.
- **Crawl replay**: step through the crawl to see what was tapped and why.
- **Insights**: one dashboard of audits (accessibility, performance, stability, coverage and release
  readiness), scored and sorted by what needs you first.
- **Accessibility** findings to triage and export, and **Compare** for diffs between builds.

<p align="center">
  <img src="docs/media/insights.png" alt="The Insights page for the Playground sample: device details, totals for screens, transitions, errors and warnings, and a list of audits with error, warning and info counts and a score for each">
</p>

Stars, notes and triage decisions are saved next to the run (`notes.json`), so they travel with it. To work
on the viewer: `cd web && bun install && bun run dev` (see [`web/README.md`](web/README.md) and
[`web/DESIGN.md`](web/DESIGN.md)).

## Commands

| Command | What it does |
|---|---|
| `doctor` | Check adb, devices, booted simulators, idb, aapt2 and the viewer build |
| `crawl --apk app.apk` / `--platform ios --app X.app` / `--package id` | Explore the app and write `runs/<project>/<run-id>/` |
| `serve` | Open the web viewer on `runs/` |
| `report <run>` | Health check: wasted taps, near-duplicate screens, navigation failures, and device conditions that skew results |
| `a11y <run> [--report]` | WCAG 2.2 checks; `--report` rebuilds `a11y-report.html` and `.md` (also written after every crawl) |
| `perf <run> [--budget 1000]` | Load time per screen, slowest transitions, jank, cold start |
| `diff <base> <candidate>` | Match screens across two runs and diff pixels and text |
| `verify <run> [--apk new.apk]` | Replay every screen's path on a new build; exit 1 when one breaks ([CI](#ci-verify-a-new-build)). Android for now |
| `export <run>` | Regenerate Maestro flows and the Mermaid graph |
| `mcp` | Serve the maps to coding agents ([Agents](#agents-mcp)) |

All run as `uv run appscreenmap <command>`; `<run>` is a run folder such as `runs/duskread/<run-id>`.
Useful `crawl` flags: `--clear-data` (first-run state), `--max-steps`, `--max-minutes`, `--font-scale 2.0`
(WCAG 1.4.4 resize-text crawl), `--keep-animations` (load times as users see them), `--serial` (device serial
or simulator UDID), `--config appscreenmap.toml`.

## Accessibility report

<p align="center">
  <img src="docs/media/a11y-report.png" alt="The generated accessibility report for the Playground sample: app and device details, a summary of how many of the 55 WCAG 2.2 criteria fail, have issues, need review, are clean or are not tested, then findings grouped by success criterion with the fix">
</p>

Every crawl writes `a11y-report.html` (self-contained, easy to attach to a ticket) and an `.md` twin,
organised by **WCAG 2.2 success criterion** rather than as a flat list:

- **A status for every A and AA criterion.** A criterion that needs a person or a device shows as *Not tested*,
  never as a pass. The report is evidence, not a conformance claim.
- **Findings with the fix and the screenshot**, naming the Compose or View API to change where there is one.
- **The criteria new in WCAG 2.2**: target size (2.5.8), dragging (2.5.7), focus not obscured (2.4.11),
  consistent help (3.2.6), redundant entry (3.3.7) and accessible authentication (3.3.8), plus label in name,
  roles, consistent navigation, orientation, truncated text and image alternatives.
- **Triage feeds the report.** Mark findings Needs fix, Won't fix or False positive in the viewer; confirmed
  ones are included.

Automated checks catch only part of WCAG. The [`a11y-audit` skill](.claude/skills/a11y-audit/SKILL.md) covers
the device and manual tests (rotation, keyboard, TalkBack) a crawl can't do; for iOS apps,
[`ios-a11y-rules`](.claude/skills/ios-a11y-rules/SKILL.md) maps WCAG to VoiceOver, Dynamic Type and Apple's 44 pt
targets, with the SwiftUI and UIKit fix for each.

## Performance

Rather than sleeping a fixed time after each tap, the crawler waits until the app stops drawing
(`dumpsys gfxinfo`), so every transition gets a **load time**, **janky and frozen frames**, and a note if a
loading spinner was still showing. Cold start is recorded on every relaunch.

```
$ uv run appscreenmap perf runs/playground/<run-id> --budget 1000
Navigation performance for playground-v1-20261013-031007 (budget 1000 ms, animations off)
  cold start: 151 ms median, 161 ms max over 11 launch(es)
  screens, slowest first (median / p90 / max ms, samples):
   🔴  s018 'Reports'            2770 / 2770 / 2770  ×1  loading indicator, never settled
   🟠  s019 'Gallery'            1825 / 1825 / 1825  ×1  97.8% janky
   🟢  s013 'Terms of use'        332 /  360 /  360  ×2  26.8% janky
   🟢  s005 'Article'             214 /  225 /  228  ×8
  findings:
    • s018 'Reports' loads in 2770 ms (median, budget 1000 ms)
    • s018 'Reports' never stopped drawing within the timeout (continuous animation or polling UI)
    • s019 'Gallery' renders janky: 97.8% slow frames
```

The same numbers are in `perf.json` and the MCP `perf_summary` tool. Animations are off during a crawl for
stable results; `--keep-animations` measures what users see. Android only for now.

## End-to-end tests

Every screen gets a [Maestro](https://maestro.mobile.dev) flow, on Android and iOS, that launches the app fresh,
follows the recorded path (typing into forms on the way) and asserts it arrived. Selectors prefer a resource-id, then
text or content description, and fall back to a position only when nothing else exists.

```yaml
# flows/s003.yaml (excerpt): reach s003 Search
appId: dev.appscreenmap.playground
---
- launchApp:
    stopApp: true
- tapOn: { id: "email" }
- inputText: "demo@playground.dev"
- tapOn: { id: "sign_in" }       # on s001
- tapOn: { id: "tab_search" }    # on s002
- assertVisible: { id: "tab_home" }
```

```bash
maestro test runs/<project>/<run-id>/flows/   # prove every screen is still reachable
```

AppScreenMap writes the files; it doesn't bundle or run Maestro (Apache-2.0, not affiliated). Maestro is the
only format today; more tools (Appium, Espresso, page objects) are planned behind a plug-in interface, and
`map.json` already has everything a generator needs.

### CI: verify a new build

```bash
uv run appscreenmap verify runs/duskread/<run-id> --apk app-release.apk
```

`verify` replays every screen's path from a fresh launch on the new build (longest paths first; screens
passed along the way count as checked). A path fails when a step's element is gone, or it leads to the wrong
screen, out of the app, or to a crash; screens behind it are reported as blocked. Every screen it reaches is
diffed against the base run.

```
✘ 9 passed, 1 failed, 1 blocked, 0 skipped · 2 visually changed   (1.3.0 vs base 1.2.0)
  ✘ s005 'Settings': 'Settings' is not on s002
      evidence: runs/duskread/<run-id>/verify/verify-…/failed/s009.png
  ⊘ s009 'Connect Notion': blocked by s005
  ≠ s002 'Hello, test': 0.84% pixels; text 1 changed
```

Exit codes: `0` all paths work, `1` a path broke (or a screen changed, with `--fail-on-change`), `2` bad
arguments. `--update-baselines` accepts the new look. Paths that can't work from a fresh launch even on the
base build (reached through app state, such as a running timer) are skipped with a note, not failed.

## Agents (MCP)

`appscreenmap mcp` serves your `runs/` to MCP clients such as Claude Code, so an agent can ask "how do I
reach X", "where am I" or "which screens fail WCAG" instead of exploring the app again.

```bash
claude mcp add appscreenmap -- uv run --directory /path/to/appscreenmap appscreenmap mcp
# options: --runs <dir> (default ./runs), --run <run-id> (default: latest finished), --serial <device>
```

| Tool | Answers |
|---|---|
| `list_runs`, `list_screens`, `find_screens` | What has been mapped; which screen is "Settings" or has a "Save" button |
| `get_screen`, `screenshot` | One screen: elements and where each leads, how to reach it, findings, load time, image |
| `route` | Steps to a screen, from launch or another screen (with the Maestro flow) |
| `where_am_i`, `go_to_screen` | Which screen the device shows now; drive it to another one |
| `a11y_findings`, `perf_summary` | Which screens fail which WCAG 2.2 criteria; which are slow |
| `crawl`, `crawl_status` | Map an app (or a new build) in the background |

## How it works

<p align="center">
  <img src="docs/media/how-it-runs.png" alt="The crawl loop on the viewer's How it works page: five steps (launch, observe, identify, act, record), with the Observe step showing the elements found on a real Playground screen">
</p>

The viewer's **How it works** page walks through this loop on your own latest run.

1. **Observe**: dump the UI hierarchy (the accessibility tree on iOS) and screenshot, and read the foreground
   activity.
2. **Identify**: fingerprint the layout, ignoring list contents and digits (clocks, counters).
   Near-identical screens merge by similarity.
3. **Act**: pick the next untried element: bottom nav → tabs → buttons → scroll → list rows → toggles → back.
4. **Record** the transition and repeat. When a screen is exhausted, route back to the nearest screen with
   untried actions over the graph built so far, relaunching if needed.
5. **Stop** when nothing is left, the map saturates, or the budget runs out.

Along the way it:

- **Stays inside the app.** On Android the app is pinned (lock task mode), so BACK at the root or a link to
  another app can't leave it. iOS has no pinning, so the explorer treats any screen owned by another process
  (Safari, an in-app browser, a system sheet) as leaving. Either way it relaunches the app and never repeats
  that action.
- **Learns list patterns.** If the first rows of a list open the same kind of screen, the rest are skipped;
  menus whose rows go to different places are fully explored.
- **Infers navigation.** A bottom-nav item that opens *Saved* from one screen is assumed to do so everywhere
  (recorded as an inferred edge).
- **Fills forms** from regex rules (email, password, phone, …) so login walls work.
- **Won't tap dangerous things**: log out, delete, pay, subscribe, uninstall, call… (configurable).
- **Handles system UI**: permission dialogs are allowed, crashes are recorded (logcat on Android, crash reports
  on iOS).

<p align="center">
  <img src="docs/media/architecture.svg" alt="The crawler talks to an emulator or device and writes a run folder of map.json, screenshots and traces. The web viewer, exporters, reports and CI checks, and the MCP server all read that folder">
</p>

A small Python crawler drives the device: the **driver** (`adb` on Android, `simctl` + `idb` on the iOS
Simulator) dumps hierarchies, takes screenshots and sends taps; the **analyzer** turns a hierarchy into elements, a fingerprint and UI patterns; the
**explorer** picks the next action and records the transition. The iOS driver translates the accessibility tree
into the same hierarchy format, so the analyzer and explorer are shared. Everything else (the viewer, exporters,
reports, `verify` and the MCP server) only reads the run folder, which is why `map.json` is the contract in
[`docs/MAP_SCHEMA.md`](docs/MAP_SCHEMA.md). The design and roadmap are in [`docs/PLAN.md`](docs/PLAN.md).

## Configuration and secrets

Every option is in [`examples/appscreenmap.toml`](examples/appscreenmap.toml). Values the crawler types are
recorded so flows can replay them, so keep real credentials out by naming an environment variable:

```toml
[inputs]
"e-?mail|user" = "qa.tester@example.com"
"pass" = "${APP_PASSWORD}"
```

The crawler types the value of `APP_PASSWORD` but writes only `${APP_PASSWORD}` to `map.json` and the flows
(`maestro test -e APP_PASSWORD=… flow.yaml` fills it there). `crawl` and `verify` stop if a variable is unset,
and the crawl warns when it types a plain-text password.

## Output

```
runs/
  index.json                  all runs, newest first, grouped by project
  <project>/<run-id>/         e.g. runs/duskread/duskread-20261013-015149/
    map.json                  screens, elements, transitions, events, stats (live during the crawl)
    trace.jsonl               one line per step
    screens/                  s001.png (full), s001.jpg (thumbnail), s001.xml (hierarchy)
    flows/s001.yaml           Maestro flow: launch → … → assert this screen
    map.mmd                   Mermaid flowchart
    a11y.json, a11y-report.*  WCAG 2.2 findings and report
    perf.json                 load times, jank, cold start
    crashes/                  logcat for each crash
    diff/<base-run>/          diff against another run (written by `diff`)
    verify/<verify-id>/       replay results on a new build (written by `verify`)
```

Runs are grouped per project (`--project`, default: the last part of the package name; iOS runs add `-ios`, so
they never mix with the Android runs of the same app). The `runs/` folder is committed, so the repo ships sample
maps of the Playground and DuskRead (Android and iOS).

## Project layout

```
src/appscreenmap/   crawler: drivers (Android, iOS Simulator), analyzer, explorer, model, export,
                    visual diff, a11y, perf, replay + verify, MCP server, CLI
web/                web viewer (React + Vite, built with Bun)
design/             tokens.css: colour, type, space and motion for the viewer and reports
samples/            Playground and DuskRead APKs, sources, iOS build script and demo.sh
runs/               committed sample crawls
docs/               PLAN.md (design + roadmap), MAP_SCHEMA.md (data contract)
examples/           sample config
tests/              unit tests on synthetic hierarchies (no device needed)
```

```bash
uv sync && uv run pytest -q
uv run ruff check src tests && uv run ruff format src
```

## Prior art

AppScreenMap builds on ideas from [DroidBot](https://github.com/honeynet/droidbot) (UI transition graphs),
[Fastbot](https://github.com/bytedance/Fastbot_Android) and [APE](https://github.com/tianxiaogu/ape)
(model-based exploration and state abstraction), Firebase Robo, and
[Maestro](https://github.com/mobile-dev-inc/maestro) (flow format). See
[docs/PLAN.md](docs/PLAN.md#2-prior-art-what-we-borrow).

## Contributing

Issues and PRs are welcome. Start with [CONTRIBUTING.md](CONTRIBUTING.md); the data contract is
[`docs/MAP_SCHEMA.md`](docs/MAP_SCHEMA.md). Please follow the [code of conduct](CODE_OF_CONDUCT.md) and
report security problems privately ([SECURITY.md](SECURITY.md)).

**A note on privacy:** a crawl records what it types into forms and screenshots whatever the app shows. Use
throwaway test accounts and review `runs/` before you commit or share it.

## License

[MIT](LICENSE) © 2026 MKS and AppScreenMap contributors. Third-party notices (including the Lucide-derived
icons in the viewer) are in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

<p align="center">
  <sub>Early alpha: expect rough edges, and tell us about them</sub><br>
  <sub>Built agent-first with <a href="https://claude.ai/code">Claude Code</a></sub><br>
  <sub>DuskRead, one of the sample apps, is <a href="https://github.com/MKS-01/duskread">a separate project</a> by the same author</sub>
</p>
