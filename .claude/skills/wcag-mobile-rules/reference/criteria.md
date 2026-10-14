# WCAG 2.2 Level A and AA on native Android

Columns: **Check** = how AppScreenMap covers it: `crawler:<rule>` (a11y/checks.py), `viewer:<rule>`
(apps/viewer/src/a11y.ts), `device` (an adb test in the a11y-audit skill), `manual`.
Fixes: **V** = Android Views, **C** = Jetpack Compose. ★ = new in 2.2. † = advisory for a single
native app under WCAG2ICT / EN 301 549.

## 1 Perceivable

| SC | Lvl | On Android | Check | Fix |
|---|---|---|---|---|
| 1.1.1 Non-text Content | A | Meaningful images/icons have a text alternative; decorative ones are hidden from TalkBack | viewer:label-missing (tappable), crawler:image-alt (review) | V: `contentDescription`, decorative `importantForAccessibility="no"` / `null` desc. C: `contentDescription = …` / `null` |
| 1.2.1 Audio-only & Video-only | A | Transcript or alternative for prerecorded media | manual | Provide transcript / described alternative |
| 1.2.2 Captions (Prerecorded) | A | Videos with audio have captions | manual | Media3 subtitle tracks; respect `CaptioningManager` |
| 1.2.3 Audio Description or Alternative | A | Described video or full text alternative | manual | Alternate audio track / transcript |
| 1.2.4 Captions (Live) | AA | Live streams have captions | manual | Live caption track |
| 1.2.5 Audio Description | AA | Prerecorded video has audio description | manual | Described audio track |
| 1.3.1 Info and Relationships | A | Structure is exposed: headings, lists, label↔field, grouping | viewer:field-unlabeled (partial), manual | V: `accessibilityHeading`, `labelFor`, `screenReaderFocusable` groups. C: `semantics { heading() }`, `mergeDescendants` |
| 1.3.2 Meaningful Sequence | A | TalkBack reading order matches the visual order | device (TalkBack swipe-through), manual | V: `accessibilityTraversalBefore/After`. C: `traversalIndex`, `isTraversalGroup` |
| 1.3.3 Sensory Characteristics | A | Instructions don't rely only on shape, colour, size, or position ("tap the round button") | manual | Name the control in text |
| 1.3.4 Orientation | AA | Works in portrait and landscape unless essential | crawler:orientation-locked (manifest), device (rotate) | Remove `screenOrientation` locks; handle config changes |
| 1.3.5 Identify Input Purpose | AA | Personal-data fields declare their purpose | manual (autofillHints not in the dump) | V: `android:autofillHints`. C: `semantics { contentType = ContentType.EmailAddress }` |
| 1.4.1 Use of Color | A | Colour isn't the only signal (errors, states, links) | manual (screenshots) | Add icon/text/underline |
| 1.4.2 Audio Control | A | Auto-playing audio > 3 s can be paused or muted | manual | Pause control; don't autoplay |
| 1.4.3 Contrast (Minimum) | AA | Text 4.5:1, large text 3:1 | viewer:contrast (estimate) | Adjust theme colours; check dark mode too |
| 1.4.4 Resize Text | AA | Works at 200% font scale without loss | crawler:text-truncated, device (`--font-scale 2.0` crawl) | Use sp; avoid fixed heights, `maxLines` + ellipsis on key text |
| 1.4.5 Images of Text | AA | No text baked into images (except logos) | manual (screenshots) | Real text views |
| 1.4.10 Reflow | AA | No 2-D scrolling at 320 dp width / large font | device (large font + display size) | Wrap content; scroll in one direction |
| 1.4.11 Non-text Contrast | AA | Icons, control borders, and focus indicators 3:1 against neighbours | manual (screenshots), viewer contrast is text-only | Stronger outlines / icon colours |
| 1.4.12 Text Spacing | AA | Mostly N/A natively (users can't override spacing); content must survive larger line height if the platform allows | manual | Avoid fixed-height text containers |
| 1.4.13 Content on Hover or Focus | AA | Tooltips/popups are dismissible, hoverable, and persistent | manual | Long-press tooltips stay until dismissed |

## 2 Operable

| SC | Lvl | On Android | Check | Fix |
|---|---|---|---|---|
| 2.1.1 Keyboard | A | Every action works with keyboard, D-pad, and Switch Access | crawler:not-focusable, device (Switch Access / Tab) | V: `focusable`, handle `onKeyDown`. C: `clickable`/`focusable` modifiers, `onKeyEvent` |
| 2.1.2 No Keyboard Trap | A | Focus can always leave a component | device | Don't consume Tab/D-pad in custom views |
| 2.1.4 Character Key Shortcuts | A | Single-key shortcuts can be turned off or remapped | manual | Require a modifier key |
| 2.2.1 Timing Adjustable | A | Time limits can be turned off, adjusted, or extended (toasts/snackbars with actions!) | manual | `AccessibilityManager.getRecommendedTimeoutMillis`; snackbars with actions shouldn't auto-dismiss |
| 2.2.2 Pause, Stop, Hide | A | Auto-moving content > 5 s (carousels, tickers) can be paused | manual | Pause control; honour "remove animations" |
| 2.3.1 Three Flashes | A | Nothing flashes > 3 times per second | manual | Remove the flashing |
| 2.4.1 Bypass Blocks † | A | Skip repeated blocks; natively, headings and panes make this easy | manual | Headings, `paneTitle`, logical grouping |
| 2.4.2 Page Titled | A | Each screen has a descriptive title (announced on change) | crawler:screen-title (review) | V: activity `title`, `accessibilityPaneTitle`. C: `semantics { paneTitle = … }` |
| 2.4.3 Focus Order | A | Focus moves in a meaningful order | device (Tab/D-pad/Switch Access) | `nextFocusDown` etc. / `focusProperties`, traversal order |
| 2.4.4 Link Purpose (In Context) | A | Link/button purpose clear from its name plus context | viewer:duplicate-label (partial), manual | "Read more about X", not "Read more" |
| 2.4.5 Multiple Ways † | AA | More than one way to reach screens (search, nav) | manual (map shows routes) | Search, nav, links |
| 2.4.6 Headings and Labels | AA | Headings and labels are descriptive | viewer:duplicate-label, manual | Specific labels |
| 2.4.7 Focus Visible | AA | Keyboard/Switch focus is visible | device | Visible focus states (`state_focused`, `indication`) |
| ★ 2.4.11 Focus Not Obscured (Min) | AA | Focused item not fully hidden by sticky UI | crawler:focus-obscured (heuristic), device | Content padding = bar height; `bringIntoView` / `BringIntoViewRequester` |
| 2.5.1 Pointer Gestures | A | Multi-finger or path gestures have single-tap alternatives | manual | Buttons for pinch-zoom, swipe actions; accessibility custom actions |
| 2.5.2 Pointer Cancellation | A | Actions fire on up, not down; can be aborted by moving away | manual | Use click (up) events |
| 2.5.3 Label in Name | A | Accessible name contains the visible text | crawler:label-in-name | Start contentDescription with the visible text, or drop it |
| 2.5.4 Motion Actuation | A | Shake/tilt actions have UI alternatives and can be disabled | manual | Add a button; setting to disable |
| ★ 2.5.7 Dragging Movements | AA | Drag actions have single-pointer alternatives | crawler:dragging (review) | +/− buttons, move up/down actions, `AccessibilityAction`s |
| ★ 2.5.8 Target Size (Minimum) | AA | ≥ 24×24 dp or spacing exception | crawler:target-size-min (with spacing); viewer:touch-target is the 48 dp guideline | `minHeight/minWidth`, padding, `TouchDelegate`; C: `minimumInteractiveComponentSize()` |

## 3 Understandable

| SC | Lvl | On Android | Check | Fix |
|---|---|---|---|---|
| 3.1.1 Language of Page | A | App language set so TalkBack uses the right voice | manual | Proper locale resources |
| 3.1.2 Language of Parts | AA | Foreign-language passages marked | manual | `LocaleSpan` / `AnnotatedString` with `LocaleList` |
| 3.2.1 On Focus | A | Focus alone doesn't change context | device | Don't navigate in focus listeners |
| 3.2.2 On Input | A | Changing a setting/typing doesn't change context unexpectedly | crawler:change-on-input | Navigate on explicit submit only |
| 3.2.3 Consistent Navigation † | AA | Repeated navigation in the same relative order | crawler:nav-inconsistent | One shared nav component |
| 3.2.4 Consistent Identification † | AA | Same function → same label/icon | crawler:identification-inconsistent | Shared strings/components |
| ★ 3.2.6 Consistent Help † | A | Help mechanisms in the same relative order | crawler:help-inconsistent | Fixed place for help/contact |
| 3.3.1 Error Identification | A | Errors identified in text and described | manual (crawler autofill exposes forms) | V: `TextInputLayout.setError`. C: `semantics { error(…) }` |
| 3.3.2 Labels or Instructions | A | Inputs have labels/instructions | viewer:field-unlabeled, viewer:field-desc | Hint plus persistent label (`labelFor`) |
| 3.3.3 Error Suggestion | AA | Suggest how to fix errors | manual | "Use format name@example.com" |
| 3.3.4 Error Prevention (Legal, Financial, Data) | AA | Reversible, checked, or confirmed submissions | manual (crawler never taps pay/delete) | Confirmation step / undo |
| ★ 3.3.7 Redundant Entry | A | Don't ask for the same info twice in one process | crawler:redundant-entry (review) | Pre-fill, "same as shipping" |
| ★ 3.3.8 Accessible Authentication (Min) | AA | No cognitive test to log in without an alternative | crawler:auth-cognitive (review) | Allow paste + autofill (`autofillHints` password/username/oneTimeCode), passkeys/Credential Manager, magic links; avoid text CAPTCHA |

## 4 Robust

| SC | Lvl | On Android | Check | Fix |
|---|---|---|---|---|
| 4.1.1 Parsing | — | **Obsolete and removed in 2.2.** Don't report it. | — | — |
| 4.1.2 Name, Role, Value | A | Every control exposes name, role, and state (checked, selected, expanded) | viewer:label-missing, crawler:no-role, manual for states | Real widgets; C: `semantics { role = …; stateDescription = … }`, `toggleable`/`selectable` |
| 4.1.3 Status Messages | AA | Status updates announced without moving focus | manual (live regions aren't in the dump) | V: `accessibilityLiveRegion`. C: `semantics { liveRegion = LiveRegionMode.Polite }` |

## AAA criteria worth knowing

| SC | What | Note |
|---|---|---|
| 1.4.6 Contrast (Enhanced) | 7:1 / large 4.5:1 | Good target for reading apps |
| 2.4.12 Focus Not Obscured (Enhanced) ★ | No part of the focused item hidden | |
| 2.4.13 Focus Appearance ★ | ≥ 2 dp perimeter, 3:1 change | |
| 2.5.5 Target Size (Enhanced) | 44×44 dp | Android's 48 dp guideline satisfies it |
| 2.5.6 Concurrent Input Mechanisms | Don't block keyboard when touch is present | |
| 3.3.9 Accessible Authentication (Enhanced) ★ | No object-recognition/personal-content exceptions | |

## Sources

- WCAG 2.2: https://www.w3.org/TR/WCAG22/ and "What's new": https://www.w3.org/WAI/standards-guidelines/wcag/new-in-22/
- Understanding docs (per criterion): https://www.w3.org/WAI/WCAG22/Understanding/
- WCAG2ICT (applying WCAG 2.2 to non-web software, W3C Note 2024-10-08): https://www.w3.org/TR/wcag2ict/
  It equates one *software program* to one web page. 2.4.1, 2.4.5, 3.2.3, 3.2.4 and 3.2.6 apply only to
  "sets of software programs", which it calls extremely rare. As of May 2026 the task force was
  discussing applying 3.2.6 (and 3.2.3) to software directly
  (https://www.w3.org/2026/05/14-wcag2ict-minutes.html). Re-check the current Note before calling them advisory.
- EN 301 549 (EU; chapter 11 = software, mirrors WCAG2ICT)
- Android accessibility: https://developer.android.com/guide/topics/ui/accessibility and
  Compose semantics: https://developer.android.com/develop/ui/compose/accessibility
