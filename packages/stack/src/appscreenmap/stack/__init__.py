"""What an installed app is built with: the device read and the APK fingerprints → `audits/stack.json`."""

from .apk import fingerprint, parse_components
from .audit import build_audit, write_audit
from .dumpsys import parse_dumpsys_package

# In the canvas: apks/ (base + splits as pulled) and dumpsys-package.txt, from the last scan.
BUILD_DIR = "build"

__all__ = [
    "BUILD_DIR",
    "build_audit",
    "fingerprint",
    "parse_components",
    "parse_dumpsys_package",
    "write_audit",
]
