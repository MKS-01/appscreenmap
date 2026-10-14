# appscreenmap-a11y

WCAG 2.2 checks on a recorded run; no device needed. Depends on `core`, `drivers`.

| Module | What |
|---|---|
| `appscreenmap.a11y.checks` | `audit_run`: per-screen, cross-screen, flow and app checks → `a11y.json`; `RULES`, `format_audit` |
| `appscreenmap.a11y.wcag` | the WCAG 2.2 criteria catalogue (levels, what is automated, device tests, viewer rules) |
| `appscreenmap.a11y.report` | `write_reports`: the conformance-style report (`a11y-report.html` / `.md`) with evidence crops |

Rules and thresholds: the `wcag-mobile-rules` and `ios-a11y-rules` skills; adding a check: `add-a11y-rule`.
