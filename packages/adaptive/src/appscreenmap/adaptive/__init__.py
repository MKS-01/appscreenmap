"""Adaptive UI: the rule catalogue and the static checks of a build (manifest, Info.plist) → `audits/adaptive.json`."""

from .audit import build_audit, load_rules, write_audit
from .facts import android_facts, ios_facts, parse_manifest, parse_plist

__all__ = [
    "android_facts",
    "build_audit",
    "ios_facts",
    "load_rules",
    "parse_manifest",
    "parse_plist",
    "write_audit",
]
