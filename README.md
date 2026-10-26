<p align="center">
  <img src="docs/media/appscreenmap-mark.svg" alt="AppScreenMap" width="96" height="96">
</p>

<h1 align="center">AppScreenMap</h1>

<h3 align="center">Map and audit any mobile app from your AI agent.</h3>

<p align="center">Android emulator and iOS Simulator · No SDK, no test IDs, no source code</p>

<p align="center">
  <a href="https://github.com/MKS-01/appscreenmap/actions/workflows/crawler.yml"><img src="https://github.com/MKS-01/appscreenmap/actions/workflows/crawler.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/Android_·_iOS-0a0a0a?style=flat-square" alt="Android and iOS">
  <a href="#ai-agent-and-mcp"><img src="https://img.shields.io/badge/MCP-server-0a0a0a?style=flat-square&logo=modelcontextprotocol&logoColor=white" alt="MCP server"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-0a0a0a?style=flat-square" alt="MIT License"></a>
  <a href="https://m8ven.ai/mcp/mks-01-appscreenmap-5cftte?s=readme"><img src="https://m8ven.ai/badge/mcp/mks-01-appscreenmap-5cftte?v=5da838a903ecc0b48a695af01acacf32" alt="M8ven Score"></a>
</p>

<p align="center">
  <a href="#know-your-app">Know your app</a> ·
  <a href="#get-started">Get started</a> ·
  <a href="#ai-agent-and-mcp">Agent and MCP</a> ·
  <a href="#dashboard">Dashboard</a> ·
  <a href="docs/SETUP.md">Docs</a> ·
  <a href="docs/ARCHITECTURE.md">Architecture</a>
</p>

<p align="center">
  <img src="docs/media/how-it-works.png" alt="You ask your AI agent for a map, an audit or a build comparison. The agent explores the app on an Android emulator or iOS Simulator and writes a run folder of plain files. The dashboard, the MCP server, the exports and the verify command all read that folder.">
</p>

```bash
appscreenmap crawl --apk app.apk   # explore the app, then run `appscreenmap` to browse the map
```

> [!NOTE]
> **Early alpha:** the project is under active development and commands may change.

## Know your app

Ask a team "how many screens does your app have, and how do I reach checkout?" and you get a guess. The answer
lives in someone's head, a stale design file, or a test suite that breaks every sprint. AppScreenMap walks through
the build you already ship and writes every screen down, so the answer is a file you can query, diff and build on.

- *What is in this build?* A complete screen inventory, including screens nobody remembers.
- *How do I reach Settings?* A route to every screen, for you and for your agent.
- *What changed since the last release?* Added, removed and changed screens, before release.
- *Is it accessible, fast, secure, store-ready?* WCAG 2.2, performance, store deadlines and security, each with the fix and an official source.
- *What does the app talk to?* The hosts it calls and its own log lines, tied to the screen you were on (`crawl --network`, `watch`).
- *Did this build break a path?* `verify` replays every path and fails the CI job if one is gone.

It makes no model calls while it explores, so the same build gives the same map, and nothing leaves your machine.
Android and iOS (iOS is beta).

## Get started

Needs macOS, [uv](https://docs.astral.sh/uv/), [Bun](https://bun.sh), and an Android emulator or device (`adb`),
or Xcode with a booted Simulator for iOS.

```bash
git clone https://github.com/MKS-01/appscreenmap && cd appscreenmap
make install                         # engine, dashboard and the `appscreenmap` command
appscreenmap setup                   # checks adb, devices, simulators; says what is missing
appscreenmap crawl --apk app.apk     # explore the app
appscreenmap                         # terminal home + dashboard
```

No app handy? Press `x` in the terminal home to map the [Playground](samples/README.md) sample app.

- **Output** is a run folder of plain files (`map.json`, `screens/`, `flows/`, `a11y.json`, `perf.json`, reports).
  `map.json` is a versioned contract: [docs/MAP_SCHEMA.md](docs/MAP_SCHEMA.md).
- **Another language:** add `--locale fr-FR` (or `ja`, `ar`, …). Android 13+; on iOS the app is relaunched.
- **Commands:** `appscreenmap --help` lists them all. After pulling new code, run `make install` again.

## AI agent and MCP

Everything can run through your AI agent. Press `t` in the terminal home for a new terminal in the same folder, run
`claude`, and ask in plain language:

> *Map my app on the emulator and review the map.*<br>
> *Audit accessibility on the latest run at WCAG 2.2 AA.*<br>
> *Map the new build and compare it with the last run.*<br>
> *Two screens got merged in the last map. Fix it and map again.*

The agent works through the MCP server, so it answers from the map instead of exploring the app again, and its
work shows up live in the dashboard:

> *You:* How do I reach Settings?<br>
> *Agent → `route("Settings")`:* From launch: tap **Profile**, then tap **Settings**. Here is the test flow.<br>
> *You:* Take the emulator there.<br>
> *Agent → `go_to_screen("Settings")` → `where_am_i()`:* Done, the device is on Settings.

### Connect

`appscreenmap mcp` serves your mapped runs to any MCP client (Claude Code, Claude Desktop, Cursor, VS Code, …). It
is a local stdio server: it reads `runs/` on your machine and talks to your emulator or Simulator, with no account,
no API key and no network calls.

```bash
claude mcp add appscreenmap -- appscreenmap mcp
```

Other clients take the same command in their MCP config:

```json
{ "mcpServers": { "appscreenmap": { "command": "appscreenmap", "args": ["mcp"] } } }
```

Options: `--runs <dir>` (default `./runs`), `--run <run-id>` (default: the latest finished run), `--serial <device>`.

### Tools

| Tool | Answers | Kind |
|---|---|---|
| `list_runs`, `list_screens`, `find_screens` | What has been mapped; which screen is "Settings" or has a "Save" button | read-only |
| `get_screen`, `screenshot` | One screen: elements and where each leads, how to reach it, findings, load time, image | read-only |
| `route` | Steps to a screen, from launch or another screen (with its test flow) | read-only |
| `a11y_findings`, `perf_summary` | Which screens fail which WCAG 2.2 criteria; which are slow | read-only |
| `where_am_i` | Which mapped screen the device shows now | read-only |
| `go_to_screen` | Drive the device to a screen along its route | drives the device |
| `crawl` | Map an app (or a new build) in the background | drives the device |
| `crawl_status` | Follow a running map | read-only |

Tools carry MCP annotations (`readOnlyHint`, `destructiveHint`), so clients can ask before `go_to_screen` and `crawl`,
the two that drive the device. More in [docs/SETUP.md](docs/SETUP.md#agents-mcp).

## Dashboard

`appscreenmap serve` opens it on `runs/`. No backend; it updates live while it maps.

- **Insights**: scored audits with findings, fixes and official sources
- **Map**: every screen as a tree, graph or storyboard. Comment, add planned screens, file screens the crawl missed, rename, move or remove; edits go in `notes.json` and the mapped data is never touched
- **Screens**: search, tappable overlays, transitions, the test flow
- **Accessibility**: findings per rule with screenshots; triage them, export a WCAG 2.2 report
- **Network · Logs**: the hosts the app called and its own log lines, with sessions you recorded by hand
- **Compare**: what changed between two builds
- **Crawl replay**: step through what was tapped and why

Export the map as one self-contained SVG (every screenshot inside) or Markdown/CSV from the dashboard, or take the files
straight from the run: test flows (`flows/`, Maestro format), a Mermaid graph (`map.mmd`), a one-file WCAG report
(`a11y-report.html`, evidence not a conformance claim), and `map.json` / `a11y.json` / `perf.json`.

## License

Open source under the [MIT License](LICENSE). © 2026 MKS and AppScreenMap contributors.

Built with [Claude Code](https://claude.com/claude-code).
