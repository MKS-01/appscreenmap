---
name: add-a11y-rule
description: Add or improve an automated WCAG 2.2 accessibility check in AppScreenMap — choose the right layer (crawler a11y.py vs the web viewer's a11y.ts), write the rule spec, guard against false positives, test it with synthetic hierarchies, and document it. Use when a new criterion should be detected automatically or an existing a11y rule is noisy or wrong.
---

# Add an accessibility rule

## 1. Pick the layer

| The check needs… | Put it in | Owner |
|---|---|---|
| Several screens, flows (`reach_path`, `autofill`), crawl events, manifest/device facts | `src/appscreenmap/a11y.py` | crawler (this session) |
| One screen's hierarchy only | `a11y.py` **if** the viewer doesn't already cover it (see the table in `wcag-mobile-rules`) | crawler |
| Screenshot pixels in the browser (contrast), interactive UI | `web/src/a11y.ts` | **web session**. Don't edit it. Write the spec below and give it to the user to pass on. |
| Data the crawl doesn't capture yet (e.g. focus traversal, live regions, autofill hints) | First extend the driver/explorer to record it (`extend-crawler`), add it to `map.json` (additive), then write the rule | crawler |

Never duplicate a viewer rule in Python. If a viewer rule is wrong (e.g. it calls 48 dp a WCAG
failure), write up the correction for the web session instead.

## 2. Write the spec first

```
id:           kebab-case, unique across a11y.py and a11y.ts
criterion:    SC number + name + level (WCAG 2.2). One primary SC.
kind:         automated (detects a likely failure) | review (flags something a person must check)
severity:     error (likely failure) | warning | info
detects:      precise condition, with thresholds in dp (px / (density/160))
exceptions:   WCAG's own exceptions for this SC (e.g. 2.5.8 spacing/inline/essential)
false +:      known noise sources and the guard for each
fix:          View + Compose guidance (1–2 sentences)
native_note:  set when WCAG2ICT doesn't apply the SC to a single app
```

Check the criterion's Understanding page (https://www.w3.org/WAI/WCAG22/Understanding/) for
exceptions. Most false-positive complaints come from a missed exception.

## 3. Implement in `a11y.py`

- Add a `Rule(...)` to `RULES`; the key is the rule id.
- Put the detection in the matching function: `_screen_checks` (per screen, from `parse_hierarchy`
  nodes), `_cross_screen_checks` (map.json elements across screens), `_flow_checks` (reach paths,
  autofill, events), `_app_checks` (manifest/device).
- Report with `out.add(rule_id, screen_id, label, detail, node=…)`. This builds the shared issue
  key `<screen>::<rule>::<rid|class>::<label>::<x>,<y>`. Keep `label` stable between runs (no
  counts or timestamps), or triage decisions get lost.
- Only flag nodes from the app's own package, that are on screen, and that aren't backdrops (≥ 90%
  of the screen).
- Convert sizes with `dp = _dp(data)`. Never hard-code pixels.
- Compose specifics: nodes are often `android.view.View` without ids, and names come from merged
  children. Use `_name(n)` and `_visible_text(n)`.

## 4. Test

In `tests/test_a11y.py`, build a run with `make_run(tmp_path, [(_screen(...), hierarchy(...))])`.
Use `DPI = 160` so 1 px = 1 dp. Cover:
1. a clear failure → flagged with the right `sc`, `level`, and `kind`
2. each WCAG exception → **not** flagged
3. each false-positive guard → not flagged
4. key stability: running twice gives identical keys

```bash
uv run pytest -q tests/test_a11y.py && uv run ruff check src tests && uv run ruff format src
```

## 5. Check it on a real crawl

Run `uv run appscreenmap a11y runs/sample-app/<run-id> --level AAA` on the committed sample run.
Check every new hit by looking at the screenshot and bounds. If more than about 1 in 5 hits is
wrong, tighten the rule or downgrade it to `review`/`info` before shipping.

## 6. Document

- `wcag-mobile-rules`: add the rule to the "Who checks what" table and to the criterion's row in
  `reference/criteria.md` (Check column).
- `docs/MAP_SCHEMA.md` § a11y.json if the output shape changed (additive only).
- `src/appscreenmap/wcag.py`: the report's criteria catalogue. Crawler coverage is derived from
  `RULES` automatically. If the check only means something under a condition (like 1.4.4 needing a
  200% font crawl), add it to `a11y_report._not_run_reason` so the report says *Not tested* instead
  of a false *No issues detected*. If a viewer rule changes its criterion, update `VIEWER_RULES`.
- Note any lesson learned (a false-positive pattern) in this skill.

## Lessons

- 48 dp is Android's guideline; WCAG AA (2.5.8) is 24 dp with a spacing exception. Keep them apart.
- A device's own bottom control row (player buttons, timer controls) isn't app navigation.
  `nav-inconsistent` only compares bars that share most items with the common bar.
- Compose clickables usually have no role (`android.view.View`). `no-role` is `info` because many
  are cards where the merged text is announced fine; confirm with TalkBack before calling it a failure.
