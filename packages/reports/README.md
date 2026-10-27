# appscreenmap-reports

Reads a finished run and reports on it. Depends on `core`, `drivers`.

| Module | What |
|---|---|
| `appscreenmap.reports.health` | `build_report`, `format_report`: wasted steps, screen identity issues, navigation failures, device caveats |
| `appscreenmap.reports.perf` | `summarize`, `format_perf`: load time per screen, slow transitions, jank, cold start |
| `appscreenmap.reports.builtin` | `write_builtin`: coverage, stability, a11y, perf as `audits/<id>.json` (a port of the viewer's `insights/builtin.ts`) |
| `appscreenmap.reports.document` | `build_document`, `write_report`: one model for the app report from every audit; profiles |
| `fonts/` | Geist and Geist Mono (latin woff2, `OFL.txt`), inlined into `report.html` so it looks the same offline |
| `appscreenmap.reports.markdown` / `htmldoc` / `fixes` | Renderers: `report.md` + assets, self-contained `report.html` (tokens inlined), `fixes.md` + `fixes.json` |
