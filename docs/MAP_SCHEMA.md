# `map.json` schema (v1)

The contract between the crawler (written by `packages/core/src/appscreenmap/core/model.py`) and the web viewer (`apps/viewer/`).
The crawler only **adds** fields within schema 1. Renaming or removing a field bumps `schema`.

## Files a run produces

```
runs/                              # crawl output, git-ignored (generated locally)
  index.json                       # catalogue of runs, rebuilt by the crawler and by `appscreenmap serve`
  <project>/                       # one folder per app, e.g. playground/
   <run-id>/                       # e.g. playground-20261013-015149 (ids are unique across projects)
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
    notes.json                     # viewer stars/notes, a11y triage, map comments and tree edits (notes.py)
    audits/index.json              # optional: audits this run has beyond the built-in ones (see "audits" below)
    audits/<audit-id>.json         # optional: one audit report (security, store, adaptive, …)
    audits/security-evidence.json  # written by `appscreenmap security`: the evidence behind audits/security.json
    audits/stack.json              # written by `appscreenmap stack`: what the app is built with (see "audits/stack.json")
    build/apks/*.apk               # `stack`: the scanned build as pulled from the device (base + splits), latest only
    build/dumpsys-package.txt      # `stack`: `dumpsys package <pkg>` at scan time, for the security scan and Frida probe
    network.jsonl                  # `crawl --network`: one line per connection or request the app made (see "network" below)
    network-proxy.log              # `crawl --network`: mitmdump's own output, for when capture fails
    logs.jsonl                     # `crawl --logs` (on with --network): the app's own log lines, masked (see "logs" below)
    timeline.jsonl                 # every crawl: which screen was showing from when (see "timeline" below)
    sessions/<session-id>/         # `watch`: a person used the app by hand while AppScreenMap recorded (see "sessions")
```

Older runs may sit directly in `runs/<run-id>/`. Use the index's `path` to locate a run's files.

**URLs:** `appscreenmap serve` accepts both `/runs/<path>/…` and `/runs/<run-id>/…`. It resolves a
bare run id to its project folder, so `/runs/<run-id>/map.json` and `PUT /runs/<run-id>/notes.json`
keep working. `DELETE /runs/[<project>/]<run-id>` deletes one run folder (the Runs page's delete button; same-machine
pages only, refused with 409 while the crawl is running) and rebuilds `index.json`. A dev server that maps `/runs` straight onto the folder must do the same
(look the id up in `index.json` → `path`, or glob `runs/*/<run-id>`).

External screens use `x:<package>` as the id. Their files use `_` in place of `:`
(`screens/x_com.android.chrome.png`). Always use the `screenshot` / `thumb` paths from the JSON
rather than building them. Paths are relative to the run directory.

## `runs/index.json`

```jsonc
{ "runs": [ {
  "id": "playground-20261013-014108",              // unique, flat (no "/"); use in URLs/routes
  "project": "playground",                         // folder under runs/; group runs by this
  "path": "playground/playground-20261013-014108", // run folder relative to runs/
  "status": "running | done | stopped | failed",
  "started_at": "2026-10-13T01:41:08+00:00", "finished_at": null,
  "app": { "package", "label", "version", "launch_activity", "activities": [],
           "orientation_locked": { "<activity>": "portrait" } },   // from the manifest; absent on old runs
  "device": { "serial", "model", "manufacturer", "android", "sdk", "width", "height",
              "density": 420,        // dpi; px per dp = density / 160. Absent on old runs → estimate width/411
              "font_scale": 1.0 },   // system font scale during the crawl (2.0 with --font-scale 2.0)
  "steps": 93, "elapsed_s": 301.2,
  "screens": 30, "transitions": 74, "crashes": 0,
  "thumb": "playground/playground-20261013-014108/screens/s001.jpg", // relative to runs/
  "diffs": ["<base-run-id>", …],                           // diff reports stored in this run
  "verifies": ["verify-20261013-101500", …],               // verify reports stored in this run (base)
  "stack": { "kind": "native | cross-platform | kmp",      // optional: from audits/stack.json (`appscreenmap stack`)
             "summary": "Native Android: Kotlin, Jetpack Compose", "version": "2.0", "generated_at": "…" }
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
    "app": { … as in index … }, "device": { … see below … }, "config": { /* CrawlConfig */ },
    "network": {                        // only with `crawl --network`; absent otherwise
      "mode": "observe", "tool": "mitmproxy", "log": "network.jsonl",
      "status": "recording | done | lost",  // lost: the proxy stopped mid-crawl (the device's setting was put back)
      "events": 3, "hosts": 3, "cleartext_hosts": ["cdn.playground.test"]
    },
    "logs": { "log": "logs.jsonl", "source": "logcat", "lines": 42 }  // only with --logs / --network
  },

  "screens": [ {
    "id": "s001",                       // app screens: s001…; external: "x:<package>"; crash: "crash"
    "kind": "app | external | crash",
    "title": "Hello, Reader",           // best-effort human name
    "activity": "dev.appscreenmap.playground.MainActivity",
    "package": "dev.appscreenmap.playground",
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
    "captures": { "bottom": "screens/s001-bottom.png" },  // extra shots of the screen; {} when none
    "source": "manual",                 // optional: filed by hand (`add-screen`), absent on crawled screens. A manual
                                        // screen has origin "unknown" and reach_path [] (nothing replayable, so no
                                        // Maestro flow or `route` steps until a crawl reaches it); `added_at` is its time
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
    "source": "manual",                 // optional: the link of a manually added screen (count 0, step 0)
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

## Canvases (merged runs) and `notes.json` comments and edits

**Scenarios.** `appscreenmap merge <run>... [--into <canvas>]` puts several runs of one app on one canvas. The merged
`map.json` keeps schema 1 and only adds fields: `run.scenarios[]` (`id`, `label`, `run_id`, `started_at`,
`finished_at`, `steps`, `screens[]`, `entry[]` (the scenario's launch screens), `playbook`), `run.merged_from[]`, and a
`scenario` id on every screen, transition and event. Screens are renumbered `s001…` (external `x:` screens are shared),
steps keep the scenarios in order, each scenario keeps its own entry, so the viewer draws one tree per scenario.
`--into` adds the runs to an existing canvas in place (same id and folder); its `notes.json` and `titles.json` (and
the sources') follow the screens to their new ids. `--move` then deletes the merged runs' own folders, so an app keeps
one canvas. Captures follow too: each source's `network.jsonl`, `logs.jsonl`, `timeline.jsonl` and `trace.jsonl` (so Crawl
replay works on a canvas) rows are concatenated with a `scenario` id (any `screen` renumbered, any `step` shifted like the transitions'), manual `sessions/<id>/` are copied with their screen ids renumbered, and a run's
`run.network` / `run.logs` summary moves to its scenario entry (`run.scenarios[].network`, `.logs`); a canvas has no
run-level `network` or `logs`. Tool output (`audits/`, `build/`) is kept; on the same file, the later source wins.

**Screens added by hand.** `appscreenmap add-screen <canvas> --image <png> --title "…" [--from <screen> --via "<label>"]
[--scenario <id>] [--hierarchy <xml>]` (or `POST /api/runs/<canvas>/screens`, multipart) files a screen a crawl missed:
the image goes to `screens/<id>.png` (+ thumb), the row gets `source: "manual"`, and with a parent one transition is
added. `edit-screen` / `PATCH /api/runs/<canvas>/screens/<id>` changes a manual screen's title, parent link or
scenario, rewriting `map.json`, `titles.json` and `notes.json` (`edits.titles`) together; crawled screens are never
edited. Both then re-run the Maestro export and the accessibility audit. Over HTTP, `POST` takes the image, title, parent, via, scenario
and hierarchy and `PATCH` takes title, parent, via and scenario; replacing an image or hierarchy, extra captures and
`--new-scenario` are CLI-only for now. Ids continue the canvas's own; nothing existing
is renamed.

**Comments and edits** live in `notes.json` next to `map.json` (`appscreenmap_notes: 1`, validated by `notes.py`), never in
`map.json`, so the crawler's output stays the contract:

```jsonc
"comments": { "<id>": {
  "id": "<id>", "x": 12, "y": 40,          // flow coordinates; with "screen", an offset from that card's top-left
  "screen": "s005",                        // optional: the pin follows this screen
  "tag": "bug | flow | copy | question", "status": "open | resolved", "text": "…",
  "replies": [{ "text": "…", "created": "…" }], "created": "…", "updated": "…" } },
"stickies": { "<id>": {
  "id": "<id>", "x": 12, "y": 40,          // same coordinates as comments: flow space, or an offset from "screen"
  "screen": "s005",                        // optional: the note follows this screen
  "text": "…", "created": "…", "updated": "…" } },   // sticky notes: optional, drawn flat in the viewer and in the SVG export
"edits": {
  "titles":  { "s003": "Sign-up chooser" },   // renamed screens
  "deleted": ["s009"],                         // taken out of the tree; their children move up
  "parents": { "s010": "s004", "s018": null }, // moved under another screen (null: a root of its own)
  "added":   { "n-lx3k": { "title": "Forgot password", "parent": "s003", "created": "…" } }, // planned screens
  "labels":  { "s004": "Sign in" }             // label of the tree link into a screen (from its tree parent)
},
"layout": { "s010": { "x": 640, "y": -120 } },   // where a card was dragged to (flow coordinates), by screen id; optional
"tree_order": ["s001", "s010", "s020"]           // the trees' roots, left to right; roots not listed follow, optional
```

`layout` and `tree_order` are additive in `notes.json` (absent on old files, read as `{}` and `[]`). They live here, not
in the browser, so a cleared cache keeps them. Positions are finite numbers within ±1,000,000, at most 5,000 cards;
`tree_order` holds at most 1,000 unique ids. A merge carries both to the new screen ids.

The viewer applies `edits` on top of the map (toolbar: select, comment, sticky note, add, move under, rename, remove, undo; dropping
a card on another in the Tree also moves it under). Planned screens are drawn dashed, without a screenshot, and have
no screen page. Open comments and edits are the to-do list for fixing the flow.

## `network.jsonl`

Written live during `crawl --network` by the mitmproxy addon (`packages/security/.../hooks/mitm_observe.py`), one JSON
object per line. **Metadata only**: never a body, a header value, a cookie or a query value, and any value the crawler
typed from `${ENV}` inputs is masked (`••••`) before the line is written. Lines without `"asm": 1` are not ours; skip them.

```jsonc
{ "asm": 1, "event": "connect", "source": "proxy", "mode": "observe",
  "t": 1792608295.581,                  // Unix seconds, measured at the proxy (not on the device)
  "host": "api.playground.test", "port": 443 }           // an HTTPS tunnel; observe mode never sees inside it

{ "asm": 1, "event": "connect_failed", …, "host": "api.playground.test", "port": 443,
  "error": "[Errno 8] nodename nor servname provided, or not known" }

{ "asm": 1, "event": "request", "source": "proxy", "mode": "observe", "t": 1792608295.6, "t_end": 1792608295.85,
  "method": "GET", "scheme": "http", "host": "cdn.playground.test", "port": 80,
  "path": "/banner.png",                // without the query string
  "query_keys": ["size"],               // names only, never values
  "status": 200, "content_type": "image/png", "bytes_out": 0, "bytes_in": 38211, "http_version": "HTTP/1.1",
  "error": "…" }                        // status, content_type, t_end absent when the request failed
```

After the crawl, each row also gets the screen showing when it started, from `timeline.jsonl`: `"screen": "s004"`,
`"screen_title"` (the screen's final title; absent when it has none), `"step"` (all absent before the first screen;
rows written while the crawl runs don't have them yet). The proxy is device-wide, so hosts include the device's own
background traffic (Google Play services, other apps) on whatever screen was showing.
A `request` row also has `"timing": {"connect", "tls", "send", "wait", "receive"}` in ms when mitmproxy recorded them:
the time between the proxy and the server, so proxy-measured too. `connect` and `tls` appear only on the request that
opened the connection, and there is no DNS phase (mitmproxy resolves inside `connect`).

`event`: `connect` (an HTTPS tunnel opened), `connect_failed` (the proxy could not reach that host), `request` (a request
read in full: plain `http://` in observe mode). The proxy sees only apps that use the system proxy; an app that bypasses
it leaves no lines, which means "not seen", never "no requests".

## `logs.jsonl`

The app's own log lines (`adb logcat --pid`, followed across app restarts), one JSON object per line. Masked before the
line is written: values the crawler typed from `${ENV}` inputs become `••••`, and token-shaped values (JWTs, bearer
tokens, the key formats of `secrets.py`) become `[<kind> · sha <8 hex>]`, so `sensitive-logging` can report them
without the value.

Log lines are tied to screens by the device clock against the host's: on an emulator the two agree to well under
0.1 s (the emulator takes the host's time). A real device with a drifting clock would need an offset.

```jsonc
{ "asm": 1, "event": "log", "source": "logcat", "t": 1792608295.581,   // Unix seconds, device clock
  "pid": 4321, "level": "verbose | debug | info | warn | error | fatal", "tag": "PlaygroundNet",
  "message": "GET https://api.playground.test/v1/status -> failed: UnknownHostException" }
```

## `timeline.jsonl`

Written by every crawl as it goes (and by `watch`, per session), one line per screen per step:

```jsonc
{ "t": 1792610929.09, "step": 4, "screen": "s004", "title": "Network check" }   // Unix seconds, host clock
```

`t` is when the input that led there landed (the tap, back or launch), not when the screen finished loading, so
requests a screen makes while it loads are its own. A screen that changes by itself is timed when the crawler saw it.
The crawl uses it to fill `screen`, `screen_title` and `step` in `network.jsonl` and `logs.jsonl`.

## `sessions/<session-id>/` (manual sessions)

Written by `appscreenmap watch`, or by the dashboard's Start debugging (`serve` runs `watch`): a person uses the app by
hand (AppScreenMap taps nothing) and the session is saved in the app's canvas. Same row formats as above, plus the screen each row belongs to.

```
sessions/session-20261022-101500/
  session.json      { "id", "kind": "manual", "started_at", "finished_at", "status": "recording | done | failed",
                      "run": "<canvas run id the screens were matched against>", "app": {package, version, label},
                      "device": { … }, "logs": {"log", "lines"} | null,
                      "network": {"mode", "tool", "log", "status", "events", "hosts", "cleartext_hosts"} | null,
                      "screens": ["s004", "s012"],       // mapped screens visited
                      "screenshots"?: ["screenshots/b2b-01-choose.png"] }   // extra shots filed with the session by hand
  timeline.jsonl    { "t", "screen": "s004" | null, "title", "similarity",
                      "package"?: "<other app in front>", "activity"?: "<in the app, a screen the map doesn't have>" }
  logs.jsonl        log rows + "screen", "screen_title" (the screen showing when the line was written)
  network.jsonl     network rows + "screen", "screen_title" (with --network)
  watch.log         only when started from the dashboard: watch's own output, for when it fails
```

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
  "network": {                                         // null without network.jsonl
    "measured": "proxy", "events": 8, "unattributed": 0,   // rows on no screen (before the first, or older runs)
    "screens": [ { "screen": "s004", "title": "Network check", "requests": 1, "tunnels": 4, "failed": 4,
                   "cleartext": 0, "hosts": ["api.playground.test", …],
                   "slowest": { "method", "host", "path", "ms", "phase": "wait | … | null" } | null } ]  // slowest first
  },
  "findings": [ "s002 'Feed' loads in 3000 ms (median, budget 1000 ms)",
                "s004 'Network check' waits 1400 ms on GET cdn.playground.test/banner.png (proxy-measured, mostly wait)", … ]
}
```

A screen's `slowest` request over the budget is a finding. Ratings: median ≤ budget → ok, ≤ 2.5 × budget → needs work, above → slow.

## `a11y.json`

Written by `appscreenmap a11y <run>` and at the end of every crawl. These are crawl-level WCAG 2.2
checks; the viewer's per-screen scanner rules (`apps/viewer/src/a11y.ts`) are not included.

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
sources is `apps/viewer/src/insights/sources.ts`. Update it when a platform or store publishes its yearly changes.

### `audits/stack.json`

`appscreenmap stack --package <pkg>` reads the app installed on the emulator: `dumpsys package` and the APKs pulled
from the device (base and splits). Status is `info`, or `warn` / `fail` when a finding is (16 KB page alignment, no 64-bit
native code); `score` is null. Beyond the shape above it adds a `facts` block. Every signal says where it came from
(`source`: `device` today, `runtime` from the Frida probe) and how sure it is (`confidence`: `certain` only that stack
ships it, `strong` a marker its build leaves, `likely` a hint). KMP on Android is never more than `likely`.

```jsonc
"facts": {
  "platform": "android", "package": "dev.appscreenmap.playground",
  "version": "2.0", "version_code": 2,
  "min_sdk": 26, "target_sdk": 35, "compile_sdk": 35,      // the device's min/target; compileSdk from the manifest; null = unknown
  "debuggable": true, "installer": null, "signing_version": 2, "primary_abi": "arm64-v8a",
  "apks": ["base.apk", "split_config.arm64_v8a.apk"],
  "abis": ["arm64-v8a"],
  "stack": { "kind": "native | cross-platform | kmp", "summary": "Native Android: Kotlin, Jetpack Compose" },
  "signals": [ { "id": "compose", "label": "Jetpack Compose",
                 "category": "framework | runtime | language | ui | kmp",
                 "confidence": "certain | strong | likely", "evidence": ["META-INF/…version"], "source": "device" } ],
  "native_libs": [ { "name": "libflutter.so", "abis": ["arm64-v8a"],
                     "library": { "label": "Flutter", "team": "Google", "url": "…" } } ],   // library: LibChecker-Rules, when known
  "components": [ { "name": "com.google.firebase…FirebaseMessagingService", "library": { … } } ],  // known ones only
  "libraries": [ { "name": "androidx.compose.ui:ui", "version": "1.7.5" } ],   // from META-INF/*.version
  "storage": [ {                                // where the app keeps data, for the data-at-rest scan
    "id": "flutter-secure-storage", "label": "flutter_secure_storage",
    "encrypted": true,                          // true | false | null (optional, depends on the app's setup)
    "locations": ["shared_prefs/FlutterSecureStorage.xml"],   // under /data/data/<pkg>/
    "confidence": "strong", "evidence": ["com.it_nomads.fluttersecurestorage"], "source": "device" } ],
  "page_16k": [ { "path": "lib/arm64-v8a/libx.so", "abi": "arm64-v8a", "align": 4096,
                  "elf_ok": false, "zip_ok": null } ],    // zip_ok null: stored compressed
  "notes": ["…"]                                // what could not be read, and why
}
```

A scan of an app with no canvas creates one with zero screens, `run.steps` 0 and `run.source: "scan"`; merging a
crawl into it adds no empty scenario, and the MCP server's default run skips it. `audits/` and `build/` follow a canvas through `merge --into` (`audits/index.json` lists are joined).

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
