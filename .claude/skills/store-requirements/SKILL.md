---
name: store-requirements
description: Keep AppScreenMap's store rules current — the dated Google Play target-API and App Store SDK / deployment-target requirements in packages/store/.../requirements.json that `appscreenmap store` measures builds against. Use when asked to update, refresh or review the store rules, after a Play Console or Apple announcement, each spring and autumn, when the audit's "rules checked" date is more than ~3 months old, or when `appscreenmap store` says nothing about a deadline you know exists.
---

# Store requirements upkeep

`appscreenmap store` (package `packages/store`) compares a build's **target SDK, compile SDK and minimum SDK** (Android) or
**build SDK, Xcode and deployment target** (iOS) with the rules in `packages/store/src/appscreenmap/store/requirements.json`.
It always lists every rule that starts within the next **365 days** as `upcoming`, so the data must stay ahead of the stores.
The viewer's source catalogue is `apps/viewer/src/insights/sources.ts` (owned by the viewer session: tell it what to change).

## When

| Trigger | Why |
|---|---|
| **April–May** | Apple raises the minimum SDK / Xcode every April (Xcode and SDK 26 on 2026-04-28); Google publishes the August target-API deadline in spring |
| **31 August** | Play's target-API deadline; the extension runs to 1 November |
| **After WWDC (June) and the Android release (June)** | New SDK levels; check what the stores announce next |
| `checked` older than ~3 months | Stale data makes a "Compatible" answer untrustworthy |

## Steps

1. **Read the official pages only**, with today's date in mind (these are the sources the `refs` point at):
   - Play: <https://support.google.com/googleplay/android-developer/answer/11926878> (target API by form factor, extension date, the availability rule for existing apps; the page contradicts itself in places: tables win, flag the difference)
   - Apple: <https://developer.apple.com/news/upcoming-requirements/> and the News feed (SDK minimum, deployment target)
   Blog posts repeat these with errors (we saw one claim API 35 was still current). Never copy a date from a secondary source.
2. **Edit `requirements.json`**:
   - New Play level → append `{"api": N, "from": "YYYY-MM-DD", "extension_until": "…"}` to each affected form factor in `android.tiers`; update `existing_app_min_api` if the availability floor moved.
   - Apple → update `ios.sdk` / `ios.deployment` (`min_major`, `from`, `text` quoted from the page).
   - A rule neither store has published goes in `expected` (text only), never in `tiers`. When the store publishes it, move it to `tiers` and rewrite `expected` for the *next* year.
   - Set `checked` to today.
   - Keep old tiers: the audit hides those beyond the window and still uses them to decide what is `met`.
3. **Add a test** in `packages/store/tests/test_store.py` for the new boundary (use the `today` parameter: a day before the date → `upcoming`, on it → `due`/`blocked`, after the extension → `blocked`).
4. **Check the fix text** in `audit.py`: the behaviour changes named in the Android target fix (edge-to-edge at 35; large-screen orientation limits ignored, predictive back at 36) should name the level you just added. Read the matching behaviour-change page on developer.android.com first.
5. **Run**: `uv run pytest -q packages/store && uv run ruff check && uv run ruff format`, then
   `uv run appscreenmap-engine store --apk samples/playground-app/apk/playground-v1.apk` and read the output. The Playground sets
   `targetSdk`/`compileSdk` in `samples/playground-app/app/build.gradle.kts`: raise both when a new level is due, rebuild with `samples/playground-app/build.sh`.
6. **Say what changed**: old rule → new rule, the date, and the page you read. If you couldn't reach an official page, leave the data alone and say so.

## Related audit skills

Only audit and scan skills are vendored, never development ones. From github.com/android/skills (Apache-2.0, unchanged,
pinned in `scripts/android-skills.lock`): `play-policy-insights` (Play policy), `android-permissions-security`,
`android-intent-security`, `edge-to-edge` (what target 35+ enforces), `adaptive` (large screens, foldables, resizable windows: what target 36 stops letting apps opt out of). `make skills-check` reports drift from upstream and `make skills-sync` copies and re-pins; run it
with the spring review. From Apple (Xcode 27, no license, git-ignored): `audit-xcode-security-settings`, `uikit-app-modernization` (multi-window and orientation on the 26+ SDKs), via `make skills-xcode`.
Never hand-edit the copies.
