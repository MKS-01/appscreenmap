"""The device read and the APK fingerprints → `audits/stack.json`: the Insights audit shape plus a `facts` block."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

PAGE_SIZES = {
    "title": "Support 16 KB page sizes",
    "url": "https://developer.android.com/guide/practices/page-sizes",
    "publisher": "Android Developers",
}
ABI_64 = {
    "title": "Support 64-bit architectures",
    "url": "https://developer.android.com/google/play/requirements/64-bit",
    "publisher": "Android Developers",
}


def _finding(
    fid: str, severity: str, title: str, detail: str, fix: str, category: str, refs: list, platform="android"
) -> dict:
    return {
        "id": fid,
        "severity": severity,
        "title": title,
        "detail": detail,
        "fix": fix,
        "platform": platform,
        "category": category,
        "refs": refs,
    }


def findings(facts: dict) -> list[dict]:
    out = []
    bad = [r["path"] for r in facts.get("page_16k", []) if not r["elf_ok"] or r["zip_ok"] is False]
    if bad:
        out.append(
            _finding(
                "stack::page-16k",
                "error" if (facts.get("target_sdk") or 0) >= 35 else "warning",
                "Native libraries are not 16 KB aligned",
                f"{len(bad)} 64-bit native librar{'y is' if len(bad) == 1 else 'ies are'} not aligned for 16 KB pages "
                f"({', '.join(bad[:5])}{', …' if len(bad) > 5 else ''}). Google Play requires 16 KB support for apps "
                "targeting Android 15 or higher.",
                "Build with AGP 8.5.1+ and NDK r28+ (or link with -Wl,-z,max-page-size=16384), update prebuilt "
                "libraries that ship unaligned, and keep uncompressed libraries zip-aligned to 16 KB.",
                "Native code",
                [PAGE_SIZES],
            )
        )
    abis = set(facts.get("abis", []))
    if abis & {"armeabi-v7a", "x86"} and not abis & {"arm64-v8a", "x86_64"}:
        out.append(
            _finding(
                "stack::no-64-bit",
                "error",
                "Native code has no 64-bit version",
                f"The app ships native libraries for {', '.join(sorted(abis))} only. Google Play requires a 64-bit "
                "version of every native library.",
                "Add arm64-v8a (and x86_64 for emulators) to the build's ABI filters.",
                "Native code",
                [ABI_64],
            )
        )
    if facts.get("debuggable"):
        out.append(
            _finding(
                "stack::debuggable",
                "info",
                "Debuggable build",
                "The installed build is debuggable, so it is not the build users get: R8, resource shrinking and "
                "release-only libraries may differ.",
                "Scan the release build too before relying on library and size results.",
                "Build",
                [],
            )
        )
    return out


def _known(v):
    return v if v is not None else "unknown"


def build_audit(package: str, device: dict, fp: dict, tool: str) -> dict:
    """`device` from `parse_dumpsys_package`, `fp` from `fingerprint`. The device's SDK levels win over the
    manifest's (they are what the system installed); compileSdk only exists in the manifest."""
    facts = {
        "platform": "android",
        "package": package,
        "version": device.get("version"),
        "version_code": device.get("version_code"),
        "min_sdk": device.get("min_sdk", fp.get("manifest_min_sdk")),
        "target_sdk": device.get("target_sdk", fp.get("manifest_target_sdk")),
        "compile_sdk": fp.get("compile_sdk"),
        "debuggable": device.get("debuggable"),
        "installer": device.get("installer"),
        "signing_version": device.get("signing_version"),
        "primary_abi": device.get("primary_abi"),
        **{k: v for k, v in fp.items() if not k.startswith("manifest_") and k != "compile_sdk"},
    }
    found = findings(facts)
    order = {"error": 0, "warning": 1, "info": 2}
    found.sort(key=lambda f: (order[f["severity"]], f["id"]))
    n = {s: sum(1 for f in found if f["severity"] == s) for s in order}
    libs = len(fp["native_libs"]) + len(fp["components"])
    return {
        "schema": 1,
        "audit": "stack",
        "title": "App stack",
        "tool": tool,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "source": "run",
        "status": "fail" if n["error"] else "warn" if n["warning"] else "info",
        "score": None,
        "summary": fp["stack"]["summary"],
        "metrics": [
            {"label": "minSdk", "value": _known(facts["min_sdk"])},
            {"label": "targetSdk", "value": _known(facts["target_sdk"])},
            {"label": "compileSdk", "value": _known(facts["compile_sdk"])},
            {"label": "ABIs", "value": len(fp["abis"]), "hint": ", ".join(fp["abis"]) or "no native code"},
            {"label": "known libraries", "value": libs, "hint": "named by LibChecker-Rules"},
            {
                "label": "storage",
                "value": len(fp["storage"]),
                "hint": f"{sum(1 for s in fp['storage'] if s['encrypted'])} encrypted",
            },
        ],
        "charts": [],
        "findings": found,
        "refs": [PAGE_SIZES, ABI_64],
        "facts": facts,
    }


def ios_findings(facts: dict) -> list[dict]:
    out = []
    if facts.get("encrypted"):
        out.append(
            _finding(
                "stack::encrypted",
                "info",
                "Encrypted App Store build",
                "The main executable is FairPlay-encrypted, so its code was not read: framework, language and "
                "storage results come from the bundle's files and linked libraries only.",
                "Scan a simulator or development build of the same version for the full picture.",
                "Build",
                [],
                "ios",
            )
        )
    if facts.get("debug_build"):
        out.append(
            _finding(
                "stack::debuggable",
                "info",
                "Debug build",
                f"The installed build is a debug build (its code is in {facts.get('executable')}.debug.dylib), so it "
                "is not the build users get: optimisation and release-only settings may differ.",
                "Scan a Release build too before relying on these results.",
                "Build",
                [],
                "ios",
            )
        )
    return out


def build_ios_audit(fp: dict, tool: str, data_container: str | None = None) -> dict:
    """`fp` from `ios.fingerprint_app`. `data_container`: the app's data folder on this Mac at scan time."""
    facts = {
        "platform": "ios",
        "package": fp.get("bundle_id"),
        **{k: v for k, v in fp.items() if k != "bundle_id"},
        "data_container": data_container,
    }
    found = sorted(ios_findings(facts), key=lambda f: f["id"])
    return {
        "schema": 1,
        "audit": "stack",
        "title": "App stack",
        "tool": tool,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "source": "run",
        "status": "info",
        "score": None,
        "summary": fp["stack"]["summary"],
        "metrics": [
            {
                "label": "deployment target",
                "value": _known(fp.get("deployment_target")),
                "hint": "MinimumOSVersion",
            },
            {"label": "build SDK", "value": _known(fp.get("build_sdk") or fp.get("sdk")), "hint": "iOS SDK"},
            {"label": "Xcode", "value": _known(fp.get("xcode"))},
            {
                "label": "frameworks",
                "value": len(fp["frameworks"]) + len(fp["linked"]),
                "hint": f"{len(fp['frameworks'])} embedded, {len(fp['linked'])} system",
            },
            {
                "label": "storage",
                "value": len(fp["storage"]),
                "hint": f"{sum(1 for s in fp['storage'] if s['encrypted'])} encrypted",
            },
        ],
        "charts": [],
        "findings": found,
        "refs": [],
        "facts": facts,
    }


def write_audit(run: Path, audit: dict) -> Path:
    d = Path(run) / "audits"
    d.mkdir(exist_ok=True)
    path = d / "stack.json"
    path.write_text(json.dumps(audit, indent=1, ensure_ascii=False) + "\n")
    return path
