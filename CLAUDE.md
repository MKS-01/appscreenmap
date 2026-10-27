# AppScreenMap

Open-source (MIT) tool that crawls a mobile app on an emulator and maps every screen and
transition. The design and roadmap are in `docs/PLAN.md`; the data contract is in `docs/MAP_SCHEMA.md`.

## Layout

- A monorepo: `apps/` (what people run) + `packages/` (building blocks); layout in
  `docs/ARCHITECTURE.md`. Two workspaces: uv for Python (`pyproject.toml`), Bun for TypeScript (`package.json`: the
  viewer, `packages/design-tokens`, and `packages/security` as `@appscreenmap/security-rules`). `make setup`.
- Python is a uv workspace (the root `pyproject.toml` is virtual). Everything imports as `appscreenmap.*` (a namespace
  package: never add `src/appscreenmap/__init__.py`). A package imports only what its `pyproject.toml` depends on
  (`packages/testkit/tests/test_layers.py` checks).
  - `packages/core/`: `appscreenmap.core`: map.json model, analyzer, config, runs, notes, media, manual (screens filed by hand), merge, accounts, activity log (`appscreenmap logs`), timeline; imports nothing else
  - `packages/drivers/`: Android (adb, dumpsys, device facts, apkinfo, logcat) and iOS Simulator; stdlib only
  - `packages/crawler/`: explorer, replay, load timing
  - `packages/a11y/`: WCAG checks (`checks.py`), criteria (`wcag.py`), HTML/MD report
  - `packages/security/`: all security tooling (scanner modules, `rules.json` catalogue also read by the viewer,
    `hooks/frida-observe.js`, `hooks/mitm_observe.py` + `network.py` for `crawl --network`); stdlib only. The mitmproxy
    addon runs in mitmproxy's own Python: never import appscreenmap or mitmproxy at its top level
  - `packages/stack/`: what an installed app is built with (`dumpsys package` + the APKs pulled from the emulator: framework,
    SDK levels, ABIs, 16 KB alignment, libraries, storage map; on iOS the simulator's `.app`: Info.plist, Mach-O, frameworks)
    → `audits/stack.json`, build kept in `<canvas>/build/`;
    `libchecker.json` is a LibChecker-Rules snapshot (`make stack-rules-sync`)
  - `packages/store/`: store readiness (target / compile / min SDK vs Play and App Store rules, 365 days ahead; `requirements.json`)
  - `packages/reports/`: health report, perf summary · `packages/regression/`: verify, visual diff ·
    `packages/exporters/`: Maestro, Mermaid
  - `packages/testkit/`: dev-only test helpers (`appscreenmap.testkit.helpers`: synthetic hierarchies, `REPO`;
    `appscreenmap.testkit.fakedevice`: a scriptable fake app/driver)
  - `apps/engine/`: `appscreenmap.engine`: the CLI (`engine/cli/`, one module per command group; `screens.py`: `add-screen` / `edit-screen`; `watch.py` and `record.py`: use the app by hand, log/traffic or a Maestro flow) and the MCP
    server (`engine/mcp_server.py`), on top of every package
  - tests live next to their code (`<package>/tests/`), on synthetic hierarchies; no device needed
- `apps/cli/`: the `appscreenmap` binary (Bun + Ink): terminal home that runs the dashboard (the engine's `serve`),
  hands every other command to the engine; `setup`, `update`, `paths`, `clean`. macOS first. `make cli`, `make cli-check`,
  `make release-local` (a release folder to test install.sh/setup/update against; never publish without being asked).
- `apps/viewer/`: React viewer, **owned by a separate session**. Don't edit it from crawler work. It imports the
  tokens and the security rules as workspace packages, never by relative path.
- `packages/design-tokens/tokens.css`: the single source of colour, type, space and motion (Ghost dark × Xcode
  blue, Geist), for
  the viewer and the HTML reports. Change it only through the `design-system` skill.
- `samples/`: the end-to-end playground, `playground-app/` (purpose-built Compose app, v1/v2 APKs + source, every
  screen = a scenario; a SwiftUI iOS version is planned). `samples/demo.sh` runs every scenario. No real third-party or
  personal app lives in the repo: real-app testing happens locally, outside it.
- `runs/<project>/<run-id>/`: crawl output, **git-ignored** (generated locally; `samples/demo.sh` makes sample ones). Run ids
  are flat and unique; `appscreenmap serve` resolves `/runs/<run-id>/…` to the project folder.

## Rules

- `map.json` is the contract with `apps/viewer/`. Within schema 1, only add fields; never rename or remove
  them. Update `docs/MAP_SCHEMA.md` in the same change.
- Test against the Playground (known answers), not stock apps; real apps are tested locally, outside the repo. Use
  `--clear-data` to map the first-run state. When a feature needs a new scenario, add a screen to the
  Playground (mark deliberate bugs `A11Y BUG (WCAG x.y.z)`), rebuild with `samples/playground-app/build.sh`,
  and list it in `samples/README.md`.
- The crawl must stay inside the target app (`stay_in_app`, lock task pinning). Never ship a change
  that presses BACK or opens other apps to recover.
- Every exploration fix gets a synthetic regression test (`packages/crawler/tests/`, or `packages/core/tests/` for
  screen identity) before re-crawling.
- One canvas per app, by default. Every crawl or re-run of an app ends in that app's one canvas: crawl, then
  `appscreenmap merge --into <canvas> <run> --labels "<flow>" --move` adds it as a scenario in place (same id and
  folder; notes, comments and tree edits kept) and removes the run's own folder, so no extra run is left behind. The
  app's first run becomes its canvas. Start a separate run or a new canvas only when the developer asks for one. Ask
  before `--clear-data` (it logs the emulator out) and before deleting a canvas.
- One finalised sign-up flow per app and path (`runs/<project>/maestro/<path>.yaml`): fix that file and overwrite it, never
  copy its steps into a TOML playbook or keep `-v2` copies. Never `hideKeyboard` on Android (it presses Back); a new
  account email every run.
- English by default in every tree. For an app that shows another language, every screen title and every link label
  on the canvas is English: crawled screens get English display titles in the canvas's `titles.json` (the crawler's
  own `map.json` title stays), manual screens and links are filed with English titles and `--via` labels, and a
  link labelled with a raw element id gets a readable name. Do this in the same pass as the capture, not when asked.
  The app's own text (screenshots, hierarchy) stays as the app shows it, and the app's language is never changed.
- No git tags or releases until asked.

## Commands

```bash
uv sync && uv run pytest -q && uv run ruff check && uv run ruff format
make test-fast   # about 10 s: skips the `slow` tests (the fake app through the crawler); the full suite above is for before a push
uv run appscreenmap-engine doctor
APP_PASSWORD=playground-demo uv run appscreenmap-engine crawl --apk samples/playground-app/apk/playground-v1.apk \
  --config samples/playground-app/appscreenmap.toml --clear-data --max-steps 200
uv run appscreenmap-engine report runs/playground/<run-id>   # health: wasted steps, identity issues, nav failures
uv run appscreenmap-engine perf runs/playground/<run-id>     # load time per screen, jank, cold start
```

## Skills (`.claude/skills/`)

- `design-system`: the token system (`packages/design-tokens/tokens.css`), its rules and decisions, and the contrast check
- `ios-simulator`: set up, run and debug an iOS Simulator crawl (build for the simulator, simctl + idb, diagnosing a bad crawl)
- `security-audit`: run `appscreenmap security` on an Android build (manifest, secrets, data at rest, Frida log) and judge the result
- `store-requirements`: refresh the dated Play / App Store rules in `packages/store/.../requirements.json` (each spring, after announcements)
- `stack-rules`: keep the app stack scan's rules current (`packages/stack`: framework fingerprints, storage map, the LibChecker snapshot via `make stack-rules-sync`), calibrate from real builds locally
- `stack-ios`: build and debug the iOS stack scan on the simulator (Mach-O, bundle markers, KMP / Compose, data container, Frida spike)
- `play-policy-insights`, `android-permissions-security`, `android-intent-security`, `edge-to-edge`, `adaptive`: unchanged copies from github.com/android/skills (Apache-2.0; `make skills-sync`) for audits and scans; `audit-xcode-security-settings`, `uikit-app-modernization`: Apple's, synced from Xcode 27 (`make skills-xcode`, git-ignored, no license). Audit/scan skills only, no development skills; excluded from ruff
- `security-rules`: the security rule catalogue (`packages/security/.../rules.json`): ids, severities, fixes, official sources
- `ios-a11y-rules`: iOS accessibility (VoiceOver, Dynamic Type, HIG 44 pt) mapped to WCAG, what is detected and the Swift fix
- `web-ui`: viewer UI work in `apps/viewer/` (owned by the web session); follows `design-system`
- `crawl-app`: run a crawl and review the result
- `tune-crawler`: turn a bad crawl into a test and a fix (screen identity, wasted taps, routing)
- `extend-crawler`: add features (drivers, exports, patterns, config, schema fields, CLI)
- `maintain-crawler`: dependency/Android upgrades, compatibility checks, schema migrations
- `wcag-mobile-rules`: WCAG 2.2 → Android reference (thresholds, what's new, who checks what)
- `a11y-audit`: full WCAG 2.2 audit (automated + 200% font crawl + device tests + manual + triage + report)
- `add-a11y-rule`: add or fix an automated a11y check (crawler `a11y/checks.py`; viewer rules belong to the web session)
- `add-exporter`: generate tests for an E2E tool (Maestro, Appium, Espresso, …) and build the pluggable exporter interface
