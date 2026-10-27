"""What an installed app is built with: the device read and the APK fingerprints → `audits/stack.json`."""

from .apk import fingerprint, parse_components
from .audit import build_audit, build_ios_audit, write_audit
from .dumpsys import parse_dumpsys_package
from .ios import fingerprint_app

# In the canvas: apks/ (base + splits as pulled) and dumpsys-package.txt on Android, app/<Name>.app on iOS; the last scan.
BUILD_DIR = "build"

__all__ = [
    "BUILD_DIR",
    "build_audit",
    "build_ios_audit",
    "fingerprint",
    "fingerprint_app",
    "parse_components",
    "parse_dumpsys_package",
    "write_audit",
]
