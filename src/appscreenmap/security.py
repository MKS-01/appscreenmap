"""Security audit scanner: APK, on-device and dynamic evidence in, `audits/security.json` out.

Stdlib only and fast, so an agent can run it after every crawl: the manifest comes from one `aapt2 dump xmltree`
call, hard-coded secrets from regexes over the raw bytes of the APK's dex files and resources (no decompiling),
data left on the device from the app's data folder over adb, and dynamic findings from the observation-only Frida
hooks in `.claude/skills/security-audit/scripts/`. Rules, severities, fixes and official sources come from
`security_rules.json`. A finding never contains a secret's value, only where it is and a fingerprint.
For apps you own or are authorised to test.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from .apkinfo import find_aapt2
from .security_rules import load_rules

COMPONENT_TAGS = ("activity", "activity-alias", "service", "receiver", "provider")
CATEGORY_LABEL = {
    "manifest": "Manifest",
    "static": "Static scan",
    "dynamic": "Dynamic run",
    "data": "Data on device",
}
SCORE_NOTE = "100 minus 20 per error, 8 per warning, 2 per info"


# ── manifest ─────────────────────────────────────────────────────────────────
@dataclass
class Component:
    kind: str
    name: str = ""
    exported: bool | None = None
    permission: str | None = None
    has_filter: bool = False
    actions: list[str] = field(default_factory=list)
    main: bool = False
    launcher: bool = False

    @property
    def is_launcher(self) -> bool:
        return self.main and self.launcher

    @property
    def exposed(self) -> bool:
        """Explicitly exported, or (no attribute) implicitly exported by having an intent filter."""
        return self.exported if self.exported is not None else self.has_filter


@dataclass
class Manifest:
    package: str = ""
    target_sdk: int | None = None
    debuggable: bool | None = None
    allow_backup: bool | None = None
    backup_rules: bool = False
    cleartext: bool | None = None
    network_config: str | None = None
    components: list[Component] = field(default_factory=list)


_ELEM = re.compile(r"^(\s*)E: (\S+)")
_ATTR = re.compile(r"^\s*A: (?:[^\s=]*:)?(\w+)(?:\(0x[0-9a-f]+\))?=(.*)$")


def _val(raw: str) -> str:
    raw = raw.strip()
    if m := re.match(r'"((?:[^"\\]|\\.)*)"', raw):
        return m.group(1)
    return raw.split()[0] if raw else ""


def _bool(v: str) -> bool | None:
    return True if v in ("true", "0xffffffff") else False if v in ("false", "0x0") else None


def parse_manifest(tree: str) -> Manifest:
    """Parse `aapt2 dump xmltree --file AndroidManifest.xml` output."""
    m = Manifest()
    stack: list[tuple[int, str]] = []
    comp: Component | None = None
    for line in tree.splitlines():
        if e := _ELEM.match(line):
            indent, tag = len(e.group(1)), e.group(2)
            while stack and stack[-1][0] >= indent:
                stack.pop()
            stack.append((indent, tag))
            if tag in COMPONENT_TAGS:
                comp = Component(tag)
                m.components.append(comp)
            elif tag == "intent-filter" and comp:
                comp.has_filter = True
            continue
        a = _ATTR.match(line)
        if not a or not stack:
            continue
        tag, key, v = stack[-1][1], a.group(1), _val(a.group(2))
        if tag == "manifest" and key == "package":
            m.package = v
        elif tag == "uses-sdk" and key == "targetSdkVersion":
            m.target_sdk = int(v, 0) if re.fullmatch(r"(0x[0-9a-f]+|\d+)", v) else None
        elif tag == "application":
            if key == "debuggable":
                m.debuggable = _bool(v)
            elif key == "allowBackup":
                m.allow_backup = _bool(v)
            elif key == "usesCleartextTraffic":
                m.cleartext = _bool(v)
            elif key == "networkSecurityConfig":
                m.network_config = v if v.startswith("@") else None
            elif key in ("dataExtractionRules", "fullBackupContent"):
                m.backup_rules = True
        elif tag in COMPONENT_TAGS and comp:
            if key == "name":
                comp.name = m.package + v if v.startswith(".") else v if "." in v else f"{m.package}.{v}"
            elif key == "exported":
                comp.exported = _bool(v)
            elif key == "permission":
                comp.permission = v
        elif tag == "action" and comp and key == "name":
            comp.actions.append(v)
            comp.main = comp.main or v == "android.intent.action.MAIN"
        elif tag == "category" and comp and key == "name" and v == "android.intent.category.LAUNCHER":
            comp.launcher = True
    return m


def parse_network_config(tree: str) -> dict:
    """From a network security config: is cleartext allowed app-wide, and for which domains."""
    out: dict = {"base_cleartext": None, "cleartext_domains": []}
    section, clear, domains = None, False, []

    def flush():
        if section == "domain-config" and clear:
            out["cleartext_domains"].extend(domains)

    for line in tree.splitlines():
        if e := _ELEM.match(line):
            if e.group(2) in ("base-config", "domain-config"):
                flush()
                section, clear, domains = e.group(2), False, []
        elif a := _ATTR.match(line):
            if a.group(1) == "cleartextTrafficPermitted":
                clear = _val(a.group(2)) == "true"
                if section == "base-config":
                    out["base_cleartext"] = clear
        elif section == "domain-config" and (t := re.match(r"^\s*T: '(.*)'", line)):
            domains.append(t.group(1))
    flush()
    return out


def resource_file(resources: str, ref: str) -> str | None:
    """Path of the file a resource id like @0x7f010000 points to, from `aapt2 dump resources`."""
    m = re.search(rf"resource {re.escape(ref.lstrip('@'))} \S+\n\s*\(\) \(file\) (\S+)", resources)
    return m.group(1) if m else None


def manifest_findings(m: Manifest, nsc: dict | None = None) -> list[dict]:
    out: list[dict] = []
    if m.debuggable:
        out.append({"rule": "debuggable", "detail": 'android:debuggable="true" in AndroidManifest.xml.'})
    if m.allow_backup is not False:
        how = "is true" if m.allow_backup else "is not set, so it defaults to true"
        extra = " A backup rules file is declared; check what it excludes." if m.backup_rules else ""
        out.append({"rule": "allow-backup", "detail": f"android:allowBackup {how}.{extra}"})
    # Cleartext: a network security config wins over the manifest attribute (API 24+).
    app_wide, why = None, ""
    if nsc and nsc["base_cleartext"] is not None:
        app_wide, why = (
            nsc["base_cleartext"],
            "the network security config's base-config permits cleartext HTTP",
        )
    elif m.cleartext is not None:
        app_wide, why = m.cleartext, 'android:usesCleartextTraffic="true"'
    elif not nsc and m.target_sdk is not None and m.target_sdk < 28:
        app_wide, why = (
            True,
            f"the app targets API {m.target_sdk} (below 28), where cleartext HTTP is allowed by default",
        )
    if app_wide:
        out.append({"rule": "cleartext-traffic", "detail": f"Cleartext HTTP is allowed app-wide: {why}."})
    if nsc and nsc["cleartext_domains"]:
        doms = ", ".join(sorted(set(nsc["cleartext_domains"])))
        out.append(
            {
                "rule": "cleartext-traffic",
                "key": "domains",
                "severity": "info",
                "detail": f"The network security config permits cleartext HTTP for: {doms}.",
            }
        )
    for c in m.components:
        if c.exposed and not c.is_launcher and not c.permission:
            how = (
                "is exported"
                if c.exported
                else "is exported implicitly (it has an intent filter and no android:exported)"
            )
            finding = {
                "rule": "exported-component",
                "key": c.name,
                "subject": c.name.rsplit(".", 1)[-1],
                "detail": f"{c.kind.capitalize()} {c.name} {how} and has no android:permission.",
            }
            if c.actions and all(a.startswith("android.appwidget.action.") for a in c.actions):
                # Home-screen widgets are exported by convention, so this is a note, not a warning.
                finding["severity"] = "info"
                finding["detail"] += (
                    " It is an app widget provider, exported by convention: check it handles untrusted intents."
                )
            out.append(finding)
    return out


# ── hard-coded secrets ───────────────────────────────────────────────────────
# High-confidence formats only. Words like "password" or "api_key" alone are not matched: they appear in
# every SDK and would bury the real findings.
SECRET_PATTERNS: list[tuple[str, re.Pattern[bytes], str]] = [
    ("AWS access key id", re.compile(rb"(?:AKIA|ASIA)[0-9A-Z]{16}"), "error"),
    ("Private key", re.compile(rb"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----"), "error"),
    ("Stripe live secret key", re.compile(rb"sk_live_[0-9a-zA-Z]{24,}"), "error"),
    ("Slack token", re.compile(rb"xox[baprs]-[0-9A-Za-z-]{10,}"), "error"),
    ("GitHub token", re.compile(rb"gh[pousr]_[0-9A-Za-z]{36,}"), "error"),
    (
        "Database URL with credentials",
        re.compile(
            rb"(?:mongodb(?:\+srv)?|postgres(?:ql)?|mysql|redis|amqps?)://[^\s:/@'\"]+:[^\s@/'\"]+@[^\s'\"]+"
        ),
        "error",
    ),
    ("Google API key", re.compile(rb"AIza[0-9A-Za-z_\-]{35}"), "info"),
]
_KIND_NOTE = {
    "Google API key": " Client API keys are meant to ship in apps; make sure this one is restricted to your package name and signing certificate.",
}
_SCANNED = re.compile(r"^(classes\d*\.dex|resources\.arsc|assets/.+|res/raw/.+)$")
_MAX_ENTRY = 24 * 1024 * 1024


def scan_bytes(data: bytes, where: str) -> list[dict]:
    """Secret findings in one blob. The value is never kept: only its length and a short sha256 fingerprint."""
    hits: dict[tuple[str, str], dict] = {}
    for kind, pat, severity in SECRET_PATTERNS:
        for m in pat.finditer(data):
            raw = m.group(0)
            if b"EXAMPLE" in raw.upper():
                continue
            fp = hashlib.sha256(raw).hexdigest()[:8]
            hits.setdefault(
                (kind, fp),
                {
                    "rule": "hardcoded-secret",
                    "key": f"{kind.lower().replace(' ', '-')}:{fp}",
                    "subject": kind,
                    "severity": severity,
                    "detail": f"{kind} ({len(raw)} characters, sha256 {fp}…) in {where}.{_KIND_NOTE.get(kind, '')}",
                },
            )
    return list(hits.values())


def scan_secrets(apk: str | Path) -> list[dict]:
    out: list[dict] = []
    with zipfile.ZipFile(apk) as z:
        for info in z.infolist():
            if _SCANNED.match(info.filename) and 0 < info.file_size <= _MAX_ENTRY:
                out.extend(scan_bytes(z.read(info), info.filename))
    seen, unique = set(), []
    for f in out:  # the same secret in two files is one finding, reported in the first
        if f["key"] not in seen:
            seen.add(f["key"])
            unique.append(f)
    return unique


# ── APK ──────────────────────────────────────────────────────────────────────
def _aapt(aapt2: str, *args: str) -> str:
    try:
        return subprocess.run(
            [aapt2, "dump", *args], check=False, capture_output=True, text=True, timeout=120
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


def scan_apk(apk: str | Path) -> dict:
    """Static evidence from an APK: {"ran": [...], "notes": [...], "findings": [...]}."""
    ev: dict = {"ran": ["static"], "notes": [], "findings": scan_secrets(apk)}
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


# ── data left on the device ──────────────────────────────────────────────────
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


# ── dynamic (Frida log) ──────────────────────────────────────────────────────
def parse_frida_log(text: str) -> dict:
    """Findings from the JSON lines `frida-observe.js` prints; other lines are ignored."""
    cleartext: set[str] = set()
    unpinned: set[str] = set()
    pinned: set[str] = set()
    seen, notes = False, []
    for line in text.splitlines():
        try:
            o = json.loads(line.strip())
        except ValueError:
            continue
        if not isinstance(o, dict) or o.get("asm") != 1:
            continue
        seen = True
        host = str(o.get("host", ""))[:120]
        if o.get("check") == "cleartext" and host:
            cleartext.add(host)
        elif o.get("check") == "pinning" and host:
            if o.get("pinned") is True:
                pinned.add(host)
            elif o.get("pinned") is False:  # null / missing means "couldn't tell": no finding
                unpinned.add(host)
        elif o.get("check") == "hook-failed":
            notes.append(f"Frida hook {o.get('what', '?')} did not attach, so that observation is missing.")
    findings = [
        {
            "rule": "cleartext-observed",
            "key": h,
            "subject": h,
            "detail": f"The app made a plain http:// request to {h}.",
        }
        for h in sorted(cleartext)
    ]
    if unpinned:
        hosts = ", ".join(sorted(unpinned)[:10])
        findings.append(
            {
                "rule": "no-cert-pinning",
                "detail": f"OkHttp opened TLS connections to {hosts} with no certificate pins configured.",
            }
        )
    return {"ran": ["dynamic"] if seen else [], "notes": notes, "findings": findings}


# ── the audit ────────────────────────────────────────────────────────────────
def build_audit(sources: dict[str, dict], platform: str = "android") -> dict:
    """Combine the evidence of every source that has run into one `audits/security.json` document."""
    rules = {r.id: r for r in load_rules()}
    ran = sorted({c for s in sources.values() for c in s.get("ran", [])})
    notes = [n for s in sources.values() for n in s.get("notes", [])]
    findings = []
    for ev in sources.values():
        for f in ev.get("findings", []):
            r = rules[f["rule"]]
            key = f.get("key")
            title = f"{r.title}: {f['subject']}" if f.get("subject") else r.title
            findings.append(
                {
                    "id": f"{r.id}:{key}" if key else r.id,
                    "severity": f.get("severity") or r.severity,
                    "title": title,
                    "detail": f"{f['detail']} {r.why}",
                    "fix": r.fix,
                    "platform": platform,
                    "category": CATEGORY_LABEL[r.category],
                    "refs": [{"title": x.title, "url": x.url, "publisher": x.publisher} for x in r.refs],
                }
            )
    order = {"error": 0, "warning": 1, "info": 2}
    findings.sort(key=lambda f: (order[f["severity"]], f["id"]))
    n = {s: sum(1 for f in findings if f["severity"] == s) for s in order}
    score = max(0, 100 - 20 * n["error"] - 8 * n["warning"] - 2 * n["info"])
    status = (
        "fail" if n["error"] else "warn" if n["warning"] else "info"
    )  # never "pass": some rules aren't checked yet
    not_checked = [r.id for r in rules.values() if r.status == "planned" and r.platform in (platform, "both")]
    skipped = [c for c in ("manifest", "static", "data", "dynamic") if c not in ran]
    parts = [f"{n['error']} error(s), {n['warning']} warning(s), {n['info']} info"]
    parts.append("checked: " + (", ".join(ran) or "nothing"))
    if skipped:
        parts.append("not run: " + ", ".join(skipped))
    return {
        "schema": 1,
        "audit": "security",
        "title": "Security",
        "tool": "appscreenmap security (aapt2, built-in scans"
        + (", Frida log)" if "dynamic" in ran else ")"),
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "source": "run",
        "status": status,
        "score": score,
        "score_note": SCORE_NOTE,
        "summary": " · ".join(parts),
        "metrics": [
            {"label": "checks run", "value": ", ".join(ran) or "none"},
            {
                "label": "not run",
                "value": ", ".join(skipped) or "none",
                "tone": "warn" if skipped else "good",
            },
            {
                "label": "rules not checked yet",
                "value": len(not_checked),
                "tone": "info",
                "hint": ", ".join(not_checked),
            },
            *({"label": "note", "value": t, "tone": "warn"} for t in notes),
        ],
        "charts": [],
        "findings": findings,
        "refs": [],
    }


def load_evidence(run: Path) -> dict[str, dict]:
    p = run / "audits" / "security-evidence.json"
    try:
        return json.loads(p.read_text()).get("sources", {})
    except (OSError, ValueError):
        return {}


def write_audit(run: Path, sources: dict[str, dict], platform: str = "android") -> dict:
    """Store the evidence ledger and the audit built from it in the run folder."""
    d = run / "audits"
    d.mkdir(exist_ok=True)
    (d / "security-evidence.json").write_text(json.dumps({"schema": 1, "sources": sources}, indent=1) + "\n")
    audit = build_audit(sources, platform)
    (d / "security.json").write_text(json.dumps(audit, indent=1) + "\n")
    return audit
