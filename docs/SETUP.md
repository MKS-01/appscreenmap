# Setup and usage

Everything beyond the [README](../README.md) quick start: requirements, running a crawl on Android and iOS, every
command, configuration, end-to-end tests, CI and MCP. For how the crawler works inside, see
[ARCHITECTURE.md](ARCHITECTURE.md).

## Requirements

| | |
|---|---|
| **Python** | 3.11 or newer, with [uv](https://docs.astral.sh/uv/) |
| **Android** | Platform-tools (`adb`) and a running emulator or USB device |
| **iOS** | macOS with Xcode, a booted simulator, and [idb](https://fbidb.io): `brew install facebook/fb/idb-companion` and `uv tool install fb-idb` |
| **Dashboard** | [Bun](https://bun.sh), to build the viewer once from a source checkout (`apps/viewer/dist` is not committed, so `serve` won't start until it exists) |
| **Recommended** | `aapt2` (Android build-tools): app details, activity coverage and the security manifest checks |
| **Optional** | An AI agent (Claude Code or any MCP client) for the hands-off flow; [Maestro](https://maestro.mobile.dev) to run the generated flows; [Frida](https://frida.re) (`uv tool install frida-tools`) for the dynamic security check |

```bash
git clone https://github.com/MKS-01/appscreenmap && cd appscreenmap
make setup                     # uv sync + bun install (Python and TypeScript workspaces)
make viewer                    # build the dashboard, one time
uv run appscreenmap-engine doctor     # checks adb, devices, simulators, idb, aapt2, viewer build
```

## Crawl an Android app

```bash
uv run appscreenmap-engine crawl --apk path/to/app.apk                        # install + map
uv run appscreenmap-engine crawl --package com.example.app --clear-data       # already installed, from a clean first-run state
uv run appscreenmap-engine serve                                              # open the dashboard
```

## Crawl an iOS app (Simulator, beta)

Build the app for the simulator (`xcodebuild -sdk iphonesimulator`; an `.ipa` is device-signed and won't run
there), boot a simulator, then:

```bash
uv run appscreenmap-engine crawl --platform ios --app path/to/YourApp.app --clear-data   # runs go to runs/<app>-ios/
```

On iOS the crawler sees what VoiceOver sees: a control with no accessibility label isn't in the tree, so it can't be
tapped, and that is itself a finding. Setup and debugging: the
[`ios-simulator` skill](../.claude/skills/ios-simulator/SKILL.md); status: [roadmap §8.3](PLAN.md#83-ios-started).

### Platform support

| | Android (emulator or device) | iOS Simulator (beta) |
|---|---|---|
| Map, screenshots, patterns, form filling | ✅ | ✅ from the accessibility tree |
| Stays inside the app | ✅ lock task pinning | ✅ enforced by the explorer (restarts the app if it leaves) |
| Maestro flows, `diff`, `report`, dashboard, MCP map queries | ✅ | ✅ |
| WCAG 2.2 checks and report | ✅ | ✅ (iOS-specific rules next) |
| Resize-text crawl (`--font-scale 2.0`) | ✅ font scale | ✅ Dynamic Type |
| Crash capture | ✅ logcat | ✅ DiagnosticReports |
| Load time, jank, cold start | ✅ | not yet |
| `verify` on a new build, MCP `where_am_i` / `go_to_screen` | ✅ | not yet |

## Sample apps

The **Playground** sample app ships in [`samples/`](../samples/): built so every screen triggers a known feature, with
v1 and v2 builds for release comparisons (an iOS version is planned). Crawl results are not committed (`runs/` is
git-ignored), so run `samples/demo.sh` to map it and give `appscreenmap serve` something to show; see
[`samples/README.md`](../samples/README.md).

## Commands

All run as `uv run appscreenmap-engine <command>`; `<run>` is a run folder such as `runs/playground/<run-id>`.

| Command | What it does |
|---|---|
| `doctor` | Check adb, devices, booted simulators, idb, aapt2 and the viewer build |
| `crawl --apk app.apk` / `--platform ios --app X.app` / `--package id` | Explore the app and write `runs/<project>/<run-id>/` |
| `serve` | Open the dashboard on `runs/` |
| `report <run>` | Health check: wasted taps, near-duplicate screens, navigation failures, and device conditions that skew results |
| `a11y <run> [--report]` | WCAG 2.2 checks; `--report` rebuilds `a11y-report.html` and `.md` |
| `perf <run> [--budget 1000]` | Load time per screen, slowest transitions, jank, cold start |
| `security <run> [--apk FILE \| --pull] [--device] [--frida-log FILE]` | Android security audit: manifest rules, hard-coded secrets, plain-text data on the device, Frida observations. Writes `audits/security.json` |
| `diff <base> <candidate>` | Match screens across two runs and diff pixels and text |
| `verify <run> [--apk new.apk]` | Replay every screen's path on a new build; exit 1 when one breaks ([CI](#ci-verify-a-new-build)). Android for now |
| `export <run>` | Regenerate Maestro flows and the Mermaid graph |
| `mcp` | Serve the maps to coding agents ([Agents](#agents-mcp)) |

Useful `crawl` flags: `--clear-data` (first-run state), `--max-steps`, `--max-minutes`, `--font-scale 2.0`
(WCAG 1.4.4 resize-text crawl), `--keep-animations` (load times as users see them), `--serial` (device serial or
simulator UDID), `--config appscreenmap.toml`.

## Configuration and secrets

Every option is in [`examples/appscreenmap.toml`](../examples/appscreenmap.toml). Values the crawler types are
recorded so flows can replay them, so keep real credentials out by naming an environment variable:

```toml
[inputs]
"e-?mail|user" = "qa.tester@example.com"
"pass" = "${APP_PASSWORD}"
```

The crawler types the value of `APP_PASSWORD` but writes only `${APP_PASSWORD}` to `map.json` and the flows
(`maestro test -e APP_PASSWORD=… flow.yaml` fills it there). `crawl` and `verify` stop if a variable is unset, and
the crawl warns when it types a plain-text password.

## End-to-end tests

Every screen gets a [Maestro](https://maestro.mobile.dev) flow, on Android and iOS, that launches the app fresh,
follows the recorded path (typing into forms on the way) and asserts it arrived. Selectors prefer a resource-id,
then text or content description, and fall back to a position only when nothing else exists.

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

AppScreenMap writes the files; it doesn't bundle or run Maestro (Apache-2.0, not affiliated). Maestro is the only
format today; more tools (Appium, Espresso, page objects) are planned behind a plug-in interface, and `map.json`
already has everything a generator needs.

## CI: verify a new build

```bash
uv run appscreenmap-engine verify runs/playground/<run-id> --apk app-release.apk
```

`verify` replays every screen's path from a fresh launch on the new build (longest paths first). A path fails when
a step's element is gone, or it leads to the wrong screen, out of the app, or to a crash; screens behind it are
reported as blocked, and every screen it reaches is diffed against the base run.

```
✘ 9 passed, 1 failed, 1 blocked, 0 skipped · 2 visually changed   (1.3.0 vs base 1.2.0)
  ✘ s005 'Settings': 'Settings' is not on s002
  ⊘ s009 'Connect Notion': blocked by s005
  ≠ s002 'Hello, test': 0.84% pixels; text 1 changed
```

Exit codes: `0` all paths work, `1` a path broke (or a screen changed, with `--fail-on-change`), `2` bad arguments.
`--update-baselines` accepts the new look. Paths that can't work from a fresh launch even on the base build (reached
through app state, such as a running timer) are skipped with a note, not failed.

## Agents (MCP)

`appscreenmap mcp` serves your `runs/` to MCP clients such as Claude Code, so an agent can ask "how do I reach X",
"where am I" or "which screens fail WCAG" instead of exploring the app again.

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
