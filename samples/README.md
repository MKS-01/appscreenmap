# Samples: end-to-end playground

Two apps for trying, demoing and testing AppScreenMap end to end. The APKs are committed, so
nothing needs building. The sample runs they produce are committed under `runs/`, so the viewer has
something to show straight after a clone.

| App | Why it's here | Folder | Runs |
|---|---|---|---|
| **Playground** | Built for AppScreenMap: every screen triggers a known feature, and two builds (v1, v2) give known diffs | [`playground-app/`](playground-app/) | `runs/playground/` |
| **DuskRead** | A real Compose app: real-world layouts, no resource ids, a live timer | [`duskread/`](duskread/) | `runs/duskread/` |

## Run every scenario

```bash
samples/demo.sh             # all scenarios, about 25 minutes on an emulator
samples/demo.sh playground  # only the Playground scenarios
samples/demo.sh duskread    # only DuskRead
```

Needs a running emulator (`adb devices`). The script installs the APKs, wipes their data first, and
leaves the device's animation, font and pinning settings as it found them.

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

Planned (roadmap §8.2): network profiles, Perfetto traces for slow screens, condition matrix.
