# AppScreenMap Playground (iOS)

SwiftUI version of the Playground (`../playground-app/`), same scenarios, so iOS crawls have known answers.
**First slice, v1 only**: bundle id `dev.appscreenmap.playground`, iOS 17+. Deliberate bugs are marked
`A11Y BUG (WCAG x.y.z)` in the source.

```bash
./build.sh   # needs Xcode + xcodegen; writes build/Playground.app (git-ignored; the .xcodeproj is generated from project.yml)
APP_PASSWORD=playground-demo appscreenmap crawl --platform ios --app samples/playground-ios/build/Playground.app \
  --config samples/playground-app/appscreenmap.toml --clear-data --max-steps 60
```

| Screen | Demonstrates |
|---|---|
| Welcome back (sign in), Reset password, Check your inbox | first-run state, form autofill, 3.3.7 Redundant Entry |
| Discover (Home) | list of 12 article cards, one template (`variant_of`), tab bar, Help top-right, 20 pt bookmark/share icons (2.5.8, 4.1.2), one-line titles (1.4.4) |
| Article | caption contrast (1.4.3), "Listen" announced as "Play audio" (2.5.3) |
| Search, Library, Profile | tabs; Profile has Account settings, Help and Log out (never tapped) |
| Help → Feedback | unlabeled message field (3.3.2) |

## Known gaps

- Not built yet: Reports, Gallery, Notifications, Text size, Terms, Developer options, the v2 build.
- `idb ui describe-all` returns the tab bar as one "Tab Bar" group without its children, so a crawl never leaves
  Home. `describe-point` does see the tabs (`RadioButton`, `AXTabButton`). Needs a driver fix (`drivers/ios.py`).
- Inside a list row the bookmark and share icons merge into the card's button, so the 2.5.8 and 4.1.2 bugs are
  not visible to the tree.
