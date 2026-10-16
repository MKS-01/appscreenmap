"""A test account per app: made once, kept on this machine, reused by later crawls.

A playbook (or `[inputs]`) refers to it as `${ACCOUNT_EMAIL}` and `${ACCOUNT_PASSWORD}`. The first crawl that needs
them generates a random email and password and saves them in a private file outside the repo and outside the run
folders (`<home>/accounts/<package>.json`, mode 0600); every later crawl of that app gets the same values, so a
sign-up done once becomes a login for the next run. Values are typed on the device but never written to a run.
"""

from __future__ import annotations

import json
import os
import secrets
import sys
from datetime import UTC, datetime
from pathlib import Path

ACCOUNT_VARS = ("ACCOUNT_EMAIL", "ACCOUNT_PASSWORD")
DEFAULT_EMAIL = (
    "asm+{rand}@example.com"  # {rand}: 8 random hex characters, fixed when the account is first made
)


def home() -> Path:
    if env := os.environ.get("APPSCREENMAP_HOME"):
        return Path(env)
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "appscreenmap"
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "appscreenmap"


def vault_path(package: str, root: Path | None = None) -> Path:
    return (root or home()) / "accounts" / f"{package}.json"


def _password() -> str:
    # Upper, lower, digit and a symbol, so sign-up forms with a password policy accept it.
    return f"Asm-{secrets.token_urlsafe(9)}-9!"


def load_or_create(package: str, email_template: str = DEFAULT_EMAIL, root: Path | None = None) -> dict:
    """The saved account of this app, made now when there is none: {email, password, status, created_at, path, new}."""
    path = vault_path(package, root)
    if path.is_file():
        data = json.loads(path.read_text())
        return {**data, "path": str(path), "new": False}
    data = {
        "email": email_template.replace("{rand}", secrets.token_hex(4)),
        "password": _password(),
        "status": "new",  # becomes "created" when a playbook step says the sign-up went through
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(json.dumps(data, indent=1) + "\n")
    path.chmod(0o600)
    return {**data, "path": str(path), "new": True}


def mark(package: str, status: str, root: Path | None = None) -> None:
    path = vault_path(package, root)
    if path.is_file():
        data = json.loads(path.read_text())
        data["status"] = status
        data[f"{status}_at"] = datetime.now(UTC).isoformat(timespec="seconds")
        path.write_text(json.dumps(data, indent=1) + "\n")


def env_for(account: dict) -> dict[str, str]:
    return {"ACCOUNT_EMAIL": account["email"], "ACCOUNT_PASSWORD": account["password"]}
