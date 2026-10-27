---
name: stack-ios
description: Build and run the iOS side of the app stack scan — reading an app installed on the iOS Simulator (its .app and data container via simctl), fingerprinting the bundle (Frameworks/, Info.plist, Mach-O load commands, Kotlin/Native and Compose markers), mapping where it keeps data, and the Frida attach spike. Use when implementing or debugging `appscreenmap stack` for iOS (docs/PLAN.md §8.6, iOS stages), adding an iOS stack rule, or when an iOS scan names the wrong framework.
---

# iOS stack scan

The Android scan (`packages/stack`) reads the app installed on the emulator. iOS does the same on a booted **simulator**:
no upload, no device: `appscreenmap stack --platform ios --package <bundle-id>` (or New project in the dashboard, which
lists booted simulators beside emulators).

| File | What |
|---|---|
| `packages/stack/.../macho.py` | load commands, thin and fat (arm64 slice), `LC_BUILD_VERSION`, `LC_VERSION_MIN_IPHONEOS`, `LC_ENCRYPTION_INFO(_64)` |
| `packages/stack/.../ios.py` | `fingerprint_app(.app)`: Info.plist, `Frameworks/`, bundle paths, binary strings, database names |
| `packages/stack/.../detect.py` `IOS_RULES`, `storage.py` `IOS_STORAGE` | the iOS rules (kinds below) |
| `packages/stack/.../audit.py` `build_ios_audit` | → `audits/stack.json` (`facts.platform: "ios"`, see `docs/MAP_SCHEMA.md`) |
| `packages/drivers/.../ios.py` `app_container`, `user_apps` | simctl only (no idb): the `.app` / data folder, the User apps |
| `apps/engine/.../cli/stack.py` `_cmd_stack_ios` | the canvas (`<project>-ios`), `build/app/<Name>.app`, the report |
| `packages/stack/tests/test_ios.py` | synthetic Mach-O (`macho()`, `fat()`) and `.app` folders (`app()`), one case per framework |

Plan and acceptance criteria: `docs/PLAN.md` §8.6, *iOS*. Simulator setup (booting, Device Hub,
idb): the `ios-simulator` skill. Rule upkeep and confidence levels: the `stack-rules` skill.

## Where the facts come from

| Fact | Source on the simulator | Already in the repo |
|---|---|---|
| The `.app` folder | `xcrun simctl get_app_container booted <bundle-id> app` | `IosDriver.is_installed` uses `get_app_container` |
| The data folder | `xcrun simctl get_app_container booted <bundle-id> data` | `IosDriver.clear_data` resolves it (`file:` URL or path) |
| Version, bundle id, deployment target, build SDK, Xcode | `Info.plist` (`CFBundleShortVersionString`, `MinimumOSVersion`, `DTSDKName`, `DTXcode`) | `appscreenmap.store.facts.ios_facts` / `parse_ios_plist` |
| Linked frameworks, min OS / SDK, encryption | the main executable's Mach-O load commands: `LC_LOAD_DYLIB`, `LC_BUILD_VERSION` (`minos`, `sdk`), `LC_ENCRYPTION_INFO_64` (`cryptid`) | none: parse with `struct` (stdlib), handle fat binaries |
| Embedded frameworks | `Frameworks/*.framework`, `*.dylib` | `security/ios.py` `_read_bundle` reads a bundle (dir or .ipa) |
| Code markers | strings in the main executable **and `<App>.debug.dylib`** | `security/secrets.scan_bytes` reads binaries |

**Debug builds split the code out.** Xcode puts a debug build's code in `<App>.debug.dylib` beside a small stub executable.
Scan both, or a debug KMP build reads as an empty Swift app.

**Encrypted binaries.** An App Store install is FairPlay-encrypted (`cryptid` 1): its code strings are noise. Framework
names, resources and Info.plist still work. Simulator builds are never encrypted. Say so in `notes`; never guess.

## Fingerprints (`IOS_RULES`; confidence as in `stack-rules`)

Rule kinds: `framework` (an embedded `Frameworks/<name>.framework`), `bundle-path` (a path prefix in the `.app`),
`bundle-file` (a file name anywhere in the `.app`), `symbol` (bytes in an unencrypted binary: main executable, debug dylib, embedded frameworks), `dylib` (a linked
library's install name contains it).

| Stack | Marker | Confidence |
|---|---|---|
| Flutter | `Frameworks/Flutter.framework` (+ `App.framework`) | certain |
| React Native | `main.jsbundle`; `React.framework` or React symbols; Hermes: `hermes.framework` / `hermesvm.framework` | certain (bundle + Hermes), strong |
| Expo | `ExpoModulesCore` framework or symbols | certain |
| Unity | `Frameworks/UnityFramework.framework` | certain |
| .NET MAUI / Xamarin | `*.dll` / `*.aotdata` in the bundle, `libmonosgen` | certain |
| Capacitor / Cordova | `Capacitor.framework`, `capacitor.config.json`, `public/`; `www/cordova.js` | certain |
| **Kotlin Multiplatform** | Kotlin/Native symbols (`kfun:` prefix) in the executable, debug dylib or a framework; a `*.framework` exporting them | **certain** on iOS (unlike Android: Kotlin/Native only exists for KMP) |
| Compose Multiplatform | `compose-resources/` folder in the `.app`; `skiko` (its renderer) in the binary; `org.jetbrains.compose` strings | strong |
| SwiftUI / UIKit | `LC_LOAD_DYLIB` of `SwiftUI.framework` / `UIKit.framework` | strong |
| Swift / Objective-C | `libswiftCore` linked or `__swift5_*` sections | strong |

Checked on a real KMP + Compose Multiplatform debug build (locally, outside the repo): no `Frameworks/`, a
`compose-resources/` folder, and in `<App>.debug.dylib` about 65 000 `kfun:` symbols, `skiko` and `org.jetbrains.compose`
strings, with SwiftUI linked; `LC_BUILD_VERSION` minos 18.0, sdk 27.0; no `LC_ENCRYPTION_INFO`.

## Storage map (data container)

| Storage | Where under the data container | At rest |
|---|---|---|
| UserDefaults | `Library/Preferences/<bundle-id>.plist` | plain |
| Core Data / SwiftData / SQLite | `Library/Application Support/*.sqlite`, `default.store` | plain unless the app encrypts |
| Realm | `Documents/*.realm` or `Library/…` | optional |
| MMKV | `Documents/mmkv/` (default) | optional |
| React Native AsyncStorage | `Library/Application Support/<bundle-id>/RCTAsyncLocalStorage_V1/` | plain |
| Flutter shared_preferences | UserDefaults keys prefixed `flutter.` | plain |
| Keychain | not in the container (the simulator's shared keychain) | encrypted |

Database names come from the binaries: C strings and Kotlin/Native's UTF-16 literals, minus reverse-domain names (those
are Kotlin packages like `com.example.db`). SQLDelight's native driver keeps them in `Library/Application Support/databases/`
(checked on a simulator, 2026-10-27), so a KMP app gets that exact path; otherwise `**/<name>` (any folder).

Also note the file protection class where it matters (`NSFileProtectionComplete`) once the data-at-rest scan reads files.
Detection comes from the bundle (frameworks, symbols); check a new `locations` path on the simulator by listing the data
container after the app has run.

## Build order (1–4 built; 5 next)

1. **Mach-O reader** (`packages/stack/.../macho.py`): load commands, fat slices, `LC_BUILD_VERSION`, `LC_ENCRYPTION_INFO_64`,
   dylib names. Tests on synthetic headers built with `struct` (like `elf()` in `test_stack.py`).
2. **Bundle fingerprint** (`ios.py`): the `.app` (or `.ipa` for later), executable + debug dylib + frameworks → the same
   `signals` / `storage` / `libraries` shape as Android, `platform: "ios"`. iOS rules live beside Android's with iOS kinds
   (`framework`, `bundle-path`, `symbol`, `dylib`).
3. **Engine:** `appscreenmap stack --platform ios --package <bundle-id>` (simctl instead of adb), canvases in the
   `<project>-ios` folder like iOS crawls, `build/app/` holding a copy of the `.app`. Device facts come from the driver
   when idb is installed, else from `simctl list` alone.
4. **Viewer:** `StackDetails` already renders any `facts`; add the iOS fields (deployment target, Xcode, encryption) and
   iOS words (Swift / SwiftUI). New project lists booted simulators beside emulators.
5. **Frida spike:** simulator apps are macOS processes, so `frida -n <process>` may attach without a jailbreak. Try it on the
   Playground iOS build; record the result in §8.6 before building on it.

## Verify

```bash
uv run pytest -q packages/stack apps/engine/tests/test_stack_cli.py apps/engine/tests/test_serve_stack.py
xcrun simctl list devices booted
xcrun simctl install booted <App>.app                      # a simulator build (an .ipa will not install)
uv run appscreenmap-engine stack --platform ios --package <bundle-id> --out <scratch>/runs
open "$(xcrun simctl get_app_container booted <bundle-id> data)"   # compare storage rows with what is really there
```

Grade against the plan's iOS acceptance criteria. Real apps are scanned locally and never named in the repo; the in-repo
known answer is the SwiftUI Playground once it exists (until then, synthetic bundles in tests).
