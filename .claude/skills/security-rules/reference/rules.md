# Security rules: the full catalogue

Machine-readable twin: `src/appscreenmap/security_rules.json` (validated by `security_rules.py`; a test fails if a rule is
missing here). Status is **planned** for every rule today: the scanner that runs them doesn't exist yet, so the viewer shows
them as "not set up". "Detect" says how a rule will be checked and what you can do by hand now. Every source is official.

Severity: **error** = fix before release, **warning** = fix or justify, **info** = a decision to make on purpose.

## Manifest and Info.plist (evidence: the build's manifest, no code run)

| Rule | Platform | Severity | Detect | Source |
|---|---|---|---|---|
| `exported-component` | Android | warning | `aapt2 dump xmltree --file AndroidManifest.xml app.apk`: any `activity`, `service`, `receiver`, `provider` with `android:exported=true` and no `android:permission` | [android:exported](https://developer.android.com/privacy-and-security/risks/android-exported) |
| `cleartext-traffic` | Android | warning | manifest `android:usesCleartextTraffic=true`, or a network security config with `cleartextTrafficPermitted=true` | [Cleartext communications](https://developer.android.com/privacy-and-security/risks/cleartext-communications) · [Network security configuration](https://developer.android.com/privacy-and-security/security-config) |
| `debuggable` | Android | **error** | manifest `android:debuggable=true` on a release build | [android:debuggable](https://developer.android.com/privacy-and-security/risks/android-debuggable) |
| `allow-backup` | Android | warning | `android:allowBackup` true or absent, without `dataExtractionRules` / `fullBackupContent` | [Security recommendations for backups](https://developer.android.com/privacy-and-security/risks/backup-best-practices) |
| `ats-exceptions` | iOS | warning | `plutil -p App.app/Info.plist`: `NSAppTransportSecurity` with `NSAllowsArbitraryLoads` or `NSExceptionDomains` | [Preventing insecure network connections](https://developer.apple.com/documentation/security/preventing-insecure-network-connections) |
| `privacy-manifest-missing` | iOS | warning | no `PrivacyInfo.xcprivacy` in the `.app` (or in an embedded SDK that needs one) | [Privacy manifest files](https://developer.apple.com/documentation/bundleresources/privacy-manifest-files) |

## Static scan of the compiled code (evidence: decompiled output; no app run)

Android: `jadx -d out app.apk`, then search `out/sources` and `out/resources`. iOS: `strings` over the app binary and a
grep of the bundle's plists and resources.

| Rule | Platform | Severity | Detect | Source |
|---|---|---|---|---|
| `hardcoded-secret` | both | **error** | high-entropy strings and known key shapes (AWS `AKIA…`, `AIza…`, `-----BEGIN … PRIVATE KEY-----`, `Bearer …`, `password=`) in code and resources; each hit is reviewed, not auto-failed | [Hardcoded Cryptographic Secrets](https://developer.android.com/privacy-and-security/risks/hardcoded-cryptographic-secrets) |
| `webview-js-interface` | Android | warning | `addJavascriptInterface(`, `setJavaScriptEnabled(true)` where the WebView loads a non-constant URL | [WebView – Native bridges](https://developer.android.com/privacy-and-security/risks/insecure-webview-native-bridges) |
| `insecure-trust-manager` | Android | **error** | an `X509TrustManager` whose `checkServerTrusted` is empty; a `HostnameVerifier` returning `true`; `onReceivedSslError` calling `proceed()` | [Unsafe X509TrustManager](https://developer.android.com/privacy-and-security/risks/unsafe-trustmanager) · [Unsafe HostnameVerifier](https://developer.android.com/privacy-and-security/risks/unsafe-hostname) |
| `weak-crypto` | Android | warning | `Cipher.getInstance("DES…" / "…/ECB/…" / "RC4")`, `MessageDigest.getInstance("MD5" / "SHA-1")` near credentials, a constant `IvParameterSpec` | [Broken or risky cryptographic algorithm](https://developer.android.com/privacy-and-security/risks/broken-cryptographic-algorithm) |
| `sensitive-logging` | Android | info | `Log.*` calls whose arguments name a token, password or personal field | [Log Info Disclosure](https://developer.android.com/privacy-and-security/risks/log-info-disclosure) |

## Dynamic run (evidence: the app instrumented while it runs; needs frida)

The least ready category: it needs a debuggable or rooted target (an emulator image that allows it) and a frida server.
Findings from a run are observations of one session, not proof of absence.

| Rule | Platform | Severity | Detect | Source |
|---|---|---|---|---|
| `no-cert-pinning` | both | info | route the app through a proxy with a user-installed CA; if its API calls succeed, nothing pins | [Network security configuration](https://developer.android.com/privacy-and-security/security-config) |
| `cleartext-observed` | both | **error** | hook the HTTP stack (OkHttp, `HttpURLConnection`, `URLSession`) and record any `http://` request | [Cleartext communications](https://developer.android.com/privacy-and-security/risks/cleartext-communications) · [Preventing insecure network connections](https://developer.apple.com/documentation/security/preventing-insecure-network-connections) |

## Data left on the device (evidence: the app's data folder after a crawl; needs no instrumentation)

| Rule | Platform | Severity | Detect | Source |
|---|---|---|---|---|
| `secrets-at-rest` | both | warning | after the crawl, read the data container (Android: `adb shell run-as <pkg>` on a debuggable build; iOS simulator: `xcrun simctl get_app_container <udid> <bundle> data`) and look for tokens in `shared_prefs/*.xml`, databases, plain files, `Library/Preferences/*.plist` | [Security checklist](https://developer.android.com/privacy-and-security/security-tips) · [Keychain services](https://developer.apple.com/documentation/security/keychain-services) |

This is the cheapest rule to implement first: the crawler already has the container path (`driver_ios.clear_data` resolves it).

## Backlog: rules the crawl or build analysis would add (not in the catalogue yet)

These come from `docs/PLAN.md` §8.4. They enter `security_rules.json` (and the table above) when there's an official page to
cite and a way to detect them with a fixture test.

| Candidate | Evidence | Idea |
|---|---|---|
| `no-secure-flag` | crawl | A screen with a password, OTP or payment field whose screenshot is capturable (Android: `FLAG_SECURE` makes `screencap` black), so it can be recorded or shown in Recents |
| `deeplink-crash` | crawl | Launching an exported activity or deep link with no extras or malformed input crashes the app or lands past a login |
| `permission-before-use` | crawl | A runtime permission requested on a screen that doesn't need it yet |
| `signing-debug-cert` | build | The release is signed with a debug certificate or a v1-only scheme |
| `vulnerable-dependency` | build | A bundled library version has a known advisory (OSV) |
| `ios-get-task-allow` | build | The `get-task-allow` entitlement is on in a distribution build |
| `unprotected-native-lib` | build | A native library lacks basic hardening flags |

## Adding or changing a rule

See `security-rules/SKILL.md`: edit the JSON, add the row here, run `uv run pytest tests/test_security_rules.py`.
