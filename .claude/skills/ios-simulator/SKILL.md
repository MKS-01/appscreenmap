---
name: ios-simulator
description: Set up, run and debug AppScreenMap against an iOS Simulator — building DuskRead for the simulator, booting it (Xcode 27 Device Hub), installing idb, reading the accessibility tree, recording a test fixture, and diagnosing a bad iOS crawl (missing tab bar, in-app browser, flat trees, stuck screens). Use for any iOS work: `crawl --platform ios`, `doctor` showing no simulator, an iOS crawl that stops early or maps too little, or extending `drivers/ios.py` / `drivers/ios_hierarchy.py`.
---

# iOS Simulator: set up, run, debug

AppScreenMap drives a simulator with two tools, because neither does the whole job:

| Tool | Does | Cannot |
|---|---|---|
| `xcrun simctl` | boot/shutdown, install, launch/terminate, screenshots, permissions (`privacy`), Dynamic Type / appearance / contrast (`ui`), status bar, keychain, push, openurl | tap, swipe, type, read the UI tree |
| `idb` (`idb_companion` + `fb-idb` client) | accessibility tree (`ui describe-all`), tap / swipe / text / key, `ui quiet` (idle + no animations), scroll, rotate, hinge, crash list, video, xctrace | build or install simulators |

Code: `packages/drivers/src/appscreenmap/drivers/ios.py` (the driver the explorer calls) and `ios_hierarchy.py` (iOS tree → the
uiautomator-style XML the analyzer reads). Design and status: `docs/PLAN.md` §8.3.

## 1. Preflight

```bash
uv run appscreenmap doctor     # needs: a booted simulator, idb client, idb_companion
brew install facebook/fb/idb-companion
uv tool install fb-idb         # puts `idb` on PATH (uvx --from fb-idb idb also works, ~1 s slower)
xcrun simctl list devices available | head
xcrun simctl boot "iPhone 17"
```

- **Xcode 27 has no Simulator.app.** Its replacement is **Device Hub**:
  `open /Applications/Xcode.app/Contents/Applications/DeviceHub.app`. A simulator also runs headless, so a booted device
  with no window is normal; open Device Hub to watch it.
- `idb` talks to a companion process. The driver finds the booted simulator on its own; to check by hand:
  `idb_companion --udid <UDID> --grpc-port 10882 &` then `idb connect localhost 10882`, then `idb ui describe-all --udid <UDID>`.
- One booted simulator is picked automatically; with several, pass `--serial <udid>`.

## 2. Build the app (DuskRead is the sample)

A simulator runs a **`.app` from an `iphonesimulator` build**. An `.ipa` is device-signed (arm64, provisioning) and will not
run there; the driver rejects it. DuskRead (`../duskread/iosApp`) is SwiftUI over a Kotlin Multiplatform core:

```bash
cd ../duskread/iosApp
xcodebuild -project iosApp.xcodeproj -scheme iosApp -sdk iphonesimulator -configuration Debug \
  -destination 'platform=iOS Simulator,name=iPhone 17' -derivedDataPath <scratch>/dd CODE_SIGNING_ALLOWED=NO build
# → <scratch>/dd/Build/Products/Debug-iphonesimulator/DuskRead.app
```

The first build runs Gradle to compile the Kotlin framework (minutes); later ones are fast. Don't edit the duskread repo
unless asked: the owner fixes what the crawl finds there and re-crawls to verify.

## 3. Crawl

```bash
uv run appscreenmap crawl --platform ios --app <path>/DuskRead.app --clear-data --max-steps 150
uv run appscreenmap serve        # the run is in runs/duskread-ios/
```

`--font-scale 2.0` sets Dynamic Type to `accessibility-large` (WCAG 1.4.4). Load times and system permission alerts aren't
supported yet. `--package <bundle id>` re-crawls an already installed app.

## 4. How the iOS tree behaves (what surprised us)

- **Flat.** SwiftUI exposes one flat list under the Application node; `--nested` doesn't add structure. Grouping-based
  detection (repeated list items) has less to go on than on Android.
- **Coordinates are points** (402×874 on an iPhone 17); screenshots are 3× pixels. The driver reports `density: 160`
  so px-per-dp = 1 and the a11y checks read points as dp.
- **Off-screen nodes are included** (the tree lists the whole scroll content); `ios_hierarchy` clips to the screen and drops
  what isn't visible.
- **`Scrollable` appears in every node's traits.** It's noise; scrollability comes from the element type (ScrollView, Table…).
- **Only what VoiceOver sees exists.** A control with no label/identifier or that isn't an accessibility element is not in
  the tree, so the crawler can't see or tap it. That is a finding about the app, not a crawler bug.
- **Out-of-process UI has a one-node tree**: an in-app browser (SFSafariViewController), share sheet, system alert. The
  driver reports package `ios.external` and the explorer restarts the app. Another app in front (Safari…) is matched by pid.
- **No activities and no Back key.** Screens are told apart by structure + text. `back()` is the edge swipe.

## 5. Diagnose a bad crawl

| Symptom | Likely cause | What to do |
|---|---|---|
| "nothing left to explore" after a few screens | The navigation (tab bar, close button) isn't in the accessibility tree | `idb ui describe-all` on that screen; if the control is absent, it's an app finding. Check for `.accessibilityLabel` / traits in the Swift view. |
| Lots of `x:com.apple.mobilesafari` or `ios.external` screens | Links open Safari / an in-app browser | Expected; they are recorded as external and the app restarts. Block the link label in `blocked_text` to stop tapping it. |
| Same screen mapped many times | Live content (timers, clocks, "1h ago") in the signature | Check `apps/engine/tests/` for the normalisation rules; digits are masked, words are not. Add a test, then tune like `tune-crawler`. |
| Blank elements list | Tree returned only the Application node | A system sheet is in front, or the app hasn't drawn yet: take `simctl io screenshot`, raise `--settle`. |
| `idb describe-all returned no tree` | Companion not running / simulator not booted / wrong UDID | `doctor`; `idb list-targets`; kill stray `idb_companion` and retry. |
| Tap does nothing | Off-screen or covered element, or coordinates in pixels | Taps are points. `idb ui describe-point x y` shows what is there. |
| Crawl taps something destructive | Label isn't in `blocked_text` | Add the wording to `DEFAULT_BLOCKED_TEXT` (`config.py`) with a test. |

## 6. Record a test fixture

Tests never need a device. To capture a tree:

```bash
idb ui describe-all --udid <UDID> | python3 -c "import sys,json; d=json.load(sys.stdin); json.dump(d[:30], open('packages/drivers/tests/fixtures/<name>.json','w'), indent=1)"
```

Shorten long text (no personal content), keep the Application node first, and test the translation in
`packages/drivers/tests/test_ios_hierarchy.py` (`idb_to_xml` → `analyze`). The driver takes an injectable runner (`run=`), so command output can
be faked without a simulator.

## 7. Not used yet (worth a look)

`idb ui quiet` (a real "settled" signal instead of fixed waits), `idb crash list` (cleaner than scanning DiagnosticReports),
`idb xctrace record` (Instruments traces for load times), `idb rotation` / `idb hinge` (orientation and fold conditions for
the adaptive audit), `idb video` (screen recordings), `simctl ui … increase_contrast|appearance` (condition matrix),
`simctl status_bar` (clean store screenshots), `simctl push` (notification flows).
