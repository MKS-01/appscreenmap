"""Security audit scanner: APK, on-device and dynamic evidence in, `audits/security.json` out.

Stdlib only and fast, so an agent can run it after every crawl: the manifest comes from one `aapt2 dump xmltree`
call, hard-coded secrets from regexes over the raw bytes of the APK's dex files and resources (no decompiling),
data left on the device from the app's data folder over adb, and dynamic findings from the observation-only Frida
hook in `hooks/`. Rules, severities, fixes and official sources come from `rules.json`. A finding never contains a
secret's value, only where it is and a fingerprint. For apps you own or are authorised to test.
"""

from .apk import scan_apk
from .audit import build_audit, load_evidence, write_audit
from .device_data import scan_device_data
from .frida import HOOK, parse_frida_log
from .manifest import manifest_findings, parse_manifest, parse_network_config, resource_file
from .secrets import scan_bytes, scan_secrets

__all__ = [
    "HOOK",
    "build_audit",
    "load_evidence",
    "manifest_findings",
    "parse_frida_log",
    "parse_manifest",
    "parse_network_config",
    "resource_file",
    "scan_apk",
    "scan_bytes",
    "scan_device_data",
    "scan_secrets",
    "write_audit",
]
