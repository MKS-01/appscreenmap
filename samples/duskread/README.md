# DuskRead sample

[DuskRead](https://github.com/MKS-01/duskread) is a real reading app (MIT, by the AppScreenMap author):
save links, follow blogs, hear articles read aloud, a focus timer. It's built with Kotlin
Multiplatform and Compose, which makes it a good real-world test. Compose exposes almost no resource
ids, so screen identity and element keys have to come from structure and text.

| File | What it is |
|---|---|
| `duskread-1.3.0.apk` | The release build (4.2 MB, signed by the author) |
| `appscreenmap.toml` | Crawl config: budgets, the onboarding name, a dummy Notion token |
| `build.sh` | Rebuilds the APK from source (uses `../../../duskread` or clones the repo) |
| `build-ios.sh` | Builds the iOS app for the simulator into `build/ios/DuskRead.app` (git-ignored; needs Xcode) |

## What a crawl finds

From a clean install (`--clear-data`), the crawl:
- starts at onboarding ("What should I call you?"), types the name from the config, and taps *Get started*
- maps Home (focus timer, latest posts), Following, Saved, Settings, the Focus timer states and Connect Notion
- infers the bottom navigation and the theme switch in the bar instead of tapping them on every screen
- reports Compose controls without a role (WCAG 4.1.2), the Focus timer's continuous redraw (`perf`),
  and onboarding as unreachable once completed (expected: it only exists on first run)

## Run it

```bash
uv run appscreenmap crawl --apk samples/duskread/duskread-1.3.0.apk \
  --config samples/duskread/appscreenmap.toml --clear-data --project duskread
```

The committed sample run lives in `runs/duskread/`.

## iOS Simulator

DuskRead also has a SwiftUI iOS target over the same Kotlin Multiplatform core, so it's the iOS sample too.
A simulator runs a `.app` from an `iphonesimulator` build (an `.ipa` is device-signed and won't run there):

```bash
samples/duskread/build-ios.sh                      # → samples/duskread/build/ios/DuskRead.app (first build: minutes)
uv run appscreenmap crawl --platform ios --app samples/duskread/build/ios/DuskRead.app \
  --config samples/duskread/appscreenmap.toml --clear-data
```

Needs a booted simulator and idb (`appscreenmap doctor` checks). The crawler reads the accessibility tree, so it sees
what VoiceOver sees: a control with no label is invisible to it, and that is itself a finding (the committed run stops
after 7 screens because the floating tab bar isn't in the tree). The committed run lives in `runs/duskread-ios/`;
the [`ios-simulator` skill](../../.claude/skills/ios-simulator/SKILL.md) covers setup and debugging.
