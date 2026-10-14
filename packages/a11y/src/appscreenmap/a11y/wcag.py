"""WCAG 2.2 success criteria catalogue and how AppScreenMap covers each one on Android.

Human-readable version with fixes: .claude/skills/wcag-mobile-rules/reference/criteria.md.
Keep the two in sync.
"""

from __future__ import annotations

from dataclasses import dataclass

PRINCIPLES = {"1": "Perceivable", "2": "Operable", "3": "Understandable", "4": "Robust"}

# (sc, name, level). All Level A and AA criteria of WCAG 2.2 (4.1.1 Parsing is obsolete and removed),
# plus the AAA criteria most relevant to apps.
_CRITERIA = [
    ("1.1.1", "Non-text Content", "A"),
    ("1.2.1", "Audio-only and Video-only (Prerecorded)", "A"),
    ("1.2.2", "Captions (Prerecorded)", "A"),
    ("1.2.3", "Audio Description or Media Alternative (Prerecorded)", "A"),
    ("1.2.4", "Captions (Live)", "AA"),
    ("1.2.5", "Audio Description (Prerecorded)", "AA"),
    ("1.3.1", "Info and Relationships", "A"),
    ("1.3.2", "Meaningful Sequence", "A"),
    ("1.3.3", "Sensory Characteristics", "A"),
    ("1.3.4", "Orientation", "AA"),
    ("1.3.5", "Identify Input Purpose", "AA"),
    ("1.4.1", "Use of Color", "A"),
    ("1.4.2", "Audio Control", "A"),
    ("1.4.3", "Contrast (Minimum)", "AA"),
    ("1.4.4", "Resize Text", "AA"),
    ("1.4.5", "Images of Text", "AA"),
    ("1.4.6", "Contrast (Enhanced)", "AAA"),
    ("1.4.10", "Reflow", "AA"),
    ("1.4.11", "Non-text Contrast", "AA"),
    ("1.4.12", "Text Spacing", "AA"),
    ("1.4.13", "Content on Hover or Focus", "AA"),
    ("2.1.1", "Keyboard", "A"),
    ("2.1.2", "No Keyboard Trap", "A"),
    ("2.1.4", "Character Key Shortcuts", "A"),
    ("2.2.1", "Timing Adjustable", "A"),
    ("2.2.2", "Pause, Stop, Hide", "A"),
    ("2.3.1", "Three Flashes or Below Threshold", "A"),
    ("2.4.1", "Bypass Blocks", "A"),
    ("2.4.2", "Page Titled", "A"),
    ("2.4.3", "Focus Order", "A"),
    ("2.4.4", "Link Purpose (In Context)", "A"),
    ("2.4.5", "Multiple Ways", "AA"),
    ("2.4.6", "Headings and Labels", "AA"),
    ("2.4.7", "Focus Visible", "AA"),
    ("2.4.11", "Focus Not Obscured (Minimum)", "AA"),
    ("2.4.12", "Focus Not Obscured (Enhanced)", "AAA"),
    ("2.4.13", "Focus Appearance", "AAA"),
    ("2.5.1", "Pointer Gestures", "A"),
    ("2.5.2", "Pointer Cancellation", "A"),
    ("2.5.3", "Label in Name", "A"),
    ("2.5.4", "Motion Actuation", "A"),
    ("2.5.5", "Target Size (Enhanced)", "AAA"),
    ("2.5.6", "Concurrent Input Mechanisms", "AAA"),
    ("2.5.7", "Dragging Movements", "AA"),
    ("2.5.8", "Target Size (Minimum)", "AA"),
    ("3.1.1", "Language of Page", "A"),
    ("3.1.2", "Language of Parts", "AA"),
    ("3.2.1", "On Focus", "A"),
    ("3.2.2", "On Input", "A"),
    ("3.2.3", "Consistent Navigation", "AA"),
    ("3.2.4", "Consistent Identification", "AA"),
    ("3.2.6", "Consistent Help", "A"),
    ("3.3.1", "Error Identification", "A"),
    ("3.3.2", "Labels or Instructions", "A"),
    ("3.3.3", "Error Suggestion", "AA"),
    ("3.3.4", "Error Prevention (Legal, Financial, Data)", "AA"),
    ("3.3.7", "Redundant Entry", "A"),
    ("3.3.8", "Accessible Authentication (Minimum)", "AA"),
    ("3.3.9", "Accessible Authentication (Enhanced)", "AAA"),
    ("4.1.2", "Name, Role, Value", "A"),
    ("4.1.3", "Status Messages", "AA"),
]

NEW_IN_22 = {"2.4.11", "2.4.12", "2.4.13", "2.5.7", "2.5.8", "3.2.6", "3.3.7", "3.3.8", "3.3.9"}

# WCAG2ICT applies these to "sets of software programs", which a single app is not.
NATIVE_ADVISORY = {"2.4.1", "2.4.5", "3.2.3", "3.2.4", "3.2.6"}

# Criteria with an adb/device test in the a11y-audit skill.
DEVICE_TESTS = {"1.3.2", "1.3.4", "1.4.4", "1.4.10", "2.1.1", "2.1.2", "2.4.3", "2.4.7", "2.4.11", "3.2.1"}

# The web viewer's per-screen rules (apps/viewer/src/a11y.ts) and the criterion each maps to.
# sc None = a platform guideline / best practice, not a WCAG requirement.
VIEWER_RULES: dict[str, dict] = {
    "label-missing": {"sc": "4.1.2", "title": "Missing label", "severity": "error"},
    "field-unlabeled": {"sc": "3.3.2", "title": "Unlabeled text field", "severity": "error"},
    "field-desc": {"sc": "4.1.2", "title": "Text field uses contentDescription", "severity": "warning"},
    "contrast": {"sc": "1.4.3", "title": "Low text contrast", "severity": "warning"},
    "duplicate-label": {"sc": "2.4.6", "title": "Duplicate description", "severity": "info"},
    "touch-target": {
        "sc": None,
        "title": "Touch target below Android's 48 dp guideline",
        "severity": "warning",
    },
    "redundant-desc": {"sc": None, "title": "Role word in description", "severity": "info"},
}


@dataclass(frozen=True)
class Criterion:
    sc: str
    name: str
    level: str

    @property
    def principle(self) -> str:
        return PRINCIPLES[self.sc.split(".")[0]]

    @property
    def new_in_22(self) -> bool:
        return self.sc in NEW_IN_22

    @property
    def native_advisory(self) -> bool:
        return self.sc in NATIVE_ADVISORY

    @property
    def url(self) -> str:
        slug = self.name.lower()
        for ch in "(),":
            slug = slug.replace(ch, "")
        return "https://www.w3.org/WAI/WCAG22/Understanding/" + "-".join(slug.split())


CRITERIA: list[Criterion] = [Criterion(*c) for c in _CRITERIA]
BY_SC: dict[str, Criterion] = {c.sc: c for c in CRITERIA}
LEVEL_ORDER = {"A": 0, "AA": 1, "AAA": 2}


def sc_key(sc: str) -> list[int]:
    return [int(p) for p in sc.split(".")]


def criteria_up_to(level: str) -> list[Criterion]:
    return [c for c in CRITERIA if LEVEL_ORDER[c.level] <= LEVEL_ORDER[level]]
