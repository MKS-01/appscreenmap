"""Static evidence from an APK: the manifest checks (via aapt2), the secret scan and the dex code checks."""

from __future__ import annotations

import subprocess
from pathlib import Path

from appscreenmap.drivers.apkinfo import find_aapt2

from .code import scan_code
from .manifest import manifest_findings, parse_manifest, parse_network_config, resource_file
from .secrets import scan_secrets


def _aapt(aapt2: str, *args: str) -> str:
    try:
        return subprocess.run(
            [aapt2, "dump", *args], check=False, capture_output=True, text=True, timeout=120
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


def scan_apk(apk: str | Path) -> dict:
    """Static evidence from an APK: {"ran": [...], "notes": [...], "findings": [...]}."""
    ev: dict = {"ran": ["static"], "notes": [], "findings": scan_secrets(apk) + scan_code(apk)}
    aapt2 = find_aapt2()
    if not aapt2:
        ev["notes"].append(
            "aapt2 not found, so the manifest checks did not run (install Android build-tools)."
        )
        return ev
    tree = _aapt(aapt2, "xmltree", "--file", "AndroidManifest.xml", str(apk))
    if not tree:
        ev["notes"].append("aapt2 could not read the manifest, so the manifest checks did not run.")
        return ev
    manifest = parse_manifest(tree)
    nsc = None
    if manifest.network_config:
        path = resource_file(_aapt(aapt2, "resources", str(apk)), manifest.network_config)
        if path:
            nsc = parse_network_config(_aapt(aapt2, "xmltree", "--file", path, str(apk)))
        else:
            ev["notes"].append("The network security config could not be located, so it was not read.")
    ev["ran"].insert(0, "manifest")
    ev["findings"] = manifest_findings(manifest, nsc) + ev["findings"]
    ev["package"] = manifest.package
    return ev
