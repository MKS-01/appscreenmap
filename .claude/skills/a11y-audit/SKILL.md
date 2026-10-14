---
name: a11y-audit
description: Run a WCAG 2.2 accessibility audit of an Android app with AppScreenMap — automated checks across a crawl, a 200% font-scale crawl, device tests (rotation, Switch Access/keyboard, TalkBack spot checks), manual review of the rest, triage into notes.json, and a findings report mapped to success criteria and levels. Use when asked to audit, check, or report on an app's accessibility or WCAG conformance.
---

# WCAG 2.2 accessibility audit

Read `wcag-mobile-rules` first. It defines terms, thresholds, and how to word findings.
Target app: the Playground sample (`dev.appscreenmap.playground`; it has deliberate `A11Y BUG` screens) unless the user
names another. Default level: **AA**.

## 1. Automated pass on a normal crawl

Use the newest good run, or crawl first (`crawl-app` skill):

```bash
uv run appscreenmap a11y runs/<project>/<run-id>                 # level ≤ AA, open + confirmed issues
uv run appscreenmap a11y runs/<project>/<run-id> --level AAA --json > <scratchpad>/a11y.json
```

Every crawl also writes `<run>/a11y.json`. The web viewer's **Accessibility** tab adds the
per-screen scanner rules (labels, 48 dp guideline, contrast estimate). Look at both. Their issue
keys share one format, so one triage covers both.

If `density_exact` is false, the run predates density recording; dp values are estimates. Re-crawl
for exact numbers.

## 2. Resize text: crawl at 200%

```bash
APP_PASSWORD=playground-demo uv run appscreenmap crawl --package dev.appscreenmap.playground \
  --config samples/playground-app/appscreenmap.toml --clear-data --font-scale 2.0 --name font200
uv run appscreenmap a11y runs/playground/font200-<stamp>
uv run appscreenmap diff runs/playground/<normal-run> runs/playground/font200-<stamp>
```

The font scale is restored afterwards. Look for `text-truncated` (1.4.4), screens missing compared
to the normal run (content no longer reachable), and overlapping or clipped controls in screenshots
(1.4.4 / 1.4.10). Read the screenshots; the diff only says what changed.

## 3. Device tests (adb). Restore every setting afterwards.

| SC | Test |
|---|---|
| 1.3.4 Orientation | `adb shell settings put system accelerometer_rotation 0; adb shell settings put system user_rotation 1` → screenshot each main screen → set back to `0`. Fails if the UI stays portrait (or breaks). Manifest locks are already in `a11y.json` (`orientation-locked`). |
| 2.1.1 / 2.1.2 / 2.4.3 / 2.4.7 Keyboard & focus | Use `adb shell input keyevent KEYCODE_TAB` (and `DPAD_DOWN`, `ENTER`) and screenshot after each step: can you reach and activate every control, is focus visible, does the order make sense, can you leave every component? |
| 2.4.11 Focus Not Obscured | While tabbing, note any focused control hidden behind a sticky bar or FAB. |
| 1.3.2 / 4.1.2 TalkBack | `adb shell settings put secure enabled_accessibility_services com.google.android.marvin.talkback/com.google.android.marvin.talkback.TalkBackService` (only if TalkBack is installed). Swipe through 2–3 key screens and check the reading order and announcements. Turn it off afterwards (`settings delete secure enabled_accessibility_services`). Ask the user before enabling it, because it changes how the emulator responds to touches. |
| 3.2.1 On Focus | Focus moves alone must not navigate. |

Run device tests only with the app pinned or on screens you navigated to deliberately, and don't
leave the app (`stay_in_app` rule).

## 4. Manual review of what can't be automated

Walk the screen list (`map.json`) and screenshots, guided by each screen's `patterns`:

| Pattern | Check |
|---|---|
| `login` / `form` | 3.3.1 errors in text, 3.3.2 persistent labels, 3.3.3 suggestions, 1.3.5 input purpose (look in the app source for `autofillHints`/`contentType`), 3.3.8 paste/password manager/passkey support, 3.3.7 repeated data |
| `list` / cards | 2.4.4 / 2.4.6 specific names ("Read more about …"), 1.3.1 headings |
| `dialog` | Focus moves into the dialog and back out, 2.1.2 |
| media, timers, carousels | 1.2.x captions/transcripts, 2.2.1 time limits (a focus timer is user-started, so it's fine), 2.2.2 pause for auto-moving content |
| everything | 1.4.1 colour-only signals, 1.4.11 icon/border contrast, 1.3.3 sensory instructions, 2.5.1 gesture alternatives, 4.1.3 status messages (snackbars/toasts announced?) |

When the app's source is available (Playground: `samples/playground-app/app/`), grep it to confirm or rule out
findings: `contentDescription`, `semantics`, `Role.`, `paneTitle`, `liveRegion`, `autofillHints`,
`screenOrientation`, `maxLines`.

## 5. Triage

Each issue's status lives in `<run>/notes.json` under `a11y`: `{ "<issue key>": { "status":
"confirmed" | "wontfix" | "false_positive", "note": "…", "updated": "<iso>" } }`. The viewer edits
the same file. To write it from the CLI, load the existing file, merge your decisions, and validate
with `appscreenmap.core.notes.validate` before saving (format owned by the web session; don't change it).
`appscreenmap a11y` then hides false positives and won't-fixes.

## 6. Report

Generate the report after triage, so confirmed viewer findings and your decisions are included:

```bash
uv run appscreenmap a11y runs/<project>/<run-id> --report            # AA (default)
uv run appscreenmap a11y runs/<project>/<run-id> --report --level AAA
```

This writes `a11y-report.html` (self-contained, shareable) and `a11y-report.md` (+ `a11y/crops/`).
For every WCAG 2.2 criterion it gives a status: **Fails** (confirmed), **Issues found**, **Needs review**,
**No issues detected** (automated, not proof), **Check in viewer**, or **Not tested**. Repeated
elements (a nav item on every screen) are grouped into one finding. Open the HTML and read it before
handing it over. Then add what the generator can't know: your device and manual test results.

When writing up findings yourself (e.g. in a PR or the chat), group by success criterion, A then AA
(AAA only if asked). For each finding include:
- SC number and name, level, and status: **Fails** (confirmed) / **Needs review** / **Advisory (native)** / **Guideline only**
- Screens (ids and titles), evidence (screenshot path plus what's wrong, with dp sizes or ratios)
- Fix for Views and/or Compose (from `wcag-mobile-rules/reference/criteria.md`), as specific to
  the code as you can make it

End with:
- coverage: which criteria were tested automatically, on device, or manually, and which were not tested
- a clear statement that automated results are not a conformance claim

If the user wants a shareable report, publish it rather than leaving it in the terminal.
