# appscreenmap-security

All of AppScreenMap's security tooling in one place: the scanner behind `appscreenmap security`, its rule
catalogue, and the Frida hook for the dynamic check. Standard library only; depends on `appscreenmap-drivers`
(for `aapt2`). For apps you own or are authorised to test.

| Module | What |
|---|---|
| `appscreenmap.security.manifest` | `aapt2 dump xmltree` → manifest and network security config → findings (debuggable, backup, cleartext, exported components) |
| `appscreenmap.security.secrets` | hard-coded secrets in dex files, resources and assets (value never kept: length + sha256 fingerprint) |
| `appscreenmap.security.apk` | `scan_apk`: manifest checks + secret scan for one APK |
| `appscreenmap.security.device_data` | plain-text secrets left in the app's data folder (adb `run-as`) |
| `appscreenmap.security.frida` | parses what the hook prints; `HOOK` is the hook's path |
| `appscreenmap.security.audit` | combines every source's evidence into `audits/security.json` (score, findings, rule text) |
| `appscreenmap.security.rules` | loads and validates `rules.json` |
| `rules.json` | the rule catalogue: id, severity, why, fix, official sources, `planned`/`ready`. Read by the viewer too |
| `hooks/frida-observe.js` | observation-only Frida hooks (cleartext requests, certificate pinning); `appscreenmap security --frida-script` prints its path |

`from appscreenmap.security import scan_apk, write_audit, …` re-exports the public functions. Rules are
documented in the `security-rules` skill; running an audit is the `security-audit` skill.
