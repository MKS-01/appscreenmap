---
name: security-audit
description: Run a security audit of an Android or iOS build with AppScreenMap — gather evidence (manifest or Info.plist, jadx static scan, data left on the device, optional frida run), judge it against the security rules, write audits/security.json so the Insights Security page shows real findings instead of "not set up", and report. Use when asked to security-check, scan or review an app build, to fill the Security audit, or to check a release before shipping. Only for apps you own or are authorised to test.
---

# Security audit

> **Authorised use only.** Run this on builds you own or have written permission to test. It reads the app's own manifest,
> code and data folder, and instruments it on your device or simulator. It doesn't attack servers and nothing here is for
> evading detection or exploiting anyone else's app. Don't paste secrets you find into chat, tickets or the report:
> record *where*, not the value.

**Status:** the scanner (`appscreenmap security <run>`) isn't built yet, so every rule in `security-rules` is `planned`, and the
Insights Security page says "not set up" and lists them. Until it ships you can run the checks by hand and write the result
file; the viewer renders it with no code change. The catalogue and how to read a finding are in `security-rules`.

## 1. Preflight

```bash
uv run appscreenmap doctor            # aapt2 for the Android manifest; a booted simulator for iOS
brew install jadx                     # static scan (Android; also fine on .aar)
uv tool install frida-tools           # dynamic checks only
```

Pick the **release** build you ship. A debug build will (rightly) trip `debuggable` and `cleartext-traffic`.
iOS: the simulator `.app` is enough for manifest, static and data checks; it is not what you ship, so say so in the report.

## 2. Gather evidence, cheapest first

| Evidence | Android | iOS (simulator `.app`) | Rules covered |
|---|---|---|---|
| Manifest / plist | `aapt2 dump xmltree --file AndroidManifest.xml app.apk`; network config from `res/xml/` | `plutil -p App.app/Info.plist`; look for `PrivacyInfo.xcprivacy` | `exported-component`, `cleartext-traffic`, `debuggable`, `allow-backup`, `ats-exceptions`, `privacy-manifest-missing` |
| Data left behind | crawl first (`crawl-app`), then `adb shell run-as <pkg> ls -R` (debuggable builds only) | `xcrun simctl get_app_container <udid> <bundle> data`, then `plutil -p` the preferences | `secrets-at-rest` |
| Static scan | `jadx -d out app.apk`, then grep `out/sources`, `out/resources` | `strings` on the binary, grep the bundle | `hardcoded-secret`, `webview-js-interface`, `insecure-trust-manager`, `weak-crypto`, `sensitive-logging` |
| Dynamic | `frida -U -f <pkg> -l hook.js` (a frida server on an emulator or rooted device) | frida needs a prepared target; treat as unproven here | `no-cert-pinning`, `cleartext-observed` |

Detection hints for every rule are in `security-rules/reference/rules.md`. Start with manifest + data; add static when time
allows; do dynamic only when asked. Say which categories you did **not** run: an audit that skipped a category must not
read as a pass.

## 3. Judge

Apply `security-rules` ("Reading a finding"). For each candidate: open the code or file, confirm it's real, then keep it,
downgrade it (say why) or drop it. Match it to a rule id; one rule can produce several findings.

## 4. Write the result

Write `runs/<project>/<run-id>/audits/security.json` (shape in `docs/MAP_SCHEMA.md`, "audits"). The viewer picks it up and
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

## Building the scanner (the work this skill leads to)

Order by cost: (1) manifest and Info.plist rules from `apkinfo.py`'s aapt2 calls; (2) `secrets-at-rest` from the data
container the drivers already resolve; (3) static rules over jadx output with fixture tests; (4) frida last. Each rule gets a
fixture test, `status` flips to `ready` in the JSON, and the command writes `audits/security.json` itself. Use `extend-crawler`
for the CLI wiring.
