# Architecture

How AppScreenMap is put together: the crawl loop, what it does along the way, the audits built on the map, and
what a run folder contains. For setup and commands see [SETUP.md](SETUP.md); for the design rationale and roadmap
see [PLAN.md](PLAN.md); for the data contract see [MAP_SCHEMA.md](MAP_SCHEMA.md).

<p align="center">
  <img src="media/architecture.svg" alt="The crawler talks to an emulator or device and writes a run folder of map.json, screenshots and traces. The web viewer, exporters, reports and CI checks, and the MCP server all read that folder">
</p>

A small Python crawler drives the device. **The crawler makes no model calls**: the same build and settings give the
same map, so a regression is a diff, not noise. An AI agent (Claude Code or any MCP client) sits on top: it runs the
crawler, reads the results and tunes the config, but never improvises the crawl.

| Part | Does |
|---|---|
| **Driver** | `adb` on Android, `simctl` + `idb` on the iOS Simulator: dumps hierarchies, takes screenshots, sends taps, reads the foreground app |
| **Analyzer** | Turns a hierarchy into elements, a screen fingerprint and UI patterns (list, tabs, bottom nav, form, login, dialog, webview) |
| **Explorer** | Picks the next action, identifies the screen, records the transition, routes back over the graph it has built |
| **Model / export** | `map.json` and the files beside it; Maestro flows and the Mermaid graph |
| **Reports** | Accessibility, performance, health, visual diff, `verify` |
| **Viewer / MCP** | The dashboard and the MCP server: both only read the run folder |

The iOS driver translates the accessibility tree into the same uiautomator-style hierarchy the analyzer already
reads, so the analyzer, explorer, exporters and viewer are shared across platforms. Everything outside the crawler
only reads the run folder, which is why `map.json` is the contract in [MAP_SCHEMA.md](MAP_SCHEMA.md).

## The crawl loop

1. **Observe**: dump the UI hierarchy (the accessibility tree on iOS) and a screenshot, and read the foreground
   activity.
2. **Identify**: fingerprint the layout, ignoring list contents and digits (clocks, counters). Near-identical
   screens merge by similarity.
3. **Act**: pick the next untried element: bottom nav → tabs → buttons → scroll → list rows → toggles → back.
4. **Record** the transition and repeat. When a screen is exhausted, route back to the nearest screen with untried
   actions over the graph built so far, relaunching if needed.
5. **Stop** when nothing is left, the map saturates, or the budget runs out.

The viewer's **How it works** page walks through this loop on your own latest run.

Along the way it:

- **Stays inside the app.** On Android the app is pinned (lock task mode), so BACK at the root or a link to another
  app can't leave it. iOS has no pinning, so the explorer treats any screen owned by another process (Safari, an
  in-app browser, a system sheet) as leaving. Either way it relaunches the app and never repeats that action.
- **Learns list patterns.** If the first rows of a list open the same kind of screen, the rest are skipped; menus
  whose rows go to different places are fully explored.
- **Infers navigation.** A bottom-nav item that opens *Saved* from one screen is assumed to do so everywhere
  (recorded as an inferred edge).
- **Fills forms** from regex rules (email, password, phone, …) so login walls work.
- **Won't tap dangerous things**: log out, delete, pay, subscribe, uninstall, call… (configurable).
- **Handles system UI**: permission dialogs are allowed, crashes are recorded (logcat on Android, crash reports on iOS).
- **Measures every navigation** (Android): instead of fixed sleeps it waits until the app stops drawing.

## The audits

**Accessibility.** Findings are organised by WCAG 2.2 success criterion, with the Compose or View API to change
where there is one. It covers the criteria new in 2.2 (target size 2.5.8, dragging 2.5.7, focus not obscured
2.4.11, consistent help 3.2.6, redundant entry 3.3.7, accessible authentication 3.3.8) plus label in name, roles,
consistent navigation, orientation, truncated text and image alternatives. A status is given for every A and AA
criterion, and anything that needs a person or a device is *Not tested*, never a pass. Automated checks catch only
part of WCAG; the [`a11y-audit` skill](../.claude/skills/a11y-audit/SKILL.md) covers the device and manual tests
(rotation, keyboard, TalkBack), and [`ios-a11y-rules`](../.claude/skills/ios-a11y-rules/SKILL.md) maps WCAG to
VoiceOver, Dynamic Type and Apple's 44 pt targets.

**Performance.** Rather than sleeping a fixed time after each tap, the crawler waits until the app stops drawing
(`dumpsys gfxinfo`), so every transition gets a load time, janky and frozen frames, and a note if a spinner never
went away. Cold start is recorded on every relaunch. Animations are off during a crawl for stable results
(`--keep-animations` measures what users see). Android only for now. The same numbers are in `perf.json` and the MCP
`perf_summary` tool.

```
$ uv run appscreenmap-engine perf runs/playground/<run-id> --budget 1000
  cold start: 151 ms median, 161 ms max over 11 launch(es)
   SLOW        s018 'Reports'     2770 / 2770 / 2770  ×1  loading indicator, never settled
   NEEDS WORK  s019 'Gallery'     1825 / 1825 / 1825  ×1  97.8% janky
   ok          s005 'Article'      214 /  225 /  228  ×8
```

**Security** (Android). `appscreenmap security <run>` is a small stdlib-only scanner that takes three kinds of evidence:
the APK (the manifest through one `aapt2` call, plus high-confidence secret formats found by regex over the raw dex,
resource and asset bytes, so there is no decompiling and a scan takes about 0.1 s), the app's data folder over adb
(plain-text secrets in preferences and files), and a log from the observation-only
[Frida hook](../packages/security/src/appscreenmap/security/hooks/frida-observe.js) (plain-HTTP hosts, missing certificate pins).
Findings use the text and official sources of the [`security-rules`](../.claude/skills/security-rules/SKILL.md)
catalogue, never contain a secret's value, and are written to `audits/security.json`, so the Security audit in the
dashboard shows real findings. The [`security-audit` skill](../.claude/skills/security-audit/SKILL.md) tells an agent how
to run and judge it. Rules the scanner doesn't cover yet stay `planned`, and the audit never reads as a pass while any
remain. For builds you own or are authorised to test.

**Network** (Android emulator). `crawl --network` starts `mitmdump` (mitmproxy, an optional external tool) with the
[observation addon](../packages/security/src/appscreenmap/security/hooks/mitm_observe.py), listening on 127.0.0.1 only,
and points the emulator at it (`settings put global http_proxy 10.0.2.2:<port>`). In `observe` mode TLS passes through
untouched, so the app behaves as users see it: HTTPS shows as host and port, plain `http://` in full. The addon writes
metadata-only lines to `network.jsonl` (`packages/security/.../network.py` runs and reads it). The device's proxy setting
is always put back: at the end of the crawl, on an error or Ctrl-C, and at once by a watchdog if mitmdump dies.
`--logs` (on with `--network`) follows the app's own log (`drivers/logcat.py`, `adb logcat --pid`, reattached when the
app restarts) into `logs.jsonl`, masked by `security/applogs.py` before each line is written. Every crawl also writes
`timeline.jsonl`: which screen showed from when, timed at the input that opened it (the explorer wraps the driver to
note each tap, back and launch). At the end, `core/timeline.attribute` gives each row its `screen` and `step`, and
`perf.json` → `network` sums them per screen.

**Manual sessions.** `appscreenmap watch` records the same while a person uses the app by hand. It taps nothing: about
once a second it reads the screen and matches it to the canvas (`crawler/replay.identify`, as MCP `where_am_i` does),
building a timeline; at the end `core/timeline.attribute` ties every log line and request to the screen that was showing.
The session lives in the canvas, under `sessions/<session-id>/`. The dashboard finds all of it through
`GET /api/captures?run=<id>` (`serve`): the run's hosts, log line count and sessions; the rows are the plain files.
The dashboard can also start and stop a session: `POST /api/sessions` runs `watch` as a child process of `serve`
(one at a time, since a device has one proxy setting), and `POST /api/sessions/<id>/stop` sends it SIGTERM, which
`watch` handles like Ctrl-C. Leaving `serve` stops it the same way.

**Your own audits.** Any audit written to `runs/<project>/<run-id>/audits/<id>.json` shows up in Insights, scored
and exportable like the built-in ones (format in [MAP_SCHEMA.md](MAP_SCHEMA.md)).

## Output

```
runs/
  index.json                  all runs, newest first, grouped by project
  <project>/<run-id>/         e.g. runs/playground/playground-v1-20261013-031007/
    map.json                  screens, elements, transitions, events, stats (live during the crawl)
    trace.jsonl               one line per step
    screens/                  s001.png (full), s001.jpg (thumbnail), s001.xml (hierarchy)
    flows/s001.yaml           Maestro flow: launch → … → assert this screen
    map.mmd                   Mermaid flowchart
    a11y.json, a11y-report.*  WCAG 2.2 findings and report
    perf.json                 load times, jank, cold start
    audits/<id>.json          extra audits (security is written by `appscreenmap security`)
    audits/security-evidence.json   the evidence the security audit was built from (apk, device, frida)
    network.jsonl             hosts and requests seen through mitmproxy (`crawl --network`)
    logs.jsonl                the app's own log lines, masked (`crawl --logs`)
    timeline.jsonl            which screen showed from when, timed at each tap: ties network and log rows to screens
    sessions/<id>/            manual sessions (`watch`): timeline, logs, network, each row tied to a screen
    notes.json                your stars, notes and triage decisions
    crashes/                  logcat for each crash
    diff/<base-run>/          diff against another run (written by `diff`)
    verify/<verify-id>/       replay results on a new build (written by `verify`)
```

Runs are grouped per project (`--project`, default: the last part of the package name; iOS runs add `-ios`, so they
never mix with the Android runs of the same app). `runs/` is git-ignored: it is generated on your machine, and
`samples/demo.sh` fills it with crawls of the sample apps.

## Project layout

```
apps/
  engine/           appscreenmap.engine: the CLI (cli/, one module per command group) and the MCP server
  viewer/           the dashboard (React + Vite, built with Bun), @appscreenmap/viewer
packages/
  core/             appscreenmap.core: map.json model, analyzer, config, runs, notes, media
  drivers/          appscreenmap.drivers: Android (adb, dumpsys, device facts, apkinfo), iOS Simulator
  crawler/          appscreenmap.crawler: explorer, replay, load timing
  a11y/             appscreenmap.a11y: WCAG 2.2 checks, criteria catalogue, HTML/MD report
  security/         appscreenmap.security: scanner, rules.json (@appscreenmap/security-rules), Frida hook, mitmproxy addon
  reports/          appscreenmap.reports: health report, perf summary
  regression/       appscreenmap.regression: verify against baselines, visual diff
  exporters/        appscreenmap.exporters: Maestro flows, Mermaid
  design-tokens/    tokens.css (@appscreenmap/design-tokens): colour, type, space, motion
  testkit/          dev-only test helpers (synthetic hierarchies, fake device), the package-layer check
samples/            the Playground sample app (APKs + source) and demo.sh
runs/               crawl output (git-ignored, generated locally)
docs/               SETUP, ARCHITECTURE, PLAN, MAP_SCHEMA (data contract)
examples/           sample config
pyproject.toml      uv workspace (Python)  ·  package.json  Bun workspace (TypeScript)  ·  Makefile
```

Each package keeps its tests in `<package>/tests/`.

```bash
uv sync && uv run pytest -q
uv run ruff check && uv run ruff format
```

## Prior art

AppScreenMap builds on ideas from [DroidBot](https://github.com/honeynet/droidbot) (UI transition graphs),
[Fastbot](https://github.com/bytedance/Fastbot_Android) and [APE](https://github.com/tianxiaogu/ape) (model-based
exploration and state abstraction), Firebase Robo, and [Maestro](https://github.com/mobile-dev-inc/maestro) (flow
format). See [PLAN.md](PLAN.md#2-prior-art-what-we-borrow).
