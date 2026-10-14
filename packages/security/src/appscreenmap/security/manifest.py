"""Manifest checks: parse `aapt2 dump xmltree` output (manifest, network security config) into findings."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

COMPONENT_TAGS = ("activity", "activity-alias", "service", "receiver", "provider")


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
    reparenting: bool = False

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
    min_sdk: int | None = None
    debuggable: bool | None = None
    allow_backup: bool | None = None
    backup_rules: bool = False
    cleartext: bool | None = None
    network_config: str | None = None
    components: list[Component] = field(default_factory=list)
    permissions: list[tuple[str, int]] = field(default_factory=list)  # declared: (name, protectionLevel)


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
            if tag == "permission":
                m.permissions.append(("", 0))
            elif tag in COMPONENT_TAGS:
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
        elif tag == "uses-sdk" and key == "minSdkVersion":
            m.min_sdk = int(v, 0) if re.fullmatch(r"(0x[0-9a-f]+|\d+)", v) else None
        elif tag == "permission" and m.permissions:
            name, level = m.permissions[-1]
            if key == "name":
                name = v
            elif key == "protectionLevel" and re.fullmatch(r"(0x[0-9a-f]+|\d+)", v):
                level = int(v, 0)
            m.permissions[-1] = (name, level)
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
            elif key == "allowTaskReparenting":
                comp.reparenting = _bool(v) is True
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
    for name, level in m.permissions:
        if level & 0xF in (0, 1):  # the base protection level: 0 normal, 1 dangerous
            kind = "normal" if level & 0xF == 0 else "dangerous"
            out.append(
                {
                    "rule": "custom-permission-weak",
                    "key": name,
                    "subject": name.rsplit(".", 1)[-1],
                    "detail": f"The app declares the custom permission {name} with protectionLevel {kind}.",
                }
            )
    for c in m.components:
        if c.reparenting:
            out.append(
                {
                    "rule": "task-hijacking",
                    "key": c.name,
                    "subject": c.name.rsplit(".", 1)[-1],
                    "detail": f'{c.kind.capitalize()} {c.name} sets android:allowTaskReparenting="true".',
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
