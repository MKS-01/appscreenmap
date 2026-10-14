# `map.json` schema (v1)

The contract between the crawler (`apps/engine/src/appscreenmap`) and the web viewer (`web/`).
The crawler only **adds** fields within schema 1. Renaming or removing a field bumps `schema`.

## Files a run produces

```
runs/                              # crawl output, git-ignored (generated locally)
  index.json                       # catalogue of runs, rebuilt by the crawler and by `appscreenmap serve`
  <project>/                       # one folder per app, e.g. duskread/
   <run-id>/                       # e.g. duskread-20261013-015149 (ids are unique across projects)
    map.json                       # this schema; rewritten atomically after every step (poll it for live view)
    trace.jsonl                    # one JSON object per step
    screens/<sid>.png|.jpg|.xml    # full screenshot, 360px-wide thumbnail, raw uiautomator hierarchy
    flows/<sid>.yaml               # Maestro flow: launch → … → this screen
    map.mmd                        # Mermaid flowchart
    crashes/crash-<n>.txt          # logcat crash buffer
    diff/<base-run-id>/diff.json   # visual diff against another run (see bottom)
    diff/<base-run-id>/*.png       # diff overlay images
    verify/<verify-id>/verify.json # `appscreenmap verify`: this run's paths replayed on a new build (see bottom)
    verify/<verify-id>/screens|failed|diff/   # what each screen looks like now, failure evidence, diffs
    perf.json                      # navigation performance summary (see "perf" below); written after every crawl
    a11y.json                      # WCAG 2.2 crawl-level checks (see bottom); written after every crawl
    a11y-report.html               # shareable WCAG 2.2 report: self-contained (crops embedded), light/dark
    a11y-report.md                 # same report as Markdown; images in a11y/crops/*.jpg
    notes.json                     # viewer stars/notes + a11y triage (owned by the web session, notes.py)
    audits/index.json              # optional: audits this run has beyond the built-in ones (see "audits" below)
    audits/<audit-id>.json         # optional: one audit report (security, store, adaptive, …)
    audits/security-evidence.json  # written by `appscreenmap security`: the evidence behind audits/security.json
```

Older runs may sit directly in `runs/<run-id>/`. Use the index's `path` to locate a run's files.

**URLs:** `appscreenmap serve` accepts both `/runs/<path>/…` and `/runs/<run-id>/…`. It resolves a
bare run id to its project folder, so `/runs/<run-id>/map.json` and `PUT /runs/<run-id>/notes.json`
keep working. A dev server that maps `/runs` straight onto the folder must do the same
(look the id up in `index.json` → `path`, or glob `runs/*/<run-id>`).

External screens use `x:<package>` as the id. Their files use `_` in place of `:`
(`screens/x_com.android.chrome.png`). Always use the `screenshot` / `thumb` paths from the JSON
rather than building them. Paths are relative to the run directory.

## `runs/index.json`

```jsonc
{ "runs": [ {
  "id": "duskread-20261013-014108",               // unique, flat (no "/"); use in URLs/routes
  "project": "duskread",                           // folder under runs/; group runs by this
  "path": "duskread/duskread-20261013-014108",     // run folder relative to runs/
  "status": "running | done | stopped | failed",
  "started_at": "2026-10-13T01:41:08+00:00", "finished_at": null,
  "app": { "package", "label", "version", "launch_activity", "activities": [],
           "orientation_locked": { "<activity>": "portrait" } },   // from the manifest; absent on old runs
  "device": { "serial", "model", "manufacturer", "android", "sdk", "width", "height",
              "density": 420,        // dpi; px per dp = density / 160. Absent on old runs → estimate width/411
              "font_scale": 1.0 },   // system font scale during the crawl (2.0 with --font-scale 2.0)
  "steps": 93, "elapsed_s": 301.2,
  "screens": 30, "transitions": 74, "crashes": 0,
  "thumb": "duskread/duskread-20261013-014108/screens/s001.jpg",   // relative to runs/
  "diffs": ["<base-run-id>", …],                           // diff reports stored in this run
  "verifies": ["verify-20261013-101500", …]                // verify reports stored in this run (base)
} ] }
```

## `map.json`

```jsonc
{
  "schema": 1,
  "run": {
    "id", "status", "started_at", "finished_at", "updated_at",   // updated_at = heartbeat on every save
    "stop_reason": "saturated: no new screen in the last 30 steps … | step budget reached (200) | complete: nothing left to explore | stopped by user | null",
    "error": "only when status = failed",
    "tool": "appscreenmap 0.1.0", "steps": 120, "elapsed_s": 410.5,
    "app": { … as in index … }, "device": { … see below … }, "config": { /* CrawlConfig */ }
  },

  "screens": [ {
    "id": "s001",                       // app screens: s001…; external: "x:<package>"; crash: "crash"
    "kind": "app | external | crash",
    "title": "Hello, Reader",           // best-effort human name
    "activity": "dev.mks.duskread.android.MainActivity",
    "package": "dev.mks.duskread",
    "signature": "db0076db5f93",
    "patterns": ["list", "tabs", "bottom_nav", "form", "login", "dialog", "drawer", "webview", "scrollable", "empty"],
    "variant_of": null,                 // or the id of a screen with the same layout but different data
    "origin": "launch | action | unknown",  // how it's reached: app start lands here (reach_path []),
                                        // reach_path replays from launch, or no recorded path yet (first seen
                                        // after returning from another app etc.; no Maestro flow). Absent on old runs.
    "depth": 0,                         // steps from launch on the first path that found it
    "visits": 7, "first_step": 1,
    "width": 1080, "height": 2400,
    "screenshot": "screens/s001.png", "thumb": "screens/s001.jpg", "hierarchy": "screens/s001.xml",
    "reach_path": [                     // replayable steps from launch; [] for the launch screen
      { "screen": "s001", "key": "…", "action": "click", "label": "Settings",
        "selector": { "id"?: "pkg:id/x", "text"?: "…", "desc"?: "…", "point": [x, y] },
        "scroll_depth": 0 }
    ],
    "autofill": [ { "key", "label", "rid", "value", "secret", "selector" } ],   // fields typed on arrival
    // value: what was typed, or a "${NAME}" placeholder filled from the environment at type time.
    // secret: true when value contains a placeholder (absent on old runs). Never show the resolved value.
    "tokens": ["S:View|", "T:hello, reader", …],                      // identity tokens (for matching across runs)
    "elements": [ {
      "id": "e12", "key": "click|ImageView||settings",
      "kind": "nav | tab | button | list_item | toggle | scroll | long_click | up | back",
      "action": "click | long_click | scroll | back",
      "label": "Settings", "class": "android.widget.ImageView", "rid": "", "text": "", "desc": "Settings", "hint": "",
      "bounds": [931, 166, 1057, 292],  // device pixels on the screenshot; [0,0,0,0] for system back
      "group": null,                    // list group id for list items
      "password": false, "checked": null, "selected": false, "direction": null,  // scroll: "up" | "left"
      "status": "pending | done | blocked | skipped | failed | unreachable",
      "effect": "new_screen | known_screen | same_screen | left_app | crash | inferred | not_found | null",
      "target": "s004",                 // screen it leads to (when known)
      "scroll_depth": 0,                // swipes needed before it is visible
      "revealed_by": [ {step}, … ],     // optional: same-screen steps that make it appear (replayed first;
                                        // already included in reach_paths through this element)
      "note": "list pattern: first 2 items all lead to s006"   // optional, explains skipped/blocked/inferred
    } ]
  } ],

  "transitions": [ {
    "id": "t7", "from": "s001", "to": "s004", "key": "…",
    "action": "click", "label": "Settings", "kind": "button",
    "count": 3,                         // times observed (0 if only inferred)
    "step": 14,                         // step when first observed
    "inferred": false,                  // true = predicted from the same nav item on another screen
    "load_ms": 640,                     // median load time over `timings` (null if none measured)
    "timings": [ {                      // one per traversal (max 20); absent fields = not measured
      "load_ms": 640,                   // action → app stopped drawing (host clock, ~50–100 ms resolution)
      "settled": true,                  // false = still drawing at the timeout (endless animation/polling)
      "render_ms": 590,                 // first → last frame drawn (device clock, framestats)
      "frames": 31, "janky_frames": 2, "frozen_frames": 0,   // janky > 16 ms, frozen > 700 ms per frame
      "p90_frame_ms": 14.2, "max_frame_ms": 21.0,
      "waited_for_loading": true,       // a spinner/"Loading…" was on screen; timed until content drew
      "stats": { "frames", "janky_frames", "janky_pct", "p50_ms", "p90_ms", "p95_ms", "p99_ms",
                 "slow_ui_thread", "deadline_missed", "high_input_latency" }   // dumpsys gfxinfo summary
    } ]
  } ],

  "events": [ { "step": 31, "type": "crash | permission | restart | nav_failed | change_on_input", "detail": "…",
                "screen"?: "s003", "log"?: "crashes/crash-1.txt" } ],

  "perf": { "startup": [ { "step": 1, "reason": "start", "LaunchState": "COLD",
                           "TotalTime": 812, "WaitTime": 815 } ] },   // am start -W, every relaunch

  "stats": {
    "screens": 30, "external": 2, "transitions": 74, "max_depth": 4,
    "activities_visited": ["…"], "activities_declared": 3, "activity_coverage": 0.667,
    "crashes": 0, "elements": { "done": 80, "skipped": 21, "blocked": 2, "pending": 0 }
  }
}
```

### Drawing tips for the viewer

- Element overlay: scale `bounds` by `img.naturalWidth / screen.width`.
- Show `inferred` transitions as dashed edges. `back` / `up` edges are history-dependent and
  can be hidden by default.
- Group screens with `variant_of` under their base screen.
- `kind: external` nodes ("opens Chrome") and `crash` belong at the graph's edge.

### `run.device`

What the run was captured on, read once at the start of the crawl (`appscreenmap verify` writes the same
object). The flat keys at the top are the original ones and keep their meaning. The rest was added later
(absent on old runs) and is grouped. Any value can be `null` when the device doesn't report it. Nothing
personal is recorded: no user-set device name, accounts, IMEI or network names.

**iOS Simulator runs** (`crawl --platform ios`) write the same object with `"platform": "ios"` and the Android-only
parts replaced: `type: "emulator"` (a simulator), `name` "iPhone 17 (Simulator)", `os: { "name": "iOS", "release": "27.0" }`
(no `android`/`sdk`), `width`/`height` in **points** with `density: 160` so px-per-dp is 1 and the accessibility checks
read points as dp, `display.window_class`, and `font_scale` from Dynamic Type (2.0 = `accessibility-large`).
`run.app.package` is the bundle id, `activities` is `[]` and `launch_activity` is `null` (iOS has no activities; screens
are told apart by structure and text). Runs go to the project folder `<app>-ios` so they never mix with Android runs
of the same app. Not recorded on iOS yet: load times (`perf.json` has no screens), crash dialogs.

```jsonc
"device": {
  "serial": "emulator-5554", "model": "SM-S911B", "manufacturer": "samsung",
  "android": "14", "sdk": "34",                        // strings, from ro.build.version.*
  "width": 1080, "height": 2340, "density": 420, "font_scale": 1.0,   // as in index (override wins)

  "type": "emulator | physical",                       // AVD, Genymotion and other virtual devices are "emulator"
  "name": "Samsung SM-S911B",                          // display name: marketing name (ro.product.marketname …) or
                                                       // manufacturer + model; "Android Emulator (Pixel_8_API_37)"
  "brand": "samsung", "codename": "dm1q", "product": "dm1qxxx",
  "avd": "Pixel_8_API_37",                             // emulator only, else null
  "form_factor": "phone | tablet | foldable | tv | watch | automotive",
  "connection": "usb | wifi | emulator",
  "os": {
    "release": "14", "sdk": 34,                        // sdk as a number here
    "codename": "REL",                                 // anything else = preview build
    "preview_sdk": null,
    "skin": "One UI 6.1",                              // One UI, HyperOS, MIUI, ColorOS, OxygenOS, EMUI, HarmonyOS,
                                                       // realme UI, Funtouch/OriginOS; null on stock Android
    "security_patch": "2024-09-01", "build_id": "UP1A.231005.007", "incremental": "S911BXXS3BXI1",
    "build_type": "user | userdebug | eng", "build_tags": "release-keys",
    "fingerprint": "samsung/dm1qxxx/dm1q:14/…", "kernel": "5.15.123-android14"
  },
  "hardware": {
    "abi": "arm64-v8a", "abis": ["arm64-v8a", "armeabi-v7a"],
    "soc": "QTI SM8550",                               // ro.soc.* (Android 12+), else chip name / board platform
    "hardware": "qcom", "ram_mb": 7841, "storage_free_mb": 92617
  },
  "display": {
    "width": 1080, "height": 2340, "physical_width": 1080, "physical_height": 2340,
    "density": 420, "physical_density": 420,
    "width_dp": 411, "height_dp": 891, "smallest_width_dp": 411,
    "window_class": "compact | medium | expanded"      // width < 600 dp ≤ medium < 840 dp ≤ expanded
  },
  "settings": {                                        // device settings during the crawl
    "locale": "en-GB", "timezone": "Europe/London",
    "dark_mode": false,                                // null = auto / custom schedule
    "font_scale": 1.0, "bold_text": false, "high_contrast_text": false, "color_inversion": null,
    "animator_scale": 1.0,                             // before the crawl turned animations off
    "navigation": "gesture | 2-button | 3-button",
    "talkback": false, "accessibility_services": ["com.google.android.marvin.talkback/.TalkBackService"],
    "power_saver": false, "airplane_mode": false,
    "battery": 87, "charging": true
  },
  "software": {
    "webview": "com.google.android.webview 141.0.7390.43",
    "play_services": "25.38.32"                       // null when Google Play services is absent
  }
}
```

`runs/index.json` rows carry the same object. `appscreenmap report` prints a one-line summary and
**device caveats**: conditions that change what the numbers mean (emulator, power saver, low battery,
TalkBack on, font scale, dark mode, airplane mode, preview build, low storage).

## `perf.json`

Written after every crawl and by `appscreenmap perf <run> [--budget ms]`. Loads count arrivals by
navigation (back/up and scrolls excluded; inferred edges have no timings).

```jsonc
{
  "run": "<run-id>", "budget_ms": 1000, "animations": "off | on",
  "startup": { "samples": 4, "median_ms": 790, "max_ms": 820 },          // cold starts
  "screens": [ { "screen": "s002", "title": "Feed", "samples": 3, "median_ms": 3000, "p90_ms": 3100,
                 "max_ms": 3100, "janky_pct": 5.0, "frozen_frames": 1, "unsettled": 0,
                 "waited_for_loading": true, "rating": "ok | needs work | slow" } ],   // slowest first
  "transitions": [ { "from", "to", "label", "action", "kind", "samples", "median_ms", "max_ms",
                     "unsettled", "janky_frames", "frozen_frames", "waited_for_loading" } ],
  "findings": [ "s002 'Feed' loads in 3000 ms (median, budget 1000 ms)", … ]
}
```

Ratings: median ≤ budget → ok, ≤ 2.5 × budget → needs work, above → slow.

## `a11y.json`

Written by `appscreenmap a11y <run>` and at the end of every crawl. These are crawl-level WCAG 2.2
checks; the viewer's per-screen scanner rules (`web/src/a11y.ts`) are not included.

```jsonc
{
  "schema": 1, "run": "<run-id>", "standard": "WCAG 2.2",
  "dp_scale": 2.625, "density_exact": true, "font_scale": 1.0,
  "rules": { "<rule-id>": { "sc": "2.5.8", "name": "Target Size (Minimum)", "level": "AA",
                            "kind": "automated | review", "severity": "error | warning | info",
                            "why": "…", "fix": "…", "native_note": "" } },
  "summary": { "issues": 25, "open": 25, "by_level": {"A": 20, "AA": 5},
               "by_kind": {"automated": 22, "review": 3}, "by_criterion": {"4.1.2 Name, Role, Value": 20} },
  "issues": [ {
    "key": "s002::no-role::View::Home::288,2201",   // same format as the viewer's issue keys
    "screen": "s002",                               // or "app" for app-level rules (orientation)
    "rule": "no-role", "sc": "4.1.2", "level": "A", "kind": "automated", "severity": "info",
    "label": "Home", "detail": "clickable android.view.View with no role",
    "bounds": [288, 2201, 403, 2327], "rid": "", "class": "android.view.View",
    "triage": "open | confirmed | wontfix | false_positive"   // from notes.json "a11y"
  } ]
}
```

Rule ids: `target-size-min` (2.5.8), `label-in-name` (2.5.3), `not-focusable` (2.1.1), `no-role` (4.1.2),
`screen-title` (2.4.2), `nav-inconsistent` (3.2.3), `identification-inconsistent` (3.2.4),
`help-inconsistent` (3.2.6), `redundant-entry` (3.3.7), `auth-cognitive` (3.3.8), `dragging` (2.5.7),
`focus-obscured` (2.4.11), `orientation-locked` (1.3.4), `text-truncated` (1.4.4), `change-on-input` (3.2.2),
`image-alt` (1.1.1). They don't overlap the viewer's rule ids.

## `audits/<audit-id>.json`

Every audit the viewer's Insights tab shows uses this one shape. Today the viewer builds `coverage`, `stability`,
`a11y` and `perf` itself from `map.json`, `a11y.json` and `perf.json`. It shows `adaptive`, `platform`, `store`
and `security` from sample data (labelled as such) until a tool writes them. Any tool (the crawler, a jadx or
frida scanner, a CI step) can add or replace an audit by writing this file into the run folder. A file always
wins over the viewer's built-in or sample version. Ids the viewer doesn't know go in `audits/index.json` and
render with the generic layout. Only `schema`, `audit` and `findings` are required; the viewer fills defaults for
the rest.

```jsonc
// audits/index.json (optional; needed only for ids the viewer doesn't already know)
{ "audits": [ { "id": "privacy", "title": "Privacy labels" } ] }

// audits/<audit-id>.json
{
  "schema": 1,
  "audit": "security",                          // id; matches the file name
  "title": "Security",
  "tool": "jadx 1.5.1 + frida 17",              // what produced it
  "generated_at": "2026-10-13T03:20:00+00:00",
  "source": "run | sample | mixed",             // sample = placeholder data; the viewer labels it
  "status": "pass | warn | fail | info | not_run",
  "score": 61,                                  // 0–100, higher is better; null if the audit doesn't score
  "score_note": "100 minus 20 per error, 8 per warning",
  "status_label": "Blocked for Play updates",   // optional: a plainer word than the status ("Partial", …)
  "summary": "One sentence for the overview card.",
  "metrics": [ { "label": "exported components", "value": 2, "unit": "", "tone": "good | warn | bad | info",
                 "hint": "…", "sample": false } ],
  "charts": [ {                                 // declarative, so a tool ships its own charts
    "type": "bars | columns | split",           // ranked rows | ordered categories | parts of a whole
    "title": "Findings by check", "unit": "ms", "note": "…", "sample": false,
    "budget": 1000, "budgetLabel": "1000 ms budget",   // bars only: a reference line
    "data": [ { "label": "Manifest", "value": 3, "tone": "good | warn | bad | info", "screen": "s004", "hint": "…" } ]
  } ],
  "findings": [ {
    "id": "sec::cleartext",                     // stable within the audit
    "severity": "error | warning | info",
    "title": "Cleartext traffic allowed app-wide",
    "detail": "…", "fix": "…",
    "screen": "s004",                           // optional map.json screen id (linked in the viewer)
    "platform": "android | ios | both",
    "category": "Manifest",                     // groups findings within the audit
    "due": "2026-11-01",                        // optional deadline (store or platform), shown on a timeline
    "refs": [ { "title": "…", "url": "https://developer.android.com/…", "publisher": "Android Developers",
                "date": "2026-10-13" } ],
    "sample": false,                            // placeholder finding inside a real report
    "requirement": "met | due | blocked | upcoming | not_checked"   // optional: a store/platform requirement's state
  } ],
  "refs": [ { "title": "…", "url": "…", "publisher": "…", "date": "…" } ]   // official docs the checks follow
}
```

Cite official sources only (Android Developers, Google Play, Apple Developer, W3C). The viewer's catalogue of
sources is `web/src/insights/sources.ts`. Update it when a platform or store publishes its yearly changes.

## `diff/<base>/diff.json`

```jsonc
{
  "base_run": "…", "cand_run": "…", "base_app": {…}, "cand_app": {…},
  "summary": { "changed": 2, "new": 1, "missing": 0, "same": 25 },
  "items": [ {
    "status": "changed | new | missing | same",
    "base": "s003", "cand": "s003", "title": "Settings", "similarity": 1.0,
    "diff": "diff/<base>/s003__s003.png",   // relative to the candidate run dir
    "changed_ratio": 0.0132, "bbox": [x1, y1, x2, y2],
    "regions": [ { "bounds": [x1, y1, x2, y2], "cells": 14,      // changed pixel areas, largest first (≤ 12)
                   "direction": "brighter | darker | changed",   // candidate vs base luminance
                   "delta": -38.2 } ],                           // mean luminance change (0–255 scale)
    "text": {                                                    // null when a hierarchy is missing
      "added": 1, "removed": 0, "moved": 1, "changed": 1,
      "changes": [ {
        "type": "added | removed | moved | changed",
        "text": "Log out",                    // candidate text (base text for removed)
        "base_text": "Sign out",              // changed only
        "digits_only": false,                 // changed only: only digits differ (clock, counter)
        "base_bounds": [x1, y1, x2, y2] | null, "cand_bounds": [x1, y1, x2, y2] | null,
        "rid": "pkg:id/signout"
      } ]                                     // sorted top to bottom
    }
  } ]
}
```

Base screenshots live in the base run: `runs/<base_run>/<base screen's screenshot>`. Bounds are in each
screen's own pixels (`base_bounds` → base screenshot, `cand_bounds` → candidate). A screen counts as
`changed` when the changed pixel ratio is above 0.2% or a text change isn't `digits_only`. The overlay PNG
outlines text changes: added green, changed/moved amber, removed blue.

## `verify/<verify-id>/verify.json`

Written by `appscreenmap verify <base-run>` inside the base run. Paths are relative to the verify folder.

```jsonc
{
  "schema": 1, "id": "verify-20261013-101500", "base_run": "<run-id>",
  "status": "done | aborted", "error"?: "…", "ok": true,      // ok: done and no failed screen
  "started_at", "finished_at",
  "app": { "package", "version" }, "base_app": { … }, "device": { … },
  "clear_data": true, "threshold": 0.6,
  "summary": { "passed": 9, "failed": 1, "blocked": 1, "skipped": 0, "changed": 2 },
  "screens": [ {                                              // failed, blocked, passed (changed first), skipped
    "screen": "s005", "title": "Settings",
    "status": "passed | failed | blocked | skipped",
    "path": ["s001", "s002"],                                 // screens passed on the way here
    // passed
    "similarity": 0.94, "load_ms": 420,
    "via": "key | id | text | desc | label | point | back",  // how the last step's element was found
    "screenshot": "screens/s005.png", "hierarchy": "screens/s005.xml",
    "changed": true,
    "visual": { "diff": "diff/s005.png", "changed_ratio", "bbox", "regions", "text" },   // as in diff.json
    // failed
    "failure": {
      "reason": "not_found | wrong_screen | left_app | crash | not_launched",
      "detail": "'Settings' is not on s002",
      "step": 1, "on": "s002", "action": "click | long_click | back | launch", "label": "Settings",
      "expected": "s005", "got": "s007" | null,
      "screenshot": "failed/s009.png", "hierarchy": "failed/s009.xml"   // named after the replayed target
    },
    // blocked
    "blocked_by": "s005",
    // skipped (not a failure): "no recorded path"; "same recorded path as s005: …" (two screens behind the
    // same steps, told apart only by app state); "'14:59 / OPEN' wasn't on s002 when the crawl first saw
    // it: …" (keeps "failure" as evidence); "behind s008, whose path depends on app state"
    "note": "…"
  } ]
}
```

A step whose element is missing on the new build fails if the base run's capture of that screen had the
element, or if the element has `revealed_by` (those steps are in the path and were replayed first). If
neither, the crawl reached the screen through app state its path doesn't record (runs from before
`revealed_by`), so the path can't work from a fresh launch on any build, and the screen is skipped.
Replay fills a screen's `autofill` fields once per arrival, not before every step taken on it.
