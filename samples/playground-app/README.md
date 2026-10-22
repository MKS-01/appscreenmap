# AppScreenMap Playground

A small Jetpack Compose app built to exercise every AppScreenMap feature on purpose. Every screen
exists for a reason, so each crawl has a known answer. Two builds of the same app (`v1`, `v2`) power
the comparison demos: visual diff, performance, and accessibility before and after.

| File | What it is |
|---|---|
| `apk/playground-v1.apk` | Release build 1.0 (R8, signed with a debug key, so anyone can install it) |
| `apk/playground-v2.apk` | Release build 2.0: the "next release", with some fixes and changes (below) |
| `appscreenmap.toml` | Crawl config (budgets, form inputs) |
| `build.sh` | Rebuilds both APKs from source into `apk/` |
| `app/` | Source (`MainActivity.kt` navigation, `Screens.kt` screens, `ScannerActivity.kt`) |

Package `dev.appscreenmap.playground`, minSdk 26, targetSdk 36. Compose test tags are exposed as
resource ids (`testTagsAsResourceId`), so selectors and Maestro flows use stable ids like `sign_in`.

## Screens and the scenario each one demonstrates

| Screen | How to reach it | Demonstrates |
|---|---|---|
| Welcome back (sign in) | First launch (`--clear-data`) | First-run / empty state, **form autofill** (email + password from the config), `login` pattern, error text (3.3.1), **3.3.8** review flag |
| Reset password → Check your inbox | Sign in → Forgot password? | Email asked twice in one flow: **3.3.7 Redundant Entry** |
| Discover (Home) | Sign in / Continue as guest | **Bottom nav** (+ inferred nav edges), **list pattern** (12 cards, first two explored, rest skipped as one template), feed under the bottom bar (**2.4.11**), 20 dp icons 6 dp apart (**2.5.8**), unlabeled bookmark icon (viewer: missing label), one-line ellipsized titles (**1.4.4**), Help top-right (**3.2.6**) |
| Article | Any card / search result / history item | **Variants**: every article is one template (`variant_of`), "Listen" announced as "Play audio" (**2.5.3**), light grey caption (viewer: **1.4.3** contrast) |
| Reports | Home → Reports | **Slow screen**: a spinner for 2.5 s, then content. Timed until the content draws (`waited_for_loading`), rated *slow* |
| Gallery | Home → Gallery | **Jank**: about 35 ms of UI-thread work per frame for 45 frames. Janky frames in `perf.json` |
| Search | Bottom nav | Typing three letters jumps to results (**3.2.2 On Input**, `change_on_input` event), bottom bar in a different order (**3.2.3**) |
| Results | Search → type / popular search | List → article template |
| Library | Bottom nav | **Tabs** (Downloads / History), empty state |
| Profile | Bottom nav | Settings list, Help mid-list (**3.2.6** vs Home), Privacy policy opens the browser (**stays in app**: blocked by pinning), **Log out** never tapped (`blocked_text`) |
| Rate us dialog (v1) | Profile → Rate us | `dialog` pattern; the screen is named after what opened it |
| Account settings | Profile | Same email again (**3.3.7**), `primary_action` = "Save" (vs "Submit" on Feedback: **3.2.4**), **Delete account** never tapped |
| Notifications | Profile | **Toggles**, a runtime permission request (`POST_NOTIFICATIONS`) |
| Text size | Profile | A slider: **2.5.7 Dragging Movements** review flag |
| Help → Feedback | Profile → Help → Contact support | Unlabeled message field (viewer: **3.3.2**), same id with a different label (**3.2.4**) |
| Terms of use | Profile | **WebView** pattern (local HTML) |
| Developer options | Profile | Depth 2: **crash button** (crash + logcat captured, app relaunched), **Open scanner**, **Network check** |
| Network check | Developer → Network check | `crawl --network`: calls `api.playground.test` (HTTPS), `cdn.playground.test` over plain `http://` (**SECURITY BUG** `cleartext-observed`, allowed by `res/xml/network_security_config.xml`) and the third-party `events.tracker.test`. `.test` hosts never resolve, so nothing leaves the device; the screen's text never changes with or without a proxy |
| Scanner | Developer → Open scanner | A **second activity** (activity coverage), locked to portrait (**1.3.4**, from the manifest) |

## v1 → v2 changes (for `appscreenmap diff`, `perf`, `a11y`)

| Change | Shows up as |
|---|---|
| "Sign in" → "Log in", teal button | Visual diff: *changed* (sign-in screen) |
| Home title "Discover" → "For you"; feed gets bottom padding | *changed*; 2.4.11 finding gone |
| Bookmark/share icons 20 dp → 48 dp, bookmark gets a label | *changed*; 2.5.8 and missing-label findings gone |
| Article titles wrap to 3 lines | 1.4.4 truncation findings gone |
| "Listen" announced as "Listen to this article"; caption darker | 2.5.3 and contrast findings gone |
| Search waits for the Search button; bottom bar order fixed | 3.2.2 and 3.2.3 findings gone; new *Search* button |
| Reports load in 0.6 s instead of 2.5 s | `perf`: Reports goes from *slow* to *ok* |
| Gallery has no UI-thread work | `perf`: jank on Gallery drops |
| "Rate us" dialog removed, "What's new" screen added | Visual diff: *missing* and *new* screens |
| Feedback message field gets a label; Text size gets +/− buttons | 3.3.2 fixed; 2.5.7 alternative provided |
| Network check: banner over https, plus a `/v1/whats-new` call | `cleartext-observed` gone; one endpoint added (network diff, planned) |

## Rebuild

```bash
./build.sh            # needs JDK 17+ and the Android SDK (ANDROID_HOME or ~/Library/Android/sdk)
```
