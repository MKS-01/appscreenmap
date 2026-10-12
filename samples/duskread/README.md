# DuskRead sample

[DuskRead](https://github.com/MKS-01/duskread) is a real reading app (MIT, by the AppScreenMap author):
save links, follow blogs, hear articles read aloud, a focus timer. It's built with Kotlin
Multiplatform and Compose, which makes it a good real-world test. Compose exposes almost no resource
ids, so screen identity and element keys have to come from structure and text.

| File | What it is |
|---|---|
| `duskread-1.3.0.apk` | The release build (4.2 MB, signed by the author) |
| `appscreenmap.toml` | Crawl config: budgets, the onboarding name, a dummy Notion token |
| `build.sh` | Rebuilds the APK from source (uses `../../../duskread` or clones the repo) |

## What a crawl finds

From a clean install (`--clear-data`), the crawl:
- starts at onboarding ("What should I call you?"), types the name from the config, and taps *Get started*
- maps Home (focus timer, latest posts), Following, Saved, Settings, the Focus timer states and Connect Notion
- infers the bottom navigation and the theme switch in the bar instead of tapping them on every screen
- reports Compose controls without a role (WCAG 4.1.2), the Focus timer's continuous redraw (`perf`),
  and onboarding as unreachable once completed (expected: it only exists on first run)

## Run it

```bash
uv run appscreenmap crawl --apk samples/duskread/duskread-1.3.0.apk \
  --config samples/duskread/appscreenmap.toml --clear-data --project duskread
```

The committed sample run lives in `runs/duskread/`.
