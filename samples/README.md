# Samples: end-to-end playground

Two apps for trying, demoing and testing AppScreenMap end to end, on Android and the iOS Simulator. The
APKs are committed, so Android needs no build; the iOS app is built from DuskRead's source by
`duskread/build-ios.sh`. Crawl results aren't committed: `demo.sh` writes them to `runs/` (git-ignored) and
`appscreenmap serve` shows them.

| App | Why it's here | Folder | Where its runs go |
|---|---|---|---|
| **Playground** | Built for AppScreenMap: every screen triggers a known feature, and two builds (v1, v2) give known diffs | [`playground-app/`](playground-app/) | `runs/playground/` |
| **DuskRead** | A real Compose app: real-world layouts, no resource ids, a live timer | [`duskread/`](duskread/) | `runs/duskread/` |
| **DuskRead iOS** | The same app's SwiftUI target on the iOS Simulator: same explorer, map format and viewer | [`duskread/`](duskread/) (`build-ios.sh`) | `runs/duskread-ios/` |

## Run every scenario

```bash
samples/demo.sh             # all scenarios, about 25 minutes on an emulator
samples/demo.sh playground  # only the Playground scenarios
samples/demo.sh duskread    # only DuskRead (Android)
samples/demo.sh ios         # only DuskRead on the iOS Simulator (builds the .app on first use)
```

Android needs a running emulator (`adb devices`). The script installs the APKs, wipes their data first, and
leaves the device's animation, font and pinning settings as it found them.

iOS needs macOS with Xcode, a booted simulator (`xcrun simctl boot "iPhone 17"`) and idb
(`brew install facebook/fb/idb-companion` and `uv tool install fb-idb`); `appscreenmap doctor` checks all three.
`all` includes the iOS scenario only when a simulator is booted.

## Scenario matrix

| # | Scenario | App | Command (what `demo.sh` runs) | Look at |
|---|---|---|---|---|
| 1 | Map an app from a clean install (first-run state) | both | `crawl --apk … --clear-data` | viewer Map; `map.json` |
| 2 | Forms filled from config (sign in, onboarding name) | both | (part of 1) | screen `autofill`; Maestro flows replay it |
| 3 | List pattern and screen variants (feed → one article template) | Playground | (part of 1) | elements `skipped: list pattern`, `variant_of` |
| 4 | Navigation inference (bottom nav, theme switch) | both | (part of 1) | dashed/`inferred` edges |
| 5 | Stay inside the app (browser link, BACK at the root) | Playground | (part of 1) | no `x:` screens; Privacy policy `blocked` |
| 6 | Dangerous actions never tapped (Log out, Delete account) | Playground | (part of 1) | elements `blocked` |
| 7 | Crash capture | Playground | (part of 1) | `events` type `crash`, `crashes/crash-1.txt` |
| 8 | Second activity, orientation lock | Playground | (part of 1) | Scanner screen; a11y 1.3.4 |
| 9 | Screen load times, slow screen with spinner, jank | both | `perf <run>` | Reports *slow*, Gallery janky, DuskRead Focus redraw |
| 10 | WCAG 2.2 audit and report | both | `a11y <run> --report` | `a11y-report.html` |
| 11 | Resize text at 200% | Playground | `crawl … --font-scale 2.0` | 1.4.4 findings, screenshots |
| 12 | Release comparison: visual diff v1 → v2 | Playground | `diff runs/playground/<v1> runs/playground/<v2>` | changed / new (*What's new*) / missing (*Rate us*) |
| 13 | Release comparison: perf and a11y v1 → v2 | Playground | `perf` + `a11y` on both runs | Reports slow → ok; fixed WCAG findings |
| 14 | Maestro flows to every screen | both | (part of 1) | `flows/*.yaml` |
| 15 | Crawl health | both | `report <run>` | steps per screen, findings |
| 16 | Secrets from the environment | Playground | `APP_PASSWORD=… crawl …` (config: `"pass" = "${APP_PASSWORD}"`) | run files hold only `${APP_PASSWORD}` |
| 17 | Release check: replay every v1 path on v2 | Playground | `verify runs/playground/<v1> --apk …/playground-v2.apk` | paths into *Rate us* break (removed in v2); exit code 1 |
| 18 | Agents use the map (MCP) | both | `appscreenmap mcp` | `where_am_i`, `route`, `go_to_screen` against the sample runs |
| 19 | First-run screens after sign-in | Playground | (part of 1, `--clear-data`) | `data_reset` event; *Reset password* mapped although sign-in persists |
| 20 | Same app on iOS: map, flows and a11y from the accessibility tree | DuskRead iOS | `crawl --platform ios --app …/DuskRead.app --clear-data` | `runs/duskread-ios/`; a Safari link recorded as external and the app restarted; controls VoiceOver can't see are missing (the finding) |

Planned (roadmap §8.2): network profiles, Perfetto traces for slow screens, condition matrix.

## Where the results go

Nothing from a crawl is committed. `samples/demo.sh` writes each run to `runs/<project>/<run-id>/` (git-ignored), and
`appscreenmap serve` shows them. For Compare and `verify` (scenarios 12, 13 and 17) you need both Playground builds,
so run `samples/demo.sh playground`, which crawls v1 and v2. The APKs here are DuskRead 1.3.0 and Playground 1.0 / 2.0.

## Licences and provenance

Playground (source and APKs) is MIT like the rest of the repo; its APKs are signed with the Android debug key.
DuskRead is a separate MIT project by the same author; its APK is signed with the author's release key. Both APKs
bundle Apache-2.0 libraries (AndroidX, Compose, Kotlin). Details: [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md).
All form values the sample crawls type are dummy data, and passwords are `${APP_PASSWORD}` placeholders.
