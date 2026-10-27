# appscreenmap-stack

What an app installed on the emulator is built with: native or cross-platform (Flutter, React Native, Expo, Unity,
Unreal, .NET MAUI / Xamarin, Capacitor, Cordova, NativeScript, Qt, Compose Multiplatform), language and UI toolkit,
SDK levels, ABIs, 16 KB page alignment, AndroidX library versions and known third-party libraries. Standard library
only; depends on `appscreenmap-drivers` (for `aapt2`) and `appscreenmap-store` (manifest SDK parsing).

| Module | What |
|---|---|
| `appscreenmap.stack.dumpsys` | `dumpsys package <pkg>`: version, min / target SDK, flags (debuggable), installer, signing scheme, splits |
| `appscreenmap.stack.apk` | the APKs pulled from the device (base + splits): native libraries, dex marker classes, `META-INF/*.version`, manifest components |
| `appscreenmap.stack.detect` | the framework rules, each with a confidence (`certain`, `strong`, `likely`) |
| `appscreenmap.stack.elf` | 16 KB page support: ELF LOAD alignment and zip offset of 64-bit native libraries |
| `appscreenmap.stack.audit` | all of it → `audits/stack.json` (the Insights audit shape plus a `facts` block) |
| `libchecker.json` | a snapshot of [LibChecker-Rules](https://github.com/LibChecker/LibChecker-Rules) (Apache-2.0, `LIBCHECKER-LICENSE`): native library and component names → library names. `make stack-rules-sync` refreshes it |

`appscreenmap stack [canvas] --package PKG [--serial S]`. Without a canvas it finds the app's one, or creates an empty
one that a later crawl merges into.
