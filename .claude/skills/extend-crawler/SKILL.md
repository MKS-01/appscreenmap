---
name: extend-crawler
description: Add a feature to the AppScreenMap crawler — a new device driver (uiautomator2, iOS), export format (Appium, Playwright-style page objects), UI pattern detector, config option, CLI command, map.json field, or exploration strategy (e.g. LLM-guided). Use when the user asks to add, build, or support something new in the crawler.
---

# Extend the crawler

Start by reading `docs/PLAN.md` §8 (roadmap) so the feature fits the plan. Update the roadmap
row when you're done.

## Architecture in one line

`driver` (device I/O) → `analyzer` (XML → elements, tokens, patterns) → `explorer` (choose, act,
identify, record) → `model.AppMap` (→ `map.json`) → `export` / `visual` / `report` → `cli`.
Keep each layer ignorant of the ones after it.

## Extension points

| Feature | Where | Notes |
|---|---|---|
| **New driver** (uiautomator2 for ~5× speed, iOS via WebDriverAgent/idb) | new `packages/drivers/.../drivers/<name>.py` with the same public methods as `AdbDriver`: `snapshot()`, `screenshot()`, `tap/long_press/swipe/back/key/input_text/hide_keyboard`, `screen_size()`, `info()`, app management (`install/launch/force_stop/clear_data/grant_all`), `pin/unpin`, crash log | `snapshot()` must return a uiautomator-format XML so the analyzer is unchanged. For iOS, convert the XCUI tree to that format and keep the mapping in the driver. Add a `--driver` flag in `cmd_crawl` (`apps/engine/src/appscreenmap/engine/cli/crawl.py`). |
| **New export** (E2E tool: Appium, Espresso, Playwright-style, …) | Use the **`add-exporter`** skill | It covers the pluggable exporter interface, selectors, secrets, tests and licensing. |
| **New UI pattern** | `analyzer._patterns()` | Add a test in `packages/core/tests/test_analyzer.py` and list the pattern in `docs/MAP_SCHEMA.md`. |
| **Element kind / priority** | `analyzer._kind()`, `KIND_PRIORITY` | Kinds drive priority and global inference. |
| **Config option** | `config.CrawlConfig` (dataclass field + comment) + `examples/appscreenmap.toml` | Unknown keys raise. Expose a CLI flag only if it's commonly changed. |
| **CLI command** | `apps/engine/src/appscreenmap/engine/cli/<group>.py`: `cmd_<name>` + its parser in that module's `register()` (a new group goes in `GROUPS` in `cli/__init__.py`) | Keep logic in a module (like `reports/health.py`); the CLI only formats. |
| **map.json field** | `model.*.to_dict()` | Additive only (schema 1). Document it in `docs/MAP_SCHEMA.md` and tell the user the web session can use it. |
| **Exploration strategy** (LLM-guided, goal-directed) | `Explorer.next_action()` / `pick_frontier()` | Keep the deterministic path as the default. An LLM strategy is optional, plugged in behind a config flag, and must still respect `blocked_text` and `stay_in_app`. |
| **Run analysis** | `packages/reports/` (`health.py`, `perf.py`) | New findings should name the symptom and point at the cause. |

## Checklist for every feature

1. Tests first where possible, with synthetic hierarchies in `packages/testkit/src/appscreenmap/testkit/helpers.py`. No device in unit tests.
2. `uv run pytest -q && uv run ruff check && uv run ruff format`.
3. If behavior on a device changed, run a real crawl of the Playground (`crawl-app` skill) and compare
   `appscreenmap report` with the previous run.
4. Docs: README (user-facing), `docs/MAP_SCHEMA.md` (data), `docs/PLAN.md` (roadmap status),
   `examples/appscreenmap.toml` (options).
5. Don't touch `apps/viewer/`. If the viewer should show the new data, describe the field and its meaning
   to the user so the web session can pick it up.
6. Safety: the crawler must never tap `blocked_text` matches, never leave the app, and always
   restore device state (animations, pinning) in `cmd_crawl`'s `finally` (`apps/engine/src/appscreenmap/engine/cli/crawl.py`).
