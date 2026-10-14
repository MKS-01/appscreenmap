# appscreenmap-reports

Reads a finished run and reports on it. Depends on `core`, `drivers`.

| Module | What |
|---|---|
| `appscreenmap.reports.health` | `build_report`, `format_report`: wasted steps, screen identity issues, navigation failures, device caveats |
| `appscreenmap.reports.perf` | `summarize`, `format_perf`: load time per screen, slow transitions, jank, cold start |
