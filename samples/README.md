# Samples: end-to-end playground

**Playground** is the sample app for trying, demoing and testing AppScreenMap end to end. It was built for
AppScreenMap: every screen triggers a known feature, and two builds (v1, v2) give known diffs, so a crawl has known
answers. The APKs are committed, so it needs no build. Crawl results aren't committed: `demo.sh` writes them to
`runs/playground/` (git-ignored) and `appscreenmap serve` shows them.

| App | Folder | Where its runs go |
|---|---|---|
| **Playground** (Android, Jetpack Compose) | [`playground-app/`](playground-app/) | `runs/playground/` |
| **Playground iOS** (SwiftUI, same scenarios) | first slice: `samples/playground-ios/` | `runs/playground-ios/` |

For a real app, crawl your own build (`appscreenmap crawl --apk …`); nothing about it needs to live in this repo.

## Run every scenario

```bash
samples/demo.sh             # every scenario (needs an emulator)
samples/demo.sh playground  # the same: Playground is the only sample for now
```

Android needs a running emulator (`adb devices`). The script installs the APKs, wipes their data first, and
leaves the device's animation, font and pinning settings as it found them.

## Scenario matrix

| # | Scenario | Command (what `demo.sh` runs) | Look at |
|---|---|---|---|
| 1 | Map an app from a clean install (first-run state) | `crawl --apk … --clear-data` | viewer Map; `map.json` |
| 2 | Forms filled from config (sign in, onboarding name) | (part of 1) | screen `autofill`; Maestro flows replay it |
| 3 | List pattern and screen variants (feed → one article template) | (part of 1) | elements `skipped: list pattern`, `variant_of` |
| 4 | Navigation inference (bottom nav, theme switch) | (part of 1) | dashed/`inferred` edges |
| 5 | Stay inside the app (browser link, BACK at the root) | (part of 1) | no `x:` screens; Privacy policy `blocked` |
| 6 | Dangerous actions never tapped (Log out, Delete account) | (part of 1) | elements `blocked` |
| 7 | Crash capture | (part of 1) | `events` type `crash`, `crashes/crash-1.txt` |
| 8 | Second activity, orientation lock | (part of 1) | Scanner screen; a11y 1.3.4 |
| 9 | Screen load times, slow screen with spinner, jank | `perf <run>` | Reports *slow*, Gallery janky |
| 10 | WCAG 2.2 audit and report | `a11y <run> --report` | `a11y-report.html` |
| 11 | Resize text at 200% | `crawl … --font-scale 2.0` | 1.4.4 findings, screenshots |
| 12 | Release comparison: visual diff v1 → v2 | `diff runs/playground/<v1> runs/playground/<v2>` | changed / new (*What's new*) / missing (*Rate us*) |
| 13 | Release comparison: perf and a11y v1 → v2 | `perf` + `a11y` on both runs | Reports slow → ok; fixed WCAG findings |
| 14 | Maestro flows to every screen | (part of 1) | `flows/*.yaml` |
| 15 | Crawl health | `report <run>` | steps per screen, findings |
| 16 | Secrets from the environment | `APP_PASSWORD=… crawl …` (config: `"pass" = "${APP_PASSWORD}"`) | run files hold only `${APP_PASSWORD}` |
| 17 | Release check: replay every v1 path on v2 | `verify runs/playground/<v1> --apk …/playground-v2.apk` | paths into *Rate us* break (removed in v2); exit code 1 |
| 18 | Agents use the map (MCP) | `appscreenmap mcp` | `where_am_i`, `route`, `go_to_screen` against the sample runs |
| 19 | First-run screens after sign-in | (part of 1, `--clear-data`) | `data_reset` event; *Reset password* mapped although sign-in persists |
| 20 | Same app on iOS: map, flows and a11y from the accessibility tree | planned: `crawl --platform ios --app …/Playground.app --clear-data` | waits for Playground iOS |

Planned (roadmap §8.2): network profiles, Perfetto traces for slow screens, condition matrix.

## Where the results go

Nothing from a crawl is committed. `samples/demo.sh` writes each run to `runs/<project>/<run-id>/` (git-ignored), and
`appscreenmap serve` shows them. For Compare and `verify` (scenarios 12, 13 and 17) you need both Playground builds,
so run `samples/demo.sh playground`, which crawls v1 and v2. The APKs here are Playground 1.0 / 2.0.

## Licences and provenance

Playground (source and APKs) is MIT like the rest of the repo; its APKs are signed with the Android debug key and
bundle Apache-2.0 libraries (AndroidX, Compose, Kotlin). Details: [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md).
All form values the sample crawls type are dummy data, and passwords are `${APP_PASSWORD}` placeholders.
