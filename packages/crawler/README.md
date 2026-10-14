# appscreenmap-crawler

Explores the app and records the map. Depends on `core`, `drivers`.

| Module | What |
|---|---|
| `appscreenmap.crawler.explorer` | `Explorer`: the crawl loop. Taps, types and scrolls through the app, identifies screens, records transitions and paths; stays inside the target app (lock task pinning, never BACK into other apps) |
| `appscreenmap.crawler.replay` | `Replayer`: navigates back to a recorded screen by its path and identifies where it landed (used by `verify` and MCP) |
| `appscreenmap.crawler.timing` | `LoadMeter`, `Timing`: how long a screen takes to settle after an action, from the app's frame counter |

Exploration fixes start with a synthetic regression test here (`tests/`), using `appscreenmap.testkit`.
