"""Official sources the built-in audits cite. Mirrors the same ids in `apps/viewer/src/insights/sources.ts`;
update both when a platform publishes its yearly changes."""

from __future__ import annotations

CHECKED = "2026-10-13"

SOURCES: dict[str, dict] = {
    "wcag22": {
        "title": "Web Content Accessibility Guidelines (WCAG) 2.2",
        "url": "https://www.w3.org/TR/WCAG22/",
        "publisher": "W3C",
        "date": CHECKED,
    },
    "androidA11y": {
        "title": "Make apps more accessible",
        "url": "https://developer.android.com/guide/topics/ui/accessibility/apps",
        "publisher": "Android Developers",
        "date": CHECKED,
    },
    "androidVitals": {
        "title": "Android vitals",
        "url": "https://developer.android.com/topic/performance/vitals",
        "publisher": "Android Developers",
        "date": CHECKED,
    },
}


def refs(*ids: str) -> list[dict]:
    return [dict(SOURCES[i]) for i in ids]
