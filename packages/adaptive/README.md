# appscreenmap-adaptive

Adaptive UI audit. `rules.json` is the rule catalogue: Android's adaptive app quality tiers, Android 17's ignored
orientation / resizability limits, Apple's HIG Layout and iPhone Duo. Each rule says how it is detected: `static`
(the build's manifest or Info.plist, this package), `condition` (a crawl per device profile, stage 4) or `manual`
(listed as not tested, with steps). Writes `audits/adaptive.json`. Depends on `drivers` (aapt2).

| Module | What |
|---|---|
| `appscreenmap.adaptive.facts` | `android_facts` / `parse_manifest` (aapt2 xmltree), `ios_facts` / `parse_plist` |
| `appscreenmap.adaptive.audit` | `build_audit`, `write_audit`, `load_rules` |
