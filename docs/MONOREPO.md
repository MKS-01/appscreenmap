# Monorepo

AppScreenMap is one product: one `appscreenmap` command, one dashboard. Inside, it is a monorepo of apps
(what people run) and packages (building blocks). This document is the target layout and the migration
plan; the migration runs on the `refactor/monorepo` branch, one green commit per step.

## Layout

```
apps/
├── cli/          Bun + Ink → compiled `appscreenmap` binary: TUI, setup, updates, serves the dashboard
├── engine/       Python: `appscreenmap-engine` commands (crawl, a11y, security, …) + MCP server
└── viewer/       React dashboard (was web/)
packages/
├── core/         map.json model, analyzer, config, runs, notes, media
├── drivers/      android (adb, dumpsys, apkinfo, device) + ios (simctl, idb)
├── crawler/      explorer, replay, load timing
├── a11y/         WCAG checks, criteria, HTML/MD report
├── security/     scanner, rule catalogue (rules.json, also read by the viewer), Frida hooks
├── reports/      health report, perf summary
├── regression/   verify against baselines, visual diff
├── exporters/    Maestro (Appium, Espresso later)
├── design-tokens/  tokens.css for the viewer and reports, tokens.ts for the TUI (was design/)
└── testkit/      dev only: synthetic hierarchies, fake device
samples/          playground-app, duskread, demo.sh
docs/             product-level docs
pyproject.toml    uv workspace root (virtual): members, dev tools, ruff, pytest
package.json      Bun workspace root
Makefile          setup · test · lint · build · viewer · demo
```

Every package has the same shape: `pyproject.toml`, `README.md`, `src/appscreenmap/<area>/`, `tests/`, and
optionally `CLAUDE.md` (area rules) and `package.json` (when TypeScript reads its files).

## One import name

No package ships `src/appscreenmap/__init__.py`, so Python merges them into one namespace package:
`appscreenmap.core.model`, `appscreenmap.security`, … The version comes from
`importlib.metadata.version("appscreenmap-engine")`.

## Layers

```
core ← drivers ← crawler ← regression
core ← a11y · reports · exporters
core + drivers ← security
everything ← apps/engine
```

Each `pyproject.toml` declares what its package may import. uv installs the whole workspace into one
environment, so an undeclared import would still work locally; `packages/testkit/tests/test_layers.py` reads
every package's `pyproject.toml` and fails when a package imports an `appscreenmap.*` area it doesn't depend on.

## The CLI

`apps/cli` is a Bun + Ink binary (darwin arm64/x64, linux x64/arm64), the same stack as readback's CLI.

```
appscreenmap [start]              TUI + dashboard (opens the browser)
appscreenmap setup                first-run check; installs or repairs the engine and the viewer
appscreenmap update [--check] [cli|engine|viewer]
appscreenmap version · doctor · paths · clean
appscreenmap crawl|a11y|security|perf|report|verify|diff|export …   → passed to the engine unchanged
appscreenmap mcp                  → the engine's MCP server over stdio
```

- **Install:** `curl -fsSL …/install.sh | sh` puts the binary on PATH. The first run installs `uv` if
  missing (asks first), runs `uv tool install appscreenmap-engine==<pinned>` (uv brings its own Python),
  downloads the matching viewer, and checks adb, the emulator and idb.
- **start:** serves the viewer, `runs/` and the notes endpoint with `Bun.serve`, opens the browser, and shows
  tabs: Home (devices, recent runs), Crawl (start one, live progress from the engine's JSON-lines events),
  Runs (open, report, perf, a11y, security), Agent (commands to start an agent session in a new terminal
  tab). It watches `runs/index.json`, so a run an agent records elsewhere appears in the TUI and the
  dashboard reloads.
- **Home folder** (`~/Library/Application Support/appscreenmap`, `~/.local/share/appscreenmap`;
  `APPSCREENMAP_HOME` overrides): `config.toml`, `viewer/<version>/` with a `current` symlink, `cache/`,
  and a pid file so a server orphaned by a killed CLI is cleaned up on the next start.
- **Versions:** each binary release pins compatible engine and viewer versions. The viewer bundle carries
  `viewer.json` (`version`, `map_schema`, `min_cli`), downloads are checked against SHA-256 sums, and the
  update check runs at most daily, never updates on its own, and is off in CI or with
  `APPSCREENMAP_NO_UPDATE_CHECK=1`.
- **Dev mode** (source checkout): the engine runs through `uv run`, the viewer through its Vite dev server,
  and `update` prints `git pull && make setup` instead.

No releases until asked: the release workflow is written but switched off, and installs are tested against
a local release folder (`APPSCREENMAP_RELEASE_URL=file://…`).

## Migration

| Step | Change |
|---|---|
| 1 | Workspace skeleton: virtual root `pyproject.toml`, `Makefile`; `src/` + `tests/` → `apps/engine/` |
| 2 | Extract `packages/core` and `packages/testkit` |
| 3a | Extract `packages/drivers` (security needs `apkinfo`); dumpsys parsers leave `perf.py` |
| 3b | Extract `packages/security`: split the scanner, move the Frida hook into the package |
| 4 | Extract `crawler`, `a11y`, `reports`, `regression`, `exporters`; `LoadMeter` leaves `perf.py` |
| 5 | Split `cli.py` into `appscreenmap.engine.cli.*`; MCP server → `appscreenmap.engine.mcp_server` |
| 6 | Bun workspace: `design/` → `packages/design-tokens/`, `web/` → `apps/viewer/`, `packages/security/package.json` (`@appscreenmap/security-rules`) (coordinated with the web session) |
| 7 | CI, CLAUDE.md files, docs and skill paths; `samples/demo.sh playground` end to end |
| 8 | `apps/cli` skeleton: `start` TUI, `Bun.serve`, pass-through to the engine |
| 9 | Crawl tab with live progress, run watcher |
| 10 | `setup`, `update`, `paths`, `clean`, install script |
| 11 | Release workflow (switched off) |

Until step 8 the engine also installs the `appscreenmap` command, so skills, docs and `samples/demo.sh` keep
working throughout.

## Log

One row per commit on `refactor/monorepo`. **Outside crawler code** lists every change to files another
session owns (`web/`, `design/`), so they can review exactly what was touched.

| Step | Commit | What moved | Outside crawler code |
|---|---|---|---|
| 1 | `c74ebac` | `src/` + `tests/` → `apps/engine/`; virtual workspace root; Makefile; repo-wide ruff | — |
| 1 | `8a7ef00` | — | `web/src/insights/registry.ts`: rules import → `apps/engine/src/appscreenmap/security_rules.json` (import path + comment only) |
| 2 | `2c20635` | `model`, `analyzer`, `config`, `runs`, `notes`, `media` → `packages/core` (`appscreenmap.core.*`); `tests/helpers.py` → `packages/testkit` (`appscreenmap.testkit.helpers`); `appscreenmap` becomes a namespace package (version from `appscreenmap.core.__version__`); package-layer test | Comments only, pointing at the moved files: `web/src/types.ts:1`, `web/src/views/HowItWorks.tsx:9`, `web/vite.config.ts:21`, `web/README.md:52` |
| 3a | `6111d79` | `driver.py` → `drivers/base.py` (`DriverError`, `Snapshot`) + `drivers/android.py` (`AdbDriver`); `driver_ios.py` → `drivers/ios.py`; `device`, `apkinfo`, `ios_hierarchy` → `packages/drivers`; dumpsys parsers `perf.py` → `drivers/dumpsys.py` (`_TOTAL_RE` → `TOTAL_FRAMES_RE`); iOS fixture moves with its test | — |
| 3b | `a0bd62f` | `security.py` → `packages/security`, split into `manifest`, `secrets`, `apk`, `device_data`, `frida`, `audit` (public API re-exported from `appscreenmap.security`); `security_rules.{py,json}` → `security/rules.{py,json}`; `.claude/skills/security-audit/scripts/frida-observe.js` → `security/hooks/` (ships in the wheel; new `appscreenmap security --frida-script` prints its path); CLI tests → `apps/engine/tests/test_security_cli.py` | `web/src/insights/registry.ts`: rules import → `packages/security/src/appscreenmap/security/rules.json` (import path + comment only) |
| 4 | `d62b6f5` | `explorer`, `replay` → `packages/crawler`, plus `crawler/timing.py` (`LoadMeter`, `Timing`, loading indicator) out of `perf.py`; `a11y.py` → `a11y/checks.py`, `a11y_report.py` → `a11y/report.py`, `wcag.py` → `a11y/wcag.py`; `report.py` → `reports/health.py`, rest of `perf.py` → `reports/perf.py`; `frame_metrics` + `FROZEN_FRAME_MS` → `drivers/dumpsys.py`; `verify`, `visual` → `packages/regression`; `export.py` → `exporters/maestro.py` + `mermaid.py` + `export.py` (`export_run`); `fakedevice.py` → `appscreenmap.testkit.fakedevice` (engine `conftest.py` removed). Mixed test files split by area: `test_perf.py` → drivers `test_dumpsys.py` + crawler `test_timing.py` + reports `test_perf.py`; `test_model_and_exports.py` → core `test_model.py` + exporters `test_export.py` + regression `test_visual.py`. `apps/engine` now holds only `cli.py` and `mcp_server.py` | — |
| 5 | `08b2d3c` | `cli.py` → `appscreenmap/engine/cli/`: `crawl` (doctor, crawl), `verify` (export, diff, verify), `analyse` (report, perf, a11y), `security`, `serve` (serve, mcp); each module registers its own subcommands, `cli/__init__.py` keeps `main()`. `mcp_server.py` → `engine/mcp_server.py`. Entry points → `appscreenmap.engine.cli:main`; new `python -m appscreenmap.engine` (the MCP `crawl` tool spawned `-m appscreenmap.cli`, now `-m appscreenmap.engine`); install hint `appscreenmap[mcp]` → `appscreenmap-engine[mcp]` (stale since step 1) | — |
| 6 | (this) | `web/` → `apps/viewer/` (`@appscreenmap/viewer`); `design/tokens.css` → `packages/design-tokens/` (`@appscreenmap/design-tokens`); `packages/security/package.json` exposes `rules.json` as `@appscreenmap/security-rules`; root `package.json` Bun workspace + root `bun.lock` (seeded from `web/bun.lock`: all 140 locked versions identical); uv excludes `packages/design-tokens`; `.github/workflows/web.yml` → `viewer.yml`; `serve`/`doctor` look for `apps/viewer/dist`; Makefile `setup`/`viewer` follow | Folder move `web/` → `apps/viewer/` (no code change), plus in the viewer: `src/tokens.css` `@import "@appscreenmap/design-tokens/tokens.css"`; `src/insights/registry.ts` imports `@appscreenmap/security-rules/rules.json` and one UI string path; `vite.config.ts` runs default `../../runs`, `fs.allow ["../.."]`; `package.json` name + two `workspace:*` deps; path text in `DESIGN.md`, `README.md`, `index.html` comment, `src/views/DesignSystem.tsx` (two UI strings, one comment). `packages/design-tokens/tokens.css`: header comment only, no value changed. Built CSS is byte-identical (`index-CPhrjlfC.css`) |
