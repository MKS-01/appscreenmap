---
name: tune-crawler
description: Diagnose and fix AppScreenMap exploration quality problems — duplicate or merged screens, wasted/repeated taps, wrong element kinds or titles, navigation/replay failures, the crawl leaving the app, slow crawls. Use after a crawl or `appscreenmap report` shows findings, or when the user says the map looks wrong.
---

# Tune the crawler: evidence → failing test → fix → re-crawl

Never fix exploration by guessing. Each fix follows this loop:

1. **Evidence.** Get the run's health report and find the steps where it went wrong.
   ```bash
   uv run appscreenmap report runs/<project>/<run-id>
   grep -n '"effect": "same_screen"' runs/<project>/<run-id>/trace.jsonl | head     # wasted taps
   ```
   The hierarchy of every screen is in `runs/<project>/<run-id>/screens/<sid>.xml`. To capture the live screen:
   ```bash
   uv run python -c "
   from appscreenmap.driver import AdbDriver; from appscreenmap.analyzer import analyze
   d=AdbDriver(); s=d.snapshot(); w,h=d.screen_size(); o=analyze(s.xml,None,s.activity,w,h)
   print(o.title, o.patterns, o.signature)
   for e in o.elements: print(e.kind, e.action, repr(e.label), e.group, e.key)"
   ```
   To print the tree with groups, walk `parse_hierarchy()` + `_mark_repeats()`; see how
   `tests/helpers.py` models Compose output.
2. **Failing test.** Reproduce the structure in `tests/` with the `node()` / `hierarchy()` helpers.
   Use synthetic data only; never commit real app dumps, since they contain user content.
3. **Fix** in the right layer (map below). Keep the change minimal and explain *why* in a comment
   only where it's non-obvious.
4. **Verify.** Run `uv run pytest -q && uv run ruff check src tests && uv run ruff format src`, then
   re-crawl sample-app with `--clear-data` and compare `report` numbers before and after
   (steps/screen, no-ops, near-duplicates, nav failures).

## Symptom → where to look

| Symptom (report / trace) | Likely cause | Code |
|---|---|---|
| Same screen appears as 2+ ids (near-duplicate pair) | Dynamic text leaking into tokens; threshold too strict | `analyzer.analyze()` token rules, `normalize_text`, `CrawlConfig.similarity`, `Explorer.identify()` |
| Different screens share one id; "crowded" screen | Tokens too coarse (Compose: every node is `View`) | text tokens, `layout_fingerprint`, `identify()` |
| Wrong `variant_of` | Layout similarity too loose / wrong trigger | `AppMap.mark_variant`, `LAYOUT_VARIANT` |
| Same element tapped on many screens, no effect | Global element not inferred | `AppMap.infer_global_nav` (nav/tab kinds), `_kind()` |
| Distinct buttons collapsed / missing | Key collision after normalization | `_elements()` key + ordinal logic |
| Element keys change between visits → `not_found`, re-explored | Key built from dynamic text or position | `_elements()` key rules (scroll keys are positional) |
| Header/buttons treated as list rows (and capped) | Over-eager repeat detection | `_mark_repeats()` (leaf rule, grid rule) |
| Whole list explored one row at a time | Rows not grouped, or outcomes not judged "same" | `_mark_repeats`, `AppMap.apply_list_cap`, `_same_outcome` |
| `nav_failed`, many restarts | History-dependent back edges, start screen varies | `Explorer.routes()` costs, `navigate()`, `follow()` |
| Typing navigates away / closes screen | Keyboard handling | `Explorer.autofill()`, `AdbDriver.hide_keyboard()` (ESC, never BACK) |
| `left_app`, `x:` screens | Pinning failed or disabled | `AdbDriver.pin()`, `Explorer.restart()`, `stay_in_app` |
| Title is the activity name | No title heuristic matched | `_title()`, the fallback in `Explorer.record()` |
| Slow (>4 s/step) | Device I/O, not Python | `settle_seconds`; future uiautomator2 driver (`extend-crawler`) |

## Lessons already learned (don't regress)

- Compose flattens LazyColumn rows into leaf siblings, so leaves are only list rows inside real
  `ListView`/`RecyclerView`/`GridView`.
- Digits are normalized (`10:15` → `##:##`) for identity. Colliding element keys get `#2`, `#3`
  instead of being dropped.
- Nested controls inside list rows (a card's "MORE") form their own group.
- ListView rows are often not `clickable`; they're treated as implicitly clickable.
- BACK can close search screens, so the keyboard is hidden with ESC.
- BACK at the app's root exits the app, so the app is pinned via `am task lock`. A force-stop unpins, so
  `restart()` re-pins.
- A screen first seen outside a recorded action has `origin: unknown` and gets a path the first time a known
  screen leads there. Only `restart()` may mark `origin: launch` (an empty path means "launch lands here").
  The viewer builds its tree from `reach_path`, so never leave a pathless screen looking like a root.
- An action that only changes scrolled content (a tap that scrolls the list, a WebView exposing its text)
  must not create a new screen. `identify(obs, hint=src)` keeps the source screen when the *fixed* part
  (`fixed_tokens`: outside scrollers/WebViews: title, toolbar, nav) is unchanged.
- Android 10+ often shows no crash dialog: the app just disappears and another app comes to the front.
  When the app leaves the foreground, check `logcat -b crash` for `Process: <pkg>,` before calling it "left the app".
- First-run screens (sign-in, onboarding) disappear once the app saves state. With `--clear-data` the
  crawler may `pm clear` once to get back (`data_reset` event, max 5 per crawl).
- Pinning shows an "App pinned" toast; `restart()` waits it out so screenshots (and visual diffs) stay clean.
- Stdout must be line-buffered, or background logs stay empty.

Add new lessons here when a fix teaches something general.
