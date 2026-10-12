---
name: add-exporter
description: Add or improve an AppScreenMap exporter that turns a crawl into tests for an E2E tool (Maestro, Appium, Espresso/UI Automator, Playwright-style page objects, Detox, XCUITest, or a user's own template) — and build the pluggable exporter interface itself. Use when asked to support another test tool, make export plug-and-play, add `--format`, or fix a generated test that doesn't run.
---

# Exporters for E2E tools

Goal: users pick the test tool they already use. The crawl (`map.json`) stays tool-neutral; an exporter only
translates it. Read `.claude/skills/extend-crawler/SKILL.md` for the general checklist, and `docs/MAP_SCHEMA.md`
for the data.

## Current state (verify before relying on it)

Export is one hard-coded function: `export.maestro_flow(data, screen)` plus `mermaid(data)`, both called from
`export.export_run()`. **There is no exporter interface, registry or `--format` flag yet.** Check
`src/appscreenmap/export.py` and `cli.py` first; if that changed, follow the code, not this paragraph.

## Step 0: build the interface (once, then reuse it)

Do this before adding a second tool, and move Maestro behind it without changing its output (the existing
export tests must still pass byte-for-byte).

1. **Interface:** an `Exporter` with `name`, `capabilities`, and `export(data: dict, screen: dict) -> dict[str, str]`
   (relative path → file text). It receives plain `map.json` dicts, never live objects.
2. **Registry:** built-ins registered by name, plus third-party plugins through the `appscreenmap.exporters`
   entry-point group (so `pip install appscreenmap-<tool>` adds a format).
3. **CLI:** `appscreenmap export <run> --format maestro,appium-python` (default: maestro, so nothing breaks) and
   a crawl-time default in config. Keep logic in the module; `cli.py` only parses and prints.
4. **Neutral steps:** `--format json` writes the resolved path per screen (launch → steps → assertion) so any tool
   in any language can generate its own tests. Treat this shape as public API: additive changes only.
5. **Templates:** `--template file` renders the neutral steps through a user-supplied template, for people who
   only want different syntax.
6. **Docs:** README (formats, how to write a plugin), `docs/MAP_SCHEMA.md` (the neutral step format),
   `docs/PLAN.md` (§8 roadmap row).

## Adding one exporter

1. **Read the tool's docs for its selector and wait model.** Don't generate from memory; wrong syntax is the most
   common failure, and nothing in the unit tests will catch it unless you test against the tool's own grammar.
2. **Map the neutral step to the tool's commands:**
   - Selector preference: resource-id → text / content-desc → point. Say in a comment when you fell back to a
     point (coordinates are brittle, and the user should know which tests to harden).
   - Use `reach_path` (steps from launch) and each screen's `autofill` (type values before the tap that needs them).
   - `scroll_depth > 0` means the element is below the fold: use the tool's scroll-until-visible.
   - Assertion: the screen's title text, else a stable resource-id (see `export._assertion`).
   - Start from a clean launch (force-stop, then launch), because that is what the path means.
3. **Declare capabilities.** If the tool can't express a step (long-press, back, a gesture), the exporter skips that
   screen and reports it, with the reason. Never emit a test that silently does less than the path.
4. **Secrets.** Typed values come from `config.placeholders` (`${ENV}` placeholders). Never write a literal test
   password into generated files; `tests/test_secrets.py` shows the expectation. Add the tool's way of reading env
   vars to the generated file's header comment.
5. **Output layout.** `tests/<format>/…` or the tool's convention, one file per screen unless the tool prefers a
   page-object class per screen plus a path helper. Include a generated-file header with the run id.

## Tests (no device needed)

- Golden test per exporter in `tests/test_model_and_exports.py` style: a synthetic map → expected file text.
- Cases to cover: id / text / desc / point selectors, autofill with a placeholder, scrolled element, a screen the
  exporter must skip, special characters in labels (quotes, regex metacharacters, unicode).
- If the tool ships a parser or linter, run generated output through it in a test (skipped when not installed).
  Otherwise validate the format structurally (valid YAML / compiles / imports).
- `uv run pytest -q && uv run ruff check src tests && uv run ruff format src`.

## Licensing

An exporter writes text in the tool's documented format. **Don't import, bundle or copy the tool's code or
templates.** Add a short entry to `THIRD_PARTY_NOTICES.md` (the tool, its license, "format only, not bundled, not
affiliated") and use the tool's name descriptively only ("exports Appium tests"), never as a project name.

## Verify for real

Generate for the sample-app sample (`runs/sample-app/<run-id>`), run the output with the actual tool on the emulator
for at least the launch screen and one three-step path, and say in your report which tool version you used. If you
couldn't run it, say that plainly: "generated, not executed."

## Report

List: formats added, capabilities and what's skipped, selector fallbacks (counts of point selectors), tests added,
and whether the output was executed against the real tool.
