"""Security audit scanner: APK, on-device and dynamic evidence in, `audits/security.json` out.

Stdlib only and fast, so an agent can run it after every crawl: the manifest comes from one `aapt2 dump xmltree`
call, hard-coded secrets and risky API references (WebView bridge, weak crypto, sticky broadcasts, …) from byte
matches over the APK's dex files and resources (no decompiling), iOS builds from Info.plist and the bundle's files,
data left on the device from the app's data folder over adb, and dynamic findings from the observation-only Frida
hook and mitmproxy addon in `hooks/` (`network.py` runs the proxy during a crawl). Rules, severities, fixes and
official sources come from `rules.json`. A finding never contains a secret's value, only where it is and a
fingerprint. For apps you own or are authorised to test.
"""

from .apk import scan_apk
from .audit import build_audit, load_evidence, write_audit
from .code import scan_code, scan_dex_bytes
from .device_data import scan_device_data
from .frida import HOOK, parse_frida_log
from .ios import ats_findings, scan_ios_app
from .manifest import manifest_findings, parse_manifest, parse_network_config, resource_file
from .secrets import scan_bytes, scan_secrets

__all__ = [
    "HOOK",
    "ats_findings",
    "build_audit",
    "load_evidence",
    "manifest_findings",
    "parse_frida_log",
    "parse_manifest",
    "parse_network_config",
    "resource_file",
    "scan_apk",
    "scan_bytes",
    "scan_code",
    "scan_device_data",
    "scan_dex_bytes",
    "scan_ios_app",
    "scan_secrets",
    "write_audit",
]
