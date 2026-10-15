"""Static evidence from an iOS build (.app folder, or .ipa / .zip): Info.plist checks, privacy manifest, secret scan.

Stdlib only: `plistlib` reads both XML and binary plists. A finding never contains a secret's value.
"""

from __future__ import annotations

import plistlib
import zipfile
from pathlib import Path

from .secrets import scan_bytes

_TEXT_EXT = {".plist", ".json", ".strings", ".xml", ".txt", ".js"}
_MAX_FILE = 24 * 1024 * 1024


def _scanned(rel: str, executable: str | None) -> bool:
    """Files worth reading: the plist, the main binary and text-like resources."""
    return rel == "Info.plist" or rel == executable or Path(rel).suffix in _TEXT_EXT


def _executable(info_bytes: bytes | None) -> str | None:
    try:
        return plistlib.loads(info_bytes or b"").get("CFBundleExecutable")
    except (plistlib.InvalidFileException, ValueError, AttributeError):
        return None


def _read_bundle(path: Path) -> tuple[dict[str, bytes], str]:
    """The .app's files as {relative path: bytes}, reading only the ones worth scanning (others map to b"")."""
    files: dict[str, bytes] = {}
    if path.is_dir():
        paths = {p.relative_to(path).as_posix(): p for p in path.rglob("*") if p.is_file()}
        exe = _executable((path / "Info.plist").read_bytes() if (path / "Info.plist").is_file() else None)
        for rel, p in paths.items():
            files[rel] = p.read_bytes() if _scanned(rel, exe) and p.stat().st_size <= _MAX_FILE else b""
        return files, path.name
    with zipfile.ZipFile(path) as z:
        apps = sorted(
            {n.split("/")[1] for n in z.namelist() if n.startswith("Payload/") and n.count("/") >= 2}
        )
        app = next((a for a in apps if a.endswith(".app")), "")
        if not app:
            return {}, ""
        prefix = f"Payload/{app}/"
        infos = {
            i.filename[len(prefix) :]: i
            for i in z.infolist()
            if i.filename.startswith(prefix) and not i.is_dir()
        }
        exe = _executable(z.read(infos["Info.plist"]) if "Info.plist" in infos else None)
        for rel, i in infos.items():
            files[rel] = z.read(i) if _scanned(rel, exe) and i.file_size <= _MAX_FILE else b""
    return files, app


def ats_findings(info: dict) -> list[dict]:
    out: list[dict] = []
    ats = info.get("NSAppTransportSecurity")
    if not isinstance(ats, dict):
        return out
    if ats.get("NSAllowsArbitraryLoads") is True:
        out.append(
            {
                "rule": "ats-exceptions",
                "key": "arbitrary-loads",
                "subject": "NSAllowsArbitraryLoads",
                "detail": "Info.plist sets NSAllowsArbitraryLoads to true, which turns App Transport Security off app-wide.",
            }
        )
    for extra in ("NSAllowsArbitraryLoadsInWebContent", "NSAllowsArbitraryLoadsForMedia"):
        if ats.get(extra) is True:
            out.append(
                {
                    "rule": "ats-exceptions",
                    "key": extra,
                    "subject": extra,
                    "severity": "info",
                    "detail": f"Info.plist sets {extra} to true, which relaxes App Transport Security for that traffic.",
                }
            )
    domains = ats.get("NSExceptionDomains")
    if isinstance(domains, dict):
        for domain, cfg in sorted(domains.items()):
            if isinstance(cfg, dict) and cfg.get("NSExceptionAllowsInsecureHTTPLoads") is True:
                out.append(
                    {
                        "rule": "ats-exceptions",
                        "key": f"domain:{domain}",
                        "subject": domain,
                        "severity": "info",
                        "detail": f"Info.plist lets {domain} load over plain HTTP (NSExceptionAllowsInsecureHTTPLoads).",
                    }
                )
    return out


def scan_ios_app(path: str | Path) -> dict:
    """Static evidence from a .app folder or .ipa: {"ran": [...], "notes": [...], "findings": [...], "package": id}."""
    path = Path(path)
    ev: dict = {"ran": [], "notes": [], "findings": []}
    try:
        files, app = _read_bundle(path)
    except (OSError, zipfile.BadZipFile) as e:
        ev["notes"].append(f"Could not read {path.name} ({e}), so the iOS checks did not run.")
        return ev
    if not files:
        ev["notes"].append(f"No .app bundle found in {path.name}, so the iOS checks did not run.")
        return ev
    info: dict = {}
    try:
        info = plistlib.loads(files["Info.plist"])
    except (KeyError, plistlib.InvalidFileException, ValueError):
        ev["notes"].append("Info.plist could not be read, so the App Transport Security check did not run.")
    ev["ran"] = ["manifest", "static"]
    if info:
        ev["package"] = info.get("CFBundleIdentifier", "")
        ev["findings"].extend(ats_findings(info))
    if "PrivacyInfo.xcprivacy" not in files:
        ev["findings"].append(
            {
                "rule": "privacy-manifest-missing",
                "detail": f"{app or 'The app bundle'} has no PrivacyInfo.xcprivacy at its root.",
            }
        )
    seen: set[str] = set()
    for rel, data in sorted(files.items()):
        for f in scan_bytes(data, rel) if data else []:
            if f["key"] not in seen:
                seen.add(f["key"])
                ev["findings"].append(f)
    return ev
