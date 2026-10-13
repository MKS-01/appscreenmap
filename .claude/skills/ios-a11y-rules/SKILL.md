---
name: ios-a11y-rules
description: Accessibility rules for native iOS apps (SwiftUI and UIKit) in AppScreenMap terms — WCAG 2.2 mapped to VoiceOver, Dynamic Type, Voice Control, Switch Control and Apple's HIG thresholds (44 pt targets), what the crawler can detect from the accessibility tree today, what needs a device or a person, and the Swift fix for each. Use when interpreting an iOS crawl's accessibility findings, writing fix guidance for an iOS app, deciding if something is a failure, or designing a new iOS a11y check.
---

# iOS accessibility: the rules

The Android counterpart is `wcag-mobile-rules` (criteria catalogue in `src/appscreenmap/wcag.py`); this page is what changes on
iOS. WCAG 2.2 still decides pass/fail; Apple's HIG sets stricter numbers in places. Say which one a finding used.

## The iOS accessibility tree is the evidence

The crawler reads what `idb ui describe-all` returns (see `ios-simulator`): the same tree VoiceOver walks. So:

- **A control that isn't in the tree can't be reached by VoiceOver, Voice Control, Switch Control or the crawler.** That's
  the strongest iOS finding and it is detected for free: the crawl simply can't get there. DuskRead's floating tab bar and
  Settings "×" are the live examples.
- Per element the tree gives: `AXLabel` (the accessible name), `AXValue`, `AXUniqueId` (the `accessibilityIdentifier`;
  tests only, VoiceOver never reads it), `type`, `traits` (Button, StaticText, TextEntry, NotEnabled, Selected, Header…),
  `frame` in points, `enabled`, `custom_actions`. Order in the list is the VoiceOver reading order.
- `Scrollable` appears on nearly every node; ignore it.

## Translating terms

| WCAG / Android says | On iOS |
|---|---|
| Accessible name | `accessibilityLabel` (SwiftUI: `.accessibilityLabel("…")`; text and `Label` get one automatically; an icon-only `Image`/`Button` does **not**) |
| Role | `accessibilityTraits` (`.isButton`, `.isHeader`, `.isSelected`, `.isImage`, `.isLink`…). SwiftUI `Button` and `Toggle` set theirs; a tap-gesture on a view does not. |
| Value / state | `accessibilityValue` ("50 percent", "on"); `.isSelected` for tabs |
| Hint | `accessibilityHint`: the result of acting, read after a pause. Never repeat the label. |
| dp / CSS px | 1 point ≈ 1 dp. Our iOS runs store points with `density: 160`, so checks read points as dp. |
| Large text | Dynamic Type: `xSmall…xxxLarge` plus five accessibility sizes (AX1–AX5); 200 % ≈ `accessibility-large`. |
| Keyboard | Full Keyboard Access (Settings → Accessibility → Keyboards), Switch Control, external keyboard focus |
| Heading | `.accessibilityAddTraits(.isHeader)`; VoiceOver's Headings rotor jumps between them |
| Screen title | the navigation bar title (`navigationTitle`) or a header at the top |

## Thresholds

| Thing | Rule | Source |
|---|---|---|
| Touch target | **≥ 44 × 44 pt** (WCAG 2.5.8 AA allows 24 × 24 CSS px with spacing; the HIG is stricter: report < 44 as a warning, < 24 as the WCAG failure) | HIG / WCAG 2.5.8 |
| Text contrast | 4.5 : 1 (3 : 1 for large text: ≥ 18 pt, or ≥ 14 pt bold); non-text 3 : 1 | WCAG 1.4.3 / 1.4.11 |
| Text size | Must scale with Dynamic Type up to 200 % with nothing clipped or overlapping | WCAG 1.4.4 / 1.4.10 |
| Motion | Honour Reduce Motion (`@Environment(\.accessibilityReduceMotion)`): replace slides and parallax with fades | WCAG 2.3.3, HIG |
| Contrast settings | Look right with Increase Contrast (`\.colorSchemeContrast`), Bold Text (`\.legibilityWeight`), Dark Mode, Reduce Transparency | HIG |
| Orientation | Don't lock unless essential | WCAG 1.3.4 |

## What the crawler checks, by evidence

| Check | Criterion | iOS evidence | Status |
|---|---|---|---|
| Control not reachable (absent from tree) | 4.1.2, 2.1.1, 2.5.3 | crawl can't reach it / screenshot shows it | **found by crawling**; no dedicated rule yet |
| Tappable element with no `AXLabel` | 4.1.2, 1.1.1 | Button with empty label | works in the **viewer's scanner** (`label-missing`, `web/src/a11y.ts`) for a control that is present but unnamed; no crawler rule yet |
| Target < 44 pt (warn) / < 24 pt (fail) | 2.5.8 | `frame` | viewer scanner flags < 44 pt (Apple HIG) as a warning; the crawler's `target-size-min` (`a11y.json`) fails < 24 pt with the spacing exception |
| Section titles without Header trait | 1.3.1, 2.4.6 | no `Header` in traits on any title-like text | planned; DuskRead has 0 `.isHeader` |
| No `accessibilityIdentifier` | (testability, not WCAG) | `AXUniqueId` null | reported as an info on screens with actions |
| Label doesn't contain visible text | 2.5.3 (Voice Control) | the tree has one string (`AXLabel`), not the drawn text | **not detectable yet**: `label-in-name` needs both; would need OCR or matching against the screenshot |
| Text truncated at 200 % | 1.4.4 | crawl with `--font-scale 2.0`, ellipsis in labels | works (`text-truncated`) |
| Reading order wrong | 1.3.2, 2.4.3 | list order vs top-to-bottom y | planned |
| Text contrast | 1.4.3 | screenshot pixels (viewer's scanner) | works |
| Orientation lock | 1.3.4 | `UISupportedInterfaceOrientations` in Info.plist | planned (read from the `.app`) |

## What needs a device or a person

VoiceOver announcements and gestures (magic tap, escape, custom actions), the Headings rotor, Voice Control commands
("Tap <name>"), Switch Control scanning order, Full Keyboard Access focus ring, Reduce Motion behaviour, captions and audio
descriptions, cognitive criteria (3.3.7 redundant entry, 3.3.8 accessible authentication). Record these in the a11y audit's
manual list (`a11y-audit` skill), not as automated findings.

## Fixes (SwiftUI)

```swift
Button { … } label: { Image(systemName: "bookmark") }
  .accessibilityLabel("Save")                      // icon-only control: name it
Text("VOICE").accessibilityAddTraits(.isHeader)    // section title
Image("hero").accessibilityHidden(true)            // decorative
HStack { … }.accessibilityElement(children: .combine)   // one stop instead of three
Button { … }.frame(minWidth: 44, minHeight: 44)    // or .contentShape(Rectangle()) with padding
Text(title).font(.body)                            // text styles scale; fixed sizes don't
  .dynamicTypeSize(...DynamicTypeSize.accessibility3)   // cap only where the layout truly can't grow
view.accessibilityIdentifier("tab.following")      // stable id for tests and AppScreenMap; VoiceOver ignores it
```

A custom control built from `onTapGesture` is invisible to assistive tech: use `Button`, or add
`.accessibilityElement()`, `.accessibilityLabel`, `.accessibilityAddTraits(.isButton)` and `.accessibilityAction`.

## Adding an iOS rule

Follow `add-a11y-rule`. iOS runs have `run.device.platform == "ios"`; rules that read Android-only attributes (resource ids
with `/`, activities, `content-desc`) must branch on it or be skipped. In the viewer (`web/src/a11y.ts`) wording that differs
by platform lives in the `IOS` overrides (read through `useRules()`, set by the run shell's `PlatformCtx`), and
`TARGET_MIN` holds the per-platform target size (48 dp Android, 44 pt iOS). The translated XML puts `AXLabel` in `text` (or
`hint` for fields) and `AXUniqueId` in `resource-id` as `<bundle>:id/<id>`. Test with a recorded tree
(`tests/fixtures/duskread-ios-home.json`), never a device.

## Known findings in DuskRead (the iOS sample), Oct 2026

1. `Shell/FloatingBar.swift`: the four tab buttons have no label/trait, so they are not in the tree.
2. Settings "×" close button: unlabeled, absent from the tree.
3. 0 `accessibilityIdentifier`, 3 `accessibilityLabel` across `iosApp/`.
4. 0 `.isHeader` traits: section titles (VOICE, NOTION, APPEARANCE…) are plain text.
5. 23 touch targets under 44 pt on Home alone (Settings 34×34 pt, the 15/25/30 MIN buttons 32 pt tall).
6. Cards open an in-app browser (out of process: nothing for the crawler to read there).
