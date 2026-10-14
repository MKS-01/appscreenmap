"""Dynamic evidence: findings from the JSON lines the observation-only Frida hook prints.

`HOOK` is the script to load: `frida -U -f <package> -l "$(appscreenmap security --frida-script)"`.
"""

from __future__ import annotations

import json
from pathlib import Path

HOOK = Path(__file__).parent / "hooks" / "frida-observe.js"


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
