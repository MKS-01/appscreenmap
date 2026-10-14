# AppScreenMap

Open-source (MIT) tool that crawls a mobile app on an emulator and maps every screen and
transition. The design and roadmap are in `docs/PLAN.md`; the data contract is in `docs/MAP_SCHEMA.md`.

## Layout

- The repo is becoming a monorepo (`apps/` + `packages/`); target layout and migration steps in `docs/MONOREPO.md`.
- Python is a uv workspace (the root `pyproject.toml` is virtual). Everything imports as `appscreenmap.*` (a namespace
  package: never add `src/appscreenmap/__init__.py`). A package imports only what its `pyproject.toml` depends on
  (`packages/testkit/tests/test_layers.py` checks).
  - `packages/core/`: `appscreenmap.core`: map.json model, analyzer, config, runs, notes, media; imports nothing else
  - `packages/drivers/`: Android (adb, dumpsys, device facts, apkinfo) and iOS Simulator; stdlib only
  - `packages/crawler/`: explorer, replay, load timing
  - `packages/a11y/`: WCAG checks (`checks.py`), criteria (`wcag.py`), HTML/MD report
  - `packages/security/`: all security tooling (scanner modules, `rules.json` catalogue also read by the viewer,
    `hooks/frida-observe.js`); stdlib only
  - `packages/reports/`: health report, perf summary · `packages/regression/`: verify, visual diff ·
    `packages/exporters/`: Maestro, Mermaid
  - `packages/testkit/`: dev-only test helpers (`appscreenmap.testkit.helpers`: synthetic hierarchies, `REPO`;
    `appscreenmap.testkit.fakedevice`: a scriptable fake app/driver)
  - `apps/engine/`: `appscreenmap.engine`: the CLI (`engine/cli/`, one module per command group) and the MCP server (`engine/mcp_server.py`), on top of every package
  - tests live next to their code (`<package>/tests/`), on synthetic hierarchies; no device needed
- `web/`: React viewer, **owned by a separate session**. Don't edit it from crawler work.
- `design/tokens.css`: the single source of colour, type, space and motion (Ghost dark × Xcode blue, Geist), for
  the viewer and the HTML reports. Change it only through the `design-system` skill.
- `samples/`: the end-to-end playground. `playground-app/` (purpose-built Compose app, v1/v2 APKs + source,
  every screen = a scenario) and `duskread/` (real app APK). `samples/demo.sh` runs every scenario.
- `runs/<project>/<run-id>/`: crawl output, **git-ignored** (generated locally; `samples/demo.sh` makes sample ones). Run ids
  are flat and unique; `appscreenmap serve` resolves `/runs/<run-id>/…` to the project folder.

## Rules

- `map.json` is the contract with `web/`. Within schema 1, only add fields; never rename or remove
  them. Update `docs/MAP_SCHEMA.md` in the same change.
- Test against the samples (Playground for known answers, DuskRead for a real app), not stock apps. Use
  `--clear-data` to map the first-run state. When a feature needs a new scenario, add a screen to the
  Playground (mark deliberate bugs `A11Y BUG (WCAG x.y.z)`), rebuild with `samples/playground-app/build.sh`,
  and list it in `samples/README.md`.
- The crawl must stay inside the target app (`stay_in_app`, lock task pinning). Never ship a change
  that presses BACK or opens other apps to recover.
- Every exploration fix gets a synthetic regression test (`packages/crawler/tests/`, or `packages/core/tests/` for
  screen identity) before re-crawling.
- No git tags or releases until asked.

## Commands

```bash
uv sync && uv run pytest -q && uv run ruff check && uv run ruff format
uv run appscreenmap doctor
uv run appscreenmap crawl --package dev.mks.duskread --clear-data --max-steps 200
uv run appscreenmap report runs/duskread/<run-id>   # health: wasted steps, identity issues, nav failures
uv run appscreenmap perf runs/duskread/<run-id>     # load time per screen, jank, cold start
```

## Skills (`.claude/skills/`)

- `design-system`: the token system (`design/tokens.css`), its rules and decisions, and the contrast check
- `ios-simulator`: set up, run and debug an iOS Simulator crawl (build DuskRead, simctl + idb, diagnosing a bad crawl)
- `security-audit`: run `appscreenmap security` on an Android build (manifest, secrets, data at rest, Frida log) and judge the result
- `security-rules`: the security rule catalogue (`packages/security/.../rules.json`): ids, severities, fixes, official sources
- `ios-a11y-rules`: iOS accessibility (VoiceOver, Dynamic Type, HIG 44 pt) mapped to WCAG, what is detected and the Swift fix
- `crawl-app`: run a crawl and review the result
- `tune-crawler`: turn a bad crawl into a test and a fix (screen identity, wasted taps, routing)
- `extend-crawler`: add features (drivers, exports, patterns, config, schema fields, CLI)
- `maintain-crawler`: dependency/Android upgrades, compatibility checks, schema migrations
- `wcag-mobile-rules`: WCAG 2.2 → Android reference (thresholds, what's new, who checks what)
- `a11y-audit`: full WCAG 2.2 audit (automated + 200% font crawl + device tests + manual + triage + report)
- `add-a11y-rule`: add or fix an automated a11y check (crawler `a11y/checks.py`; viewer rules belong to the web session)
- `add-exporter`: generate tests for an E2E tool (Maestro, Appium, Espresso, …) and build the pluggable exporter interface
