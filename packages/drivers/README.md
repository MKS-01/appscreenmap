# appscreenmap-drivers

Talks to devices. Standard library only; imports nothing else from the repo.

| Module | What |
|---|---|
| `appscreenmap.drivers.base` | `DriverError`, `Snapshot` (one raw observation: hierarchy XML + foreground activity) |
| `appscreenmap.drivers.android` | `AdbDriver`: uiautomator dumps, input, screenshots, lock-task pinning, data reset, perf counters |
| `appscreenmap.drivers.dumpsys` | parsers for `dumpsys gfxinfo` (summary, framestats) and `am start -W` |
| `appscreenmap.drivers.device` | device facts from `getprop` and a shell probe: model, form factor, font scale, TalkBack, … |
| `appscreenmap.drivers.apkinfo` | `aapt2` lookup and APK facts: package, launch activity, declared activities, orientation locks |
| `appscreenmap.drivers.ios` | `IosSimulatorDriver` over `xcrun simctl` + `idb` |
| `appscreenmap.drivers.ios_hierarchy` | idb accessibility tree → the same hierarchy XML the analyzer reads |

A new driver implements the same methods as `AdbDriver` that the explorer calls and returns `Snapshot`s.
