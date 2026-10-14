"""Store readiness: does a build meet Google Play's and the App Store's SDK rules, now and in the next 12 months?

Reads the build's target / compile / minimum SDK (APK manifest via aapt2, iOS Info.plist), measures it against the dated
rules in `requirements.json` and writes `audits/store.json`. Stdlib only.
"""

from .audit import FORM_FACTORS, HORIZON_DAYS, build_audit, load_requirements, write_audit
from .facts import android_facts, ios_facts, parse_android_sdk, parse_ios_plist

__all__ = [
    "FORM_FACTORS",
    "HORIZON_DAYS",
    "android_facts",
    "build_audit",
    "ios_facts",
    "load_requirements",
    "parse_android_sdk",
    "parse_ios_plist",
    "write_audit",
]
