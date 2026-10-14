"""Store readiness: a build's SDK levels against the dated Google Play / App Store rules → `audits/store.json`.

The rules live in `requirements.json`. The audit always looks `HORIZON_DAYS` ahead, so a requirement that takes effect
within the next year shows up as "upcoming" with its date before it blocks anyone.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

HORIZON_DAYS = 365
FORM_FACTORS = ("phone", "wear", "tv", "automotive", "xr")
SCORE_NOTE = "100 minus 20 per error, 8 per warning"
REQUIREMENTS = Path(__file__).with_name("requirements.json")
ANDROID_DEV = "https://developer.android.com/google/play/requirements/target-sdk"


def load_requirements() -> dict:
    return json.loads(REQUIREMENTS.read_text())


def _d(s: str) -> date:
    return date.fromisoformat(s)


def _days(n: int) -> str:
    return (
        "today"
        if n == 0
        else f"in {n} day{'s' if n != 1 else ''}"
        if n > 0
        else f"{-n} day{'s' if n != -1 else ''} ago"
    )


def _finding(fid, severity, title, detail, fix, platform, category, refs, requirement, due=None) -> dict:
    f = {
        "id": fid,
        "severity": severity,
        "title": title,
        "detail": detail,
        "fix": fix,
        "platform": platform,
        "category": category,
        "refs": refs,
        "requirement": requirement,
    }
    if (
        due and requirement != "met"
    ):  # a met rule's date is history; on the timeline it only stretches the axis
        f["due"] = due
    return f


def android_findings(facts: dict, req: dict, today: date, form_factor: str = "phone") -> list[dict]:
    a = req["android"]
    refs = a["refs"]
    tiers = a["tiers"][form_factor]
    target, compile_sdk = facts.get("target_sdk"), facts.get("compile_sdk")
    out: list[dict] = []
    if target is None:
        return [
            _finding(
                "store::target-unknown",
                "warning",
                "Target SDK could not be read",
                "The manifest has no targetSdkVersion, or it could not be read. Play treats a missing one as the "
                "minimum API level, which fails the target rule.",
                "Set targetSdk in the app module's build.gradle(.kts) defaultConfig.",
                "android",
                "Target SDK",
                refs,
                "not_checked",
            )
        ]
    for t in tiers:
        start, ext = _d(t["from"]), _d(t["extension_until"]) if t.get("extension_until") else None
        days = (start - today).days
        label = f"API {t['api']}"
        due = t["from"]
        if start > today + timedelta(days=HORIZON_DAYS):
            continue
        if target >= t["api"]:
            out.append(
                _finding(
                    f"store::target-{t['api']}",
                    "info",
                    f"Targets {label}: meets the Play rule",
                    f"targetSdkVersion is {target}; Play requires {label} for new apps and updates "
                    f"({'from' if days <= 0 else 'due'} {t['from']}).",
                    "Nothing to do.",
                    "android",
                    "Target SDK",
                    refs,
                    "met",
                    due,
                )
            )
        elif days > 0:
            out.append(
                _finding(
                    f"store::target-{t['api']}",
                    "warning",
                    f"Must target {label} by {t['from']}",
                    f"targetSdkVersion is {target}. From {t['from']} ({_days(days)}) Play rejects new apps and updates "
                    f"below {label} ({form_factor}).",
                    f"Raise targetSdk to {t['api']}, then test the behaviour changes of each level in between "
                    "(edge-to-edge is enforced at 35; large-screen orientation/resizability limits are ignored and "
                    "predictive back is on by default at 36).",
                    "android",
                    "Target SDK",
                    refs,
                    "upcoming",
                    due,
                )
            )
        elif ext and today < ext:
            out.append(
                _finding(
                    f"store::target-{t['api']}",
                    "error",
                    f"Targets API {target}: Play updates need {label}",
                    f"targetSdkVersion is {target}. Since {t['from']} Play rejects updates below {label} ({form_factor}). "
                    f"Only a Play Console extension request keeps updates open, until {t['extension_until']} "
                    f"({_days((ext - today).days)}).",
                    f"Raise targetSdk to {t['api']} and ship before {t['extension_until']}, or request the extension "
                    "in Play Console now.",
                    "android",
                    "Target SDK",
                    refs,
                    "due",
                    t["extension_until"],
                )
            )
        else:
            out.append(
                _finding(
                    f"store::target-{t['api']}",
                    "error",
                    f"Targets API {target}: blocked from Play updates",
                    f"targetSdkVersion is {target}. Play has required {label} since {t['from']}"
                    + (f" (extensions ended {t['extension_until']})" if ext else "")
                    + f" ({form_factor}).",
                    f"Raise targetSdk to {t['api']} and rebuild.",
                    "android",
                    "Target SDK",
                    refs,
                    "blocked",
                    due,
                )
            )
    # Availability to new users on newer Android versions.
    floor = a["existing_app_min_api"]
    if target < floor:
        out.append(
            _finding(
                "store::availability",
                "warning",
                f"Hidden from new users on Android above API {target}",
                f"Apps targeting below API {floor} stay available to new users only on devices running Android "
                f"{target} or lower.",
                f"Raise targetSdk to at least {floor}.",
                "android",
                "Target SDK",
                refs,
                "due",
            )
        )
    # Build (compile) SDK.
    required = max((t["api"] for t in tiers if _d(t["from"]) <= today), default=None)
    soonest = max(
        (t["api"] for t in tiers if _d(t["from"]) <= today + timedelta(days=HORIZON_DAYS)), default=None
    )
    if compile_sdk is None:
        out.append(
            _finding(
                "store::compile-unknown",
                "info",
                "Build SDK (compileSdk) not recorded in the manifest",
                "The APK carries no compileSdkVersion, so which SDK it was compiled against can't be checked here.",
                "Check compileSdk in build.gradle(.kts); it must be at least targetSdk.",
                "android",
                "Build SDK",
                [
                    {
                        "title": "Set compileSdk",
                        "url": "https://developer.android.com/build/gradle-tips#configure-compile-sdk",
                        "publisher": "Android Developers",
                    }
                ],
                "not_checked",
            )
        )
    else:
        cref = [
            {
                "title": "compileSdk",
                "url": "https://developer.android.com/reference/tools/gradle-api/current/com/android/build/api/dsl/CommonExtension",
                "publisher": "Android Developers",
            }
        ]
        if compile_sdk < target:
            out.append(
                _finding(
                    "store::compile-below-target",
                    "warning",
                    f"compileSdk {compile_sdk} is below targetSdk {target}",
                    "The app targets behaviour of an API it was not compiled against. AGP warns and the new platform "
                    "APIs and lint checks for that level were not available to the build.",
                    f"Set compileSdk to at least {target}.",
                    "android",
                    "Build SDK",
                    cref,
                    "due",
                )
            )
        elif soonest and compile_sdk < soonest:
            out.append(
                _finding(
                    "store::compile-behind",
                    "warning" if required and compile_sdk < required else "info",
                    f"compileSdk {compile_sdk} is behind the API {soonest} the stores need",
                    f"To target API {soonest} the build must compile against SDK {soonest} or later.",
                    f"Set compileSdk to {soonest} (and update AGP / androidx if they refuse it).",
                    "android",
                    "Build SDK",
                    cref,
                    "due" if required and compile_sdk < required else "upcoming",
                )
            )
        else:
            out.append(
                _finding(
                    "store::compile-ok",
                    "info",
                    f"compileSdk {compile_sdk}: current",
                    f"Compiled against SDK {compile_sdk} (target {target}).",
                    "Nothing to do.",
                    "android",
                    "Build SDK",
                    cref,
                    "met",
                )
            )
    out.append(
        _finding(
            "store::next",
            "info",
            "Beyond the published deadlines",
            a["expected"],
            "Re-run this audit after each Play announcement, and refresh requirements.json (store-requirements skill).",
            "android",
            "Upcoming",
            refs,
            "upcoming",
        )
    )
    return out


def ios_findings(facts: dict, req: dict, today: date) -> list[dict]:
    i = req["ios"]
    refs = i["refs"]
    out: list[dict] = []
    sdk, dep = i["sdk"], i["deployment"]
    major = facts.get("sdk_major")
    if major is None:
        out.append(
            _finding(
                "store::sdk-unknown",
                "warning",
                "Build SDK could not be read",
                "No DTSDKName / DTPlatformVersion in Info.plist.",
                "Build and archive with Xcode, then scan the archive.",
                "ios",
                "Build SDK",
                refs,
                "not_checked",
            )
        )
    else:
        start = _d(sdk["from"])
        days = (start - today).days
        name = facts.get("sdk_name") or f"SDK {major}"
        xcode = f" (Xcode {facts['xcode']})" if facts.get("xcode") else ""
        if major >= sdk["min_major"]:
            out.append(
                _finding(
                    "store::sdk",
                    "info",
                    f"Built with {name}{xcode}: meets the App Store rule",
                    f"App Store Connect needs apps {sdk['text']} ({'since' if days <= 0 else 'from'} {sdk['from']}).",
                    "Nothing to do.",
                    "ios",
                    "Build SDK",
                    refs,
                    "met",
                    sdk["from"],
                )
            )
        elif days > 0:
            out.append(
                _finding(
                    "store::sdk",
                    "warning",
                    f"Build with the iOS {sdk['min_major']} SDK by {sdk['from']}",
                    f"Built with {name}{xcode}. From {sdk['from']} ({_days(days)}) uploads must be {sdk['text']}.",
                    f"Archive with Xcode {sdk['min_major']} or later (CI image too).",
                    "ios",
                    "Build SDK",
                    refs,
                    "upcoming",
                    sdk["from"],
                )
            )
        else:
            out.append(
                _finding(
                    "store::sdk",
                    "error",
                    f"Built with {name}{xcode}: App Store Connect rejects it",
                    f"Since {sdk['from']} uploads must be {sdk['text']}.",
                    f"Archive with Xcode {sdk['min_major']} or later (check the CI image and macOS version it runs).",
                    "ios",
                    "Build SDK",
                    refs,
                    "blocked",
                    sdk["from"],
                )
            )
        if facts.get("simulator_build"):
            out.append(
                _finding(
                    "store::simulator-build",
                    "info",
                    "This is a simulator build",
                    "Simulator builds can't be uploaded; the SDK level is read from the simulator SDK.",
                    "Scan the device archive (.ipa) before submitting.",
                    "ios",
                    "Build SDK",
                    refs,
                    "not_checked",
                )
            )
    dmajor = facts.get("deployment_major")
    if dmajor is None:
        out.append(
            _finding(
                "store::deployment-unknown",
                "info",
                "Deployment target not found",
                "Info.plist has no MinimumOSVersion.",
                "Check IPHONEOS_DEPLOYMENT_TARGET in the Xcode project.",
                "ios",
                "Deployment target",
                refs,
                "not_checked",
            )
        )
    else:
        start = _d(dep["from"])
        days = (start - today).days
        if dmajor >= dep["min_major"]:
            out.append(
                _finding(
                    "store::deployment",
                    "info",
                    f"Deployment target iOS {facts['deployment_target']}: meets the rule",
                    f"App Store Connect needs iOS {dep['min_major']} or later ({'since' if days <= 0 else 'from'} {dep['from']}).",
                    "Nothing to do.",
                    "ios",
                    "Deployment target",
                    refs,
                    "met",
                    dep["from"],
                )
            )
        else:
            out.append(
                _finding(
                    "store::deployment",
                    "warning" if days > 0 else "error",
                    f"Deployment target iOS {facts['deployment_target']} is below iOS {dep['min_major']}",
                    f"Uploads must target iOS {dep['min_major']} or later {'from' if days > 0 else 'since'} {dep['from']}.",
                    f"Raise IPHONEOS_DEPLOYMENT_TARGET to {dep['min_major']} or later.",
                    "ios",
                    "Deployment target",
                    refs,
                    "upcoming" if days > 0 else "blocked",
                    dep["from"],
                )
            )
    out.append(
        _finding(
            "store::next",
            "info",
            "Beyond the published deadlines",
            i["expected"],
            "Re-run this audit after each Apple announcement, and refresh requirements.json (store-requirements skill).",
            "ios",
            "Upcoming",
            refs,
            "upcoming",
        )
    )
    return out


def build_audit(facts: dict, today: date | None = None, form_factor: str = "phone") -> dict:
    today = today or datetime.now(UTC).date()
    req = load_requirements()
    ios = facts["platform"] == "ios"
    unreadable = facts.get("notes") and not any(k in facts for k in ("target_sdk", "sdk_name"))
    if unreadable:
        findings = []
    elif ios:
        findings = ios_findings(facts, req, today)
    else:
        findings = android_findings(facts, req, today, form_factor)
    notes = facts.get("notes", [])
    order = {"error": 0, "warning": 1, "info": 2}
    findings.sort(key=lambda f: (order[f["severity"]], f["id"]))
    n = {s: sum(1 for f in findings if f["severity"] == s) for s in order}
    score = max(0, 100 - 20 * n["error"] - 8 * n["warning"])  # info notes (met, upcoming) cost nothing
    status = "not_run" if not findings else "fail" if n["error"] else "warn" if n["warning"] else "pass"
    label = {
        "fail": "Blocked from store updates",
        "warn": "Action needed within the year",
        "pass": "Compatible",
    }.get(status)
    if ios:
        metrics = [
            {"label": "build SDK", "value": facts.get("sdk_name") or "unknown"},
            {"label": "Xcode", "value": facts.get("xcode") or "unknown"},
            {"label": "deployment target", "value": facts.get("deployment_target") or "unknown"},
        ]
    else:
        metrics = [
            {"label": "targetSdk", "value": facts.get("target_sdk", "unknown")},
            {"label": "compileSdk", "value": facts.get("compile_sdk") or "unknown"},
            {"label": "minSdk", "value": facts.get("min_sdk") or "unknown"},
            {"label": "form factor", "value": form_factor},
        ]
    metrics += [{"label": "note", "value": t, "tone": "warn"} for t in notes]
    metrics.append(
        {
            "label": "rules checked",
            "value": req["checked"],
            "hint": f"requirements.json; looks {HORIZON_DAYS} days ahead",
        }
    )
    plat = "ios" if ios else "android"
    refs = req[plat]["refs"]
    return {
        "schema": 1,
        "audit": "store",
        "title": "Store readiness",
        "tool": "appscreenmap store (" + ("Info.plist" if ios else "aapt2") + ")",
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "source": "run",
        "status": status,
        **({"status_label": label} if label else {}),
        "score": score if findings else None,
        "score_note": SCORE_NOTE,
        "summary": f"{n['error']} blocking, {n['warning']} to fix within {HORIZON_DAYS} days; rules as of {req['checked']}."
        if findings
        else "; ".join(notes) or "Nothing could be read.",
        "metrics": metrics,
        "charts": [],
        "findings": findings,
        "refs": refs,
    }


def write_audit(run: Path, audit: dict) -> None:
    d = Path(run) / "audits"
    d.mkdir(exist_ok=True)
    (d / "store.json").write_text(json.dumps(audit, indent=1) + "\n")
