---
name: wcag-mobile-rules
description: WCAG 2.2 success criteria applied to native Android apps (Views and Jetpack Compose) — what each criterion means on mobile, thresholds in dp/sp, how AppScreenMap detects it (crawler rule, viewer rule, device test, or manual), and how to fix it. Use when interpreting accessibility findings, deciding if something is a WCAG failure, writing fix guidance, or designing a new a11y check.
---

# WCAG 2.2 on Android: the rules

The machine-readable catalogue the report uses is `src/appscreenmap/wcag.py`; keep it in sync with
the reference. The full table of all 55 Level A + AA criteria (plus the AAA ones worth knowing) is in
[`reference/criteria.md`](reference/criteria.md). Read it when you need a specific criterion.
This page covers what you need every time.

## Translating web terms to native

| WCAG says | On Android |
|---|---|
| Web page | A screen: an activity, fragment, Compose destination, or dialog/bottom sheet (one AppScreenMap screen id) |
| Set of web pages | WCAG2ICT equates one app to one web page, so 2.4.1, 2.4.5, 3.2.3, 3.2.4 and 3.2.6 ("sets of software programs") don't strictly apply to a single app. Report them as advisory (`native_note` in `a11y.json`). The task force is discussing applying 3.2.6/3.2.3 directly; see `reference/criteria.md` § Sources. |
| CSS pixel | ≈ 1 dp. `px = dp × density / 160`; `run.device.density` holds the dpi. |
| Keyboard | Hardware keyboard, D-pad, and **Switch Access**: all move accessibility/input focus. |
| Accessible name | `contentDescription`, else text (merged from children in Compose), else hint (for fields) |
| Role | Widget class (`Button`, `CheckBox`, …) or Compose `Role`. A clickable `android.view.View` has none. |
| Large text (contrast) | WCAG: ≥ 18 pt or ≥ 14 pt bold (≈ 24 dp / 18.7 dp). Android tooling applies 18/14 as **sp**, which is more lenient. Say which one you used. |

## What's new in 2.2 (all apply to apps)

| SC | Level | One-line test on Android |
|---|---|---|
| 2.4.11 Focus Not Obscured (Min) | AA | A focused control is never *fully* hidden by a sticky bar, FAB, banner, or bottom sheet |
| 2.4.12 Focus Not Obscured (Enh) | AAA | …not even *partly* hidden |
| 2.4.13 Focus Appearance | AAA | Focus indicator ≥ 2 dp outline area, 3:1 change in contrast |
| 2.5.7 Dragging Movements | AA | Everything done by dragging (sliders, reorder, swipe-to-dismiss) also works with taps |
| 2.5.8 Target Size (Min) | AA | Targets ≥ 24×24 dp, **or** 24 dp circles centred on targets don't overlap (spacing exception). Also: inline text, equivalent control, essential. |
| 3.2.6 Consistent Help | A | Help/contact/chat entries sit in the same relative place on every screen that has them |
| 3.3.7 Redundant Entry | A | Don't make people retype what they already entered in the same flow; pre-fill it or offer it |
| 3.3.8 Accessible Authentication (Min) | AA | No memory, transcription, or puzzle test to log in unless paste/password managers/passkeys or another method work |
| 3.3.9 Accessible Authentication (Enh) | AAA | Same, without the object-recognition and personal-content exceptions |

4.1.1 Parsing was **removed** in 2.2. Never report it.

## Thresholds you'll need

- Contrast: text 4.5:1 (large 3:1) for 1.4.3 AA, 7:1 (large 4.5:1) for 1.4.6 AAA. Icons, control
  boundaries, and focus indicators need 3:1 for 1.4.11.
- Target size: 24 dp is the WCAG AA minimum (2.5.8) and 44 dp is AAA (2.5.5). **48 dp is Android's
  design guideline**, not a WCAG failure line. The viewer's `touch-target` rule uses 48 dp, so report
  a 30 dp target as "below Android guideline", not as a 2.5.8 failure.
- Resize text (1.4.4): works at font scale 2.0 (Android 14+ nonlinear scaling goes to 200%).
  Crawl with `--font-scale 2.0` and look for truncation, overlap, and clipped controls.
- Reflow (1.4.10): no two-direction scrolling at 320 dp width. Check with large font plus display size.

## Who checks what in AppScreenMap

| Source | Rules | Where |
|---|---|---|
| Crawler (`appscreenmap a11y`, `a11y.json`) | 2.5.8 with spacing, 2.5.3, 2.1.1, 4.1.2 role, 2.4.11, 1.3.4, 1.4.4 truncation, 1.1.1 review, 2.4.2 review, 3.2.2, 3.2.3, 3.2.4, 3.2.6, 3.3.7, 3.3.8 review, 2.5.7 review | `src/appscreenmap/a11y.py` |
| Viewer (web session) | missing label (4.1.2/1.1.1), unlabeled field (3.3.2/4.1.2), field contentDescription, 48 dp touch target (guideline), contrast estimate (1.4.3), duplicate description (2.4.6), redundant role words (best practice) | `web/src/a11y.ts` |
| Device tests (the `a11y-audit` skill) | 1.4.4 / 1.4.10 at font scale 2.0, 1.3.4 rotation, 2.1.1 / 2.4.3 / 2.4.7 with Switch Access or keyboard, TalkBack spot checks | manual with adb |
| Manual only | Media (1.2.x), 1.3.3, 1.4.1, 1.4.13, 2.2.x, 2.3.1, 2.5.1, 2.5.2, 2.5.4, 3.1.x, 3.3.1, 3.3.3, 3.3.4, 4.1.3 | checklist in `a11y-audit` |

## Wording findings

Automated output is **evidence, not a verdict**. In reports:
- "Fails 2.5.8 (AA)" only for automated rules you've confirmed by looking at the screenshot and bounds.
- "Needs review: 3.3.8" for `kind: review`.
- "Advisory for native apps" when `native_note` is set.
- "Below Android guideline (48 dp)" for the viewer's touch-target hits that are ≥ 24 dp.
