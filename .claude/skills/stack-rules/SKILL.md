---
name: stack-rules
description: Keep the app stack scan's rules current — the framework, language and UI fingerprints (packages/stack/.../detect.py), the storage map (storage.py), the LibChecker-Rules library-name snapshot (libchecker.json) and, once built, their iOS counterparts. Use when `appscreenmap stack` names the wrong framework or misses one, a new framework or major release changes its runtime files (React Native, Flutter, Expo, Compose Multiplatform, .NET MAUI, Unity…), a storage library is missing from "Where it keeps data", the snapshot is more than ~3 months old, or someone asks to add, tune or review a stack rule.
---

# Stack rules upkeep

`appscreenmap stack` (package `packages/stack`, plan `docs/PLAN.md` §8.6) reads an installed build and matches it against
rules. The rules are data in code: each is a name, a category and a list of `(kind, pattern, confidence)` checks.
The data contract is `audits/stack.json` in `docs/MAP_SCHEMA.md`.

| File | Holds |
|---|---|
| `packages/stack/src/appscreenmap/stack/detect.py` | `RULES`: frameworks, runtimes, language, UI toolkit, KMP. `CROSS_PLATFORM` and `summarize()` turn signals into the one-line summary |
| `packages/stack/src/appscreenmap/stack/storage.py` | `STORAGE`: where each storage library writes under `/data/data/<pkg>/` and whether it encrypts (`True`, `False`, `None` = optional) |
| `packages/stack/src/appscreenmap/stack/libchecker.json` | Snapshot of [LibChecker-Rules](https://github.com/LibChecker/LibChecker-Rules) (Apache-2.0): native library and component names → library labels. Never edit by hand |
| `packages/stack/tests/test_stack.py` | One parametrised case per framework, plus calibration tests |
| `detect.py` `IOS_RULES`, `storage.py` `IOS_STORAGE`, `tests/test_ios.py` | The iOS rules and their cases (`CASES`); how they are read is in `stack-ios` |

Check kinds: `lib` (a native library file name), `lib-prefix`, `path` (an APK entry path prefix), `dex` (a class
descriptor prefix in the dex string table, e.g. `Lcom/getcapacitor/`). iOS: `framework`, `bundle-path`, `bundle-file`,
`symbol`, `dylib` (see `stack-ios`); an iOS storage location may use `{bundle}` for the bundle id.

## Confidence: what each level promises

| Level | Use only when | Example |
|---|---|---|
| `certain` | Only that stack ships the file: its runtime | `libflutter.so`, `libhermesvm.so`, `libunity.so` |
| `strong` | The stack's build always leaves it, but another stack could carry it | `META-INF/androidx.compose.*.version`, `Lorg/jetbrains/compose/resources/`, every storage rule |
| `likely` | A hint that is often, not always, true | KMP-oriented libraries on Android (Ktor client, SQLDelight) |

Two rules never change: **KMP on Android is never more than `likely`** (it compiles to plain Kotlin; on iOS `kfun:`
symbols make it `certain`), and a storage hit is
`strong` at most (bundled is not used; the Frida probe confirms). A bundled library is not proof the app uses it.

## Add or fix a rule

1. **Get evidence from a real build, locally.** Real apps are tested outside the repo and never named in it (code, tests,
   docs, commit messages). Pull and list one:
   ```bash
   uv run appscreenmap-engine stack --package <pkg> --out <scratch>/runs     # keeps the APKs in <canvas>/build/apks/
   unzip -l <scratch>/runs/<proj>/<run>/build/apks/base.apk | grep -E "lib/|assets/|META-INF/.*version"
   python3 -I -c "import sys,re;b=open(sys.argv[1],'rb').read();print(sorted(set(re.findall(rb'L[a-z][\w/]{3,60}/', b)))[:200])" classes.dex
   ```
   Prefer a runtime file (`lib`, `path`) over a class name: R8 renames library classes in release builds (it hid SQLDelight
   entirely in one app; the framework `SQLiteOpenHelper` and the `*.db` names survived).
2. **Write the test first** in `test_stack.py`: a synthetic APK (`apk()`, `dex()`, `elf()` helpers) with the new markers and
   the expected summary or storage row. Add a negative case when the change is a calibration (the marker must *not* fire).
3. **Edit the rule.** Keep the confidence honest (table above). A new category or a new `facts` field is a schema change:
   update `docs/MAP_SCHEMA.md` (additive only), `packages/stack/README.md`, and the viewer's `insights/stack.ts` type.
   Viewer label text lives in `insights/StackDetails.tsx` (`KIND_WORD`).
4. **Storage rules** also need `locations` (paths under the data folder, exact file names when the library fixes them, e.g.
   `shared_prefs/FlutterSecureStorage.xml`) and `encrypted`. The data-at-rest scan reads these paths, so a wrong path means
   a missed check. Cite the library's own docs or source for the file name in the commit message.
5. **Verify:** `uv run pytest -q packages/stack`, then scan the Playground on the emulator
   (`uv run appscreenmap-engine stack --package dev.appscreenmap.playground --out <scratch>/runs`: still "Native Android:
   Kotlin, Jetpack Compose", min 26 / target 36 / compile 36) and the real app that prompted the change, locally.
6. Record a calibration in the table below when a rule was wrong.

## Refresh the LibChecker snapshot

```bash
make stack-rules-sync        # python3 -I scripts/sync-libchecker-rules.py: fetches the pinned commit, rewrites libchecker.json
git diff --stat packages/stack/src/appscreenmap/stack/libchecker.json
uv run pytest -q packages/stack
```

Every ~3 months, or when a known library shows as unnamed. The snapshot records `commit` and `synced`; the commit message
says the old and new commit. Only exact-name rules come across (LibChecker's regex rules live in its app, not the repo).

## When

| Trigger | Check |
|---|---|
| React Native release | native library names (`libreactnative.so` replaced `libreactnativejni.so` in 0.76; Hermes ships as `libhermes.so` or `libhermesvm.so`) and the bundle path |
| Flutter, Compose Multiplatform, Expo, MAUI, Unity major release | their runtime files and asset folders |
| A wrong or missing signal on a real app | steps above, then a calibration row |
| `libchecker.json` `synced` older than ~3 months | refresh |

## Calibrations

| Date | Rule | What was wrong | Change |
|---|---|---|---|
| 2026-10-27 | `kmp-libraries` | `kotlinx.datetime` fired on a React Native app (an Android SDK bundles it) | removed from the KMP hints |
| 2026-10-27 | `sqlite` (storage) | R8 hid SQLDelight in a release build, so no storage was found | framework `SQLiteOpenHelper` rule, plus the `*.db` names the code opens |
