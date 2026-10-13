---
name: security-audit
description: Run a security audit of an Android or iOS build with AppScreenMap — `appscreenmap security <run>` scans an APK (manifest, hard-coded secrets), the app's data folder and a Frida observation log and writes audits/security.json; judge the findings against the security rules, do the checks it doesn't cover by hand, and report. Use when asked to security-check, scan or review an app build, to fill the Security audit, or to check a release before shipping. Only for apps you own or are authorised to test.
---

# Security audit

> **Authorised use only.** Run this on builds you own or have written permission to test. It reads the app's own manifest,
> code and data folder, and instruments it on your device or simulator. It doesn't attack servers and nothing here is for
> evading detection or exploiting anyone else's app. Don't paste secrets you find into chat, tickets or the report:
> record *where*, not the value.

**Status:** `appscreenmap security <run>` is built for **Android**: manifest rules, hard-coded secrets in the APK, secrets left in the
app's data folder, and an observation-only Frida log. It writes `audits/security.json` itself, so the Insights Security page shows
real findings. What it does *not* check yet (code-level rules such as `weak-crypto`, and everything on iOS) is still done by hand
below, and a rule stays `planned` in the catalogue until the command covers it. Rules, severities and fixes live in `security-rules`.

## 1. Preflight

```bash
uv run appscreenmap doctor            # aapt2 reads the manifest; adb for the device checks
uv tool install frida-tools           # only for the dynamic check
```

Pick the **release** build you ship. A debug build will (rightly) trip `debuggable` and `cleartext-traffic`.

## 2. Run the scanner (Android)

```bash
RUN=runs/<project>/<run-id>                                   # a crawl of the app (crawl-app)
uv run appscreenmap security $RUN --apk app-release.apk       # manifest + hard-coded secrets, about 0.1 s
uv run appscreenmap security $RUN --pull --device             # or: pull the installed APK, and read the app's data folder
uv run appscreenmap security $RUN --frida-log frida.log       # add the dynamic observations (below)
```

Each call adds its evidence to the run (`audits/security-evidence.json`) and rebuilds `audits/security.json` from everything
collected so far, so you can run the three steps in any order. Add `--json` to read the audit instead of the summary.

| Flag | Evidence | Rules |
|---|---|---|
| `--apk FILE` / `--pull` | Manifest (`aapt2`), network security config, secret formats in dex, resources and assets | `exported-component`, `cleartext-traffic`, `debuggable`, `allow-backup`, `hardcoded-secret` |
| `--device` | Plain-text secrets in `shared_prefs/` and `files/`; needs a debuggable build (`run-as`) or a rooted emulator (`su`), else it says it didn't run | `secrets-at-rest` |
| `--frida-log FILE` | JSON lines from `scripts/frida-observe.js` | `cleartext-observed`, `no-cert-pinning` |

The secret scan only matches high-confidence formats (AWS, Stripe live, Slack, GitHub, private keys, database URLs with
credentials, Google API keys) and records where and a short fingerprint, never the value. A Google API key is reported as info:
client keys ship in apps on purpose, so the fix is to restrict it.

**Dynamic (Frida).** On your own debug build, with a frida server on the emulator:

```bash
frida -U -f <package> -l .claude/skills/security-audit/scripts/frida-observe.js > frida.log   # then use or crawl the app
```

The script only observes: it logs plain `http://` hosts and whether OkHttp has any certificate pin configured. It doesn't bypass
pinning or change traffic. It was written without a device to test on, so check that its hooks attach (a `hook-failed` line, or
a "Frida hook … did not attach" note in the audit) before trusting an empty result.

### By hand: what the scanner doesn't cover yet

| Evidence | Android | iOS (simulator `.app`) | Rules |
|---|---|---|---|
| Plist | | `plutil -p App.app/Info.plist`; look for `PrivacyInfo.xcprivacy` | `ats-exceptions`, `privacy-manifest-missing` |
| Data left behind | | `xcrun simctl get_app_container <udid> <bundle> data`, then `plutil -p` the preferences | `secrets-at-rest` |
| Code | `jadx -d out app.apk`, then grep `out/sources` | `strings` on the binary, grep the bundle | `webview-js-interface`, `insecure-trust-manager`, `weak-crypto`, `sensitive-logging` |

Detection hints for every rule are in `security-rules/reference/rules.md`. Say which categories you did **not** run: an audit that
skipped a category must not read as a pass (the command never returns `pass` while rules remain unchecked).

## 3. Judge

Apply `security-rules` ("Reading a finding"). For each candidate: open the code or file, confirm it's real, then keep it,
downgrade it (say why) or drop it. Match it to a rule id; one rule can produce several findings.

## 4. Write the result by hand (only for what the scanner doesn't cover)

The command writes this for you. For hand-run checks, add findings to `runs/<project>/<run-id>/audits/security.json` (shape in `docs/MAP_SCHEMA.md`, "audits"). The viewer picks it up and
replaces the placeholder. Use the rule's own text:

```jsonc
{ "schema": 1, "audit": "security", "title": "Security", "tool": "jadx 1.5.1 + aapt2 (by hand)",
  "generated_at": "2026-10-14T12:00:00+00:00", "source": "run", "status": "fail", "score": 70,
  "score_note": "100 minus 20 per error, 8 per warning, 2 per info",
  "summary": "1 error, 2 warnings · manifest and static scan run; dynamic not run",
  "metrics": [ { "label": "checks run", "value": "manifest, static" }, { "label": "not run", "value": "dynamic", "tone": "warn" } ],
  "charts": [],
  "findings": [ {
      "id": "debuggable", "severity": "error", "category": "Manifest", "platform": "android",
      "title": "Debuggable build", "detail": "android:debuggable=\"true\" in AndroidManifest.xml.",
      "fix": "<the rule's fix>", "refs": [ { "title": "android:debuggable", "url": "https://developer.android.com/…", "publisher": "Android Developers" } ] } ],
  "refs": [] }
```

- `id` is the rule id (add a suffix for several findings of one rule: `exported-component:com.x.Settings`).
- Score is yours to define; state it in `score_note`. Don't invent a score you can't explain.
- Put what you skipped in `summary` and `metrics`, never leave it out.

## 5. Report back

Lead with the errors and what each exposes (not how to exploit it). Then warnings, then what was **not** checked. Link the
Insights page (`#/r/<run>/insights/security`). Offer fixes as code, and re-run the same checks after the fix to confirm.
Never include a secret's value.

## Extending the scanner

`src/appscreenmap/security.py` (stdlib only; tests in `tests/test_security.py` use real `aapt2` output saved in `tests/fixtures/`).
Add a check by returning `{"rule": <id>, "key": ..., "detail": ...}` from a collector, add a fixture test, and flip the rule's
`status` to `ready` in `security_rules.json`. Next in line: the `jadx`-backed code rules, and iOS (plist and data container).
Use `extend-crawler` for CLI wiring.
