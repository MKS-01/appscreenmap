"""Data left on the device: plain-text secrets in the app's data folder, read with adb `run-as`."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from .secrets import scan_bytes

_SECRET_KEY = re.compile(
    r"(token|secret|passw(?:or)?d|api[_-]?key|auth|session|credential|private[_-]?key)", re.IGNORECASE
)
_MAX_FILES = 60


def scan_device_data(drv, package: str) -> dict:
    """Plain-text secrets in the app's data folder. `drv.run_as(package, cmd)` returns None when it can't enter."""
    listing = drv.run_as(package, "find shared_prefs files -type f -size -256k 2>/dev/null")
    if listing is None:
        return {
            "ran": [],
            "notes": [
                (
                    "The app's data folder isn't readable (not a debuggable build, and the device isn't rooted), "
                    "so the data-at-rest check did not run."
                )
            ],
            "findings": [],
        }
    findings: list[dict] = []
    for path in [p.strip() for p in listing.splitlines() if p.strip()][:_MAX_FILES]:
        body = drv.run_as(package, f"cat '{path}'") or ""
        if path.startswith("shared_prefs/") and path.endswith(".xml"):
            try:
                root = ET.fromstring(body)
            except ET.ParseError:
                root = None
            for el in root if root is not None else []:
                name, val = el.get("name", ""), (el.text or el.get("value") or "").strip()
                if (
                    _SECRET_KEY.search(name)
                    and len(val) >= 8
                    and val.lower() not in ("true", "false", "null")
                ):
                    findings.append(
                        {
                            "rule": "secrets-at-rest",
                            "key": f"{path}:{name}",
                            "subject": f"{path} ({name})",
                            "detail": f"{path} stores '{name}' as a {len(val)}-character value in plain text.",
                        }
                    )
        for hit in scan_bytes(body.encode(errors="replace"), path):
            findings.append({**hit, "rule": "secrets-at-rest", "key": f"{path}:{hit['key']}"})
    return {"ran": ["data"], "notes": [], "findings": findings}
