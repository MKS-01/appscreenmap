---
name: crawl-app
description: Run an AppScreenMap crawl of an Android app on an emulator and review the result. Use when asked to map/crawl/explore an app, demo the tool, capture an app's empty or first-run state, re-map after a new build, or compare two builds visually.
---

# Crawl an app and review the map

## 1. Preflight

```bash
uv run appscreenmap doctor
```

Everything except the web viewer build must show ✔. If several devices are connected, pass
`--serial`.

**Target app:** use **sample-app** (`dev.mks.sample-app`) unless the user names another app.
Don't crawl stock emulator apps for testing. The sample-app APK is built at
`../sample-app/androidApp/build/outputs/apk/debug/androidApp-debug.apk`.

**Clean slate:** `--clear-data` wipes app data, so the map starts from the first-run state
(onboarding, empty lists). Use it unless the user wants their current data mapped.

## 2. Run

Run in the background so the user can follow along and stop it:

```bash
uv run appscreenmap crawl --package dev.mks.sample-app --clear-data --max-steps 200 \
  > <scratchpad>/crawl.log 2>&1        # run_in_background: true
```

Watch for discoveries and every way the run can end, not just success:

```bash
tail -n 0 -f <scratchpad>/crawl.log | grep -E --line-buffered "★|⏹|✔|✘|💥|Traceback|Error|could not|stopped"
```

The crawl stops itself when one of these happens:
- `complete: nothing left to explore`
- `saturated: no new screen in the last N steps` (`stop_after_no_new`, default 30)
- the step or time budget runs out

To stop early, stop the background task. SIGTERM is handled: the run is saved as `stopped`,
the app is unpinned, and animations are restored.

Output goes to `runs/<project>/<run-id>/` (project = last part of the package, or `--project`).
Runs are committed as samples, so delete broken or throwaway runs before committing.

**iOS Simulator.** Build the app for the simulator (`xcodebuild -sdk iphonesimulator`; an `.ipa` can't run there),
boot a simulator (Xcode 27 replaced Simulator.app with Device Hub), then:

```bash
uv run appscreenmap doctor    # lists booted simulators, idb and idb_companion
uv run appscreenmap crawl --platform ios --app path/to/sample-app.app --clear-data --max-steps 150
```

It reads the accessibility tree (what VoiceOver sees) and taps through `idb`; a control with no accessibility label or
identifier is invisible to the crawler, which is itself the finding. A tree with no content (in-app browser, system
sheet) counts as leaving the app: the crawl restarts the app instead of pressing Back. Runs go to `runs/<app>-ios/`.
Needs `brew install facebook/fb/idb-companion` and `uv tool install fb-idb`. sample-app (`../sample-app/iosApp`) is the sample.

Useful flags: `--apk <file>` (installs first), `--max-minutes`, `--settle 1.2` (slow apps),
`--config examples/appscreenmap.toml` (test credentials in `[inputs]`, extra `blocked_text`).

## 3. Review

```bash
uv run appscreenmap report runs/<project>/<run-id>
```

Read the `findings`. Then check navigation performance:

```bash
uv run appscreenmap perf runs/<project>/<run-id>            # slowest screens, transitions, jank, cold start
```

Compare load times only between runs on the same device with the same animation setting
(`perf.json` → `animations`). Use `--keep-animations` when the user wants times as users perceive them.

Then sanity-check the map itself:

```bash
python3 -c "
import json,sys; d=json.load(open('runs/<project>/<run-id>/map.json'))
for s in d['screens']: print(s['id'], s['kind'], repr(s['title']), s['patterns'], s.get('variant_of'), 'depth', s.get('depth'))
"
```

Spot-check 2–3 screenshots in `runs/<project>/<run-id>/screens/` with the Read tool. Do the titles match what's
on screen? Does the first screen show the empty state?

Things to call out to the user:
- Screens that should exist but are missing (compare against what the app's source shows).
- Two ids that are really one screen, or one id covering two screens → use the `tune-crawler` skill.
- Any `left_app` effect or `x:` screen. With `stay_in_app` on, this should not happen.
- Crashes (`crashes/crash-N.txt`).

## 4. Use the output

- Viewer: `uv run appscreenmap serve` (needs `web/dist`; the web session owns that build).
- Maestro flow to reach a screen: `runs/<project>/<run-id>/flows/s004.yaml` → `maestro test …`.
- Visual diff between two builds: crawl each, then
  `uv run appscreenmap diff runs/<project>/<old> runs/<project>/<new>`. The report lands in `<new>/diff/<old-id>/`.

## 5. Report back

Give the user: stop reason, screens/transitions/steps/time, the screen list with titles, and
the top findings with a recommended next step (usually `tune-crawler` for one specific finding).
Delete runs you started that ended up broken or unwanted, and say that you did.
