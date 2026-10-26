"""Snapshot LibChecker-Rules (Apache-2.0) into packages/stack: native library and component names → library labels.

    python3 -I scripts/sync-libchecker-rules.py        # `make stack-rules-sync`

Only exact-name rules are kept (LibChecker's regex rules carry their patterns in the app, not in the rules repo).
"""

from __future__ import annotations

import io
import json
import tarfile
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

REPO = "LibChecker/LibChecker-Rules"
OUT = Path(__file__).resolve().parents[1] / "packages/stack/src/appscreenmap/stack"
KINDS = {
    "native-libs": "native",
    "activities-libs": "components",
    "services-libs": "components",
    "receivers-libs": "components",
    "providers-libs": "components",
}


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "appscreenmap-sync"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def main() -> None:
    commit = json.loads(_get(f"https://api.github.com/repos/{REPO}/commits/master"))["sha"]
    archive = _get(f"https://codeload.github.com/{REPO}/tar.gz/{commit}")
    rules: dict[str, dict[str, dict]] = {"native": {}, "components": {}}
    license_text = ""
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
        for m in tar.getmembers():
            if not m.isfile():
                continue
            parts = m.name.split("/")[1:]  # drop the "<repo>-<sha>/" root
            if parts == ["LICENSE"]:
                license_text = tar.extractfile(m).read().decode()
            if len(parts) != 2 or parts[0] not in KINDS or not parts[1].endswith(".json"):
                continue
            try:
                rule = json.loads(tar.extractfile(m).read())
            except ValueError:
                continue
            if label := str(rule.get("label") or "").strip():
                entry = {
                    "label": label,
                    "team": rule.get("team") or None,
                    "url": rule.get("relativeUrl") or None,
                }
                rules[KINDS[parts[0]]][parts[1].removesuffix(".json")] = entry
    snapshot = {
        "source": f"https://github.com/{REPO}",
        "commit": commit,
        "synced": datetime.now(UTC).date().isoformat(),
        "license": "Apache-2.0 (LIBCHECKER-LICENSE)",
        **{k: dict(sorted(v.items())) for k, v in rules.items()},
    }
    (OUT / "libchecker.json").write_text(json.dumps(snapshot, indent=0, ensure_ascii=False) + "\n")
    (OUT / "LIBCHECKER-LICENSE").write_text(license_text)
    print(
        f"libchecker.json: {len(rules['native'])} native, {len(rules['components'])} components @ {commit[:10]}"
    )


if __name__ == "__main__":
    main()
