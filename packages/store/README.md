# appscreenmap-store

Store readiness: does a build meet Google Play's and the App Store's SDK rules, now and over the next 12 months.
Standard library only; depends on `appscreenmap-drivers` (for `aapt2`).

| Module | What |
|---|---|
| `appscreenmap.store.facts` | Android: `targetSdk` / `minSdk` / `compileSdk` from the manifest (`aapt2`). iOS: build SDK, Xcode and deployment target from `Info.plist` (`.app` or `.ipa`) |
| `appscreenmap.store.audit` | facts + `requirements.json` → `audits/store.json`; always lists every requirement due within `HORIZON_DAYS` (365) as `upcoming`, with its date |
| `requirements.json` | the dated store rules (data, no code). Keep it current with the `store-requirements` skill |

`appscreenmap store [run] --apk FILE | --app FILE [--form-factor phone|wear|tv|automotive|xr] [--today YYYY-MM-DD]`.
