---
name: security-rules
description: The security audit's rule catalogue for Android and iOS apps — each rule's id, severity, evidence (manifest, static scan, dynamic run, data left on the device), how to detect it, the fix, and its official Android / Apple / Google Play source. Use when interpreting a security finding, writing fix guidance, deciding if something is a real problem, adding or changing a rule, or when the Insights Security audit shows "not set up" and you need to know what it will check.
---

# Security rules

One catalogue, three readers:

| File | Reader |
|---|---|
| `src/appscreenmap/security_rules.json` | the source of truth: id, title, platform, category, severity, tools needed, why, fix, official refs, status |
| `src/appscreenmap/security_rules.py` | loads and **validates** it (severity, platform, category, https + official host only, unique ids) |
| `web/src/insights/registry.ts` | the viewer shows every `planned` rule as a placeholder on the Security audit ("not set up") |
| [`reference/rules.md`](reference/rules.md) | the human version with how to detect each rule by hand; a test fails if a rule is missing from it |

## What a rule is

```json
{ "id": "debuggable", "title": "Debuggable build", "platform": "android", "category": "manifest",
  "severity": "error", "needs": ["aapt2"], "status": "planned",
  "why": "…one or two sentences on what an attacker gets…", "fix": "…the change to make…",
  "refs": [{ "title": "android:debuggable", "url": "https://developer.android.com/…", "publisher": "Android Developers" }] }
```

- **platform**: `android`, `ios` or `both`. **category**: `manifest`, `static`, `dynamic`, `data` (the four kinds of evidence).
- **status**: `planned` until a scanner implements it, then `ready`. The viewer treats `planned` as "not set up".
- **severity**: `error` fix before release; `warning` fix or justify in writing; `info` a decision to make on purpose.
- **refs**: official pages only (developer.android.com, developer.apple.com, support.google.com, source.android.com,
  w3.org). No blogs, no OWASP copies. Android has a page per vulnerability class under
  `developer.android.com/privacy-and-security/risks/`; use the one that matches the rule. Open the page and read it: a link
  that merely sounds related is worse than none. Apple's documentation pages render client-side, so check them in a browser.

## Reading a finding

1. Say which evidence it came from. A manifest flag is a fact about the build; a static match is a *candidate* (read the
   code before calling it a bug); a dynamic observation is one session.
2. Severity is about the app as shipped, not the crawl. `debuggable` on a debug build isn't a finding; on the release build it is.
3. A secret is real only if it grants something. Rotate first, then decide if it was ever exposed.
4. Never write exploit steps in a finding: say what is exposed and how to fix it.

## Adding or changing a rule

1. Edit `security_rules.json`. Read the official page you cite; copy its exact title.
2. Add the row to `reference/rules.md` (id in backticks; the test checks this) with how to detect it by hand.
3. `uv run pytest tests/test_security_rules.py` (validates fields, hosts, ids, and the docs sync), then
   `cd web && bun run build`.
4. When a scanner implements a rule, set `"status": "ready"` and add a fixture test beside the scanner.

Run the audit with the `security-audit` skill. Platform deadlines and yearly Android/iOS changes are the *Platform changes*
audit (`web/src/insights/sources.ts`), not this one.
