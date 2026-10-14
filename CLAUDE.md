# AppScreenMap

Open-source (MIT) tool that crawls a mobile app on an emulator and maps every screen and
transition. The design and roadmap are in `docs/PLAN.md`; the data contract is in `docs/MAP_SCHEMA.md`.

## Layout

- The repo is becoming a monorepo (`apps/` + `packages/`); target layout and migration steps in `docs/MONOREPO.md`.
- `apps/engine/`: the Python engine, a uv workspace member (the root `pyproject.toml` is the virtual workspace)
  - `src/appscreenmap/`: crawler (driver → analyzer → explorer → model → export/visual/report → cli)
  - `tests/`: unit tests on synthetic hierarchies (`tests/helpers.py`); no device needed
- `web/`: React viewer, **owned by a separate session**. Don't edit it from crawler work.
- `design/tokens.css`: the single source of colour, type, space and motion (Ghost dark × Xcode blue, Geist), for
  the viewer and the HTML reports. Change it only through the `design-system` skill.
- `samples/`: the end-to-end playground. `playground-app/` (purpose-built Compose app, v1/v2 APKs + source,
  every screen = a scenario) and `sample-app/` (real app APK). `samples/demo.sh` runs every scenario.
- `runs/<project>/<run-id>/`: crawl output, **git-ignored** (generated locally; `samples/demo.sh` makes sample ones). Run ids
  are flat and unique; `appscreenmap serve` resolves `/runs/<run-id>/…` to the project folder.

## Rules

- `map.json` is the contract with `web/`. Within schema 1, only add fields; never rename or remove
  them. Update `docs/MAP_SCHEMA.md` in the same change.
- Test against the samples (Playground for known answers, sample-app for a real app), not stock apps. Use
  `--clear-data` to map the first-run state. When a feature needs a new scenario, add a screen to the
  Playground (mark deliberate bugs `A11Y BUG (WCAG x.y.z)`), rebuild with `samples/playground-app/build.sh`,
  and list it in `samples/README.md`.
- The crawl must stay inside the target app (`stay_in_app`, lock task pinning). Never ship a change
  that presses BACK or opens other apps to recover.
- Every exploration fix gets a synthetic regression test in `apps/engine/tests/` before re-crawling.
- No git tags or releases until asked.

## Commands

```bash
uv sync && uv run pytest -q && uv run ruff check && uv run ruff format
uv run appscreenmap doctor
uv run appscreenmap crawl --package dev.mks.sample-app --clear-data --max-steps 200
uv run appscreenmap report runs/sample-app/<run-id>   # health: wasted steps, identity issues, nav failures
uv run appscreenmap perf runs/sample-app/<run-id>     # load time per screen, jank, cold start
```

## Skills (`.claude/skills/`)

- `design-system`: the token system (`design/tokens.css`), its rules and decisions, and the contrast check
- `ios-simulator`: set up, run and debug an iOS Simulator crawl (build sample-app, simctl + idb, diagnosing a bad crawl)
- `security-audit`: run `appscreenmap security` on an Android build (manifest, secrets, data at rest, Frida log) and judge the result
- `security-rules`: the security rule catalogue (`security_rules.json`): ids, severities, fixes, official sources
- `ios-a11y-rules`: iOS accessibility (VoiceOver, Dynamic Type, HIG 44 pt) mapped to WCAG, what is detected and the Swift fix
- `crawl-app`: run a crawl and review the result
- `tune-crawler`: turn a bad crawl into a test and a fix (screen identity, wasted taps, routing)
- `extend-crawler`: add features (drivers, exports, patterns, config, schema fields, CLI)
- `maintain-crawler`: dependency/Android upgrades, compatibility checks, schema migrations
- `wcag-mobile-rules`: WCAG 2.2 → Android reference (thresholds, what's new, who checks what)
- `a11y-audit`: full WCAG 2.2 audit (automated + 200% font crawl + device tests + manual + triage + report)
- `add-a11y-rule`: add or fix an automated a11y check (crawler `a11y.py`; viewer rules belong to the web session)
- `add-exporter`: generate tests for an E2E tool (Maestro, Appium, Espresso, …) and build the pluggable exporter interface
