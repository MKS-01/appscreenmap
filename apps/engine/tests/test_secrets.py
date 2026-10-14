"""Secrets as ${ENV} placeholders: typed on the device, never written to a run."""

import json

import pytest
from fakedevice import FakeApp, FakeDriver, btn, crawl, title

from appscreenmap import explorer as explorer_mod
from appscreenmap.core.config import CrawlConfig, MissingSecret, placeholders, resolve
from appscreenmap.export import export_run
from appscreenmap.testkit.helpers import PKG, hierarchy, node

SECRET = "s3cr3t-Hunter2"

LOGIN = {
    "login": hierarchy(
        title("Sign in"),
        node(
            "android.widget.EditText",
            (100, 300, 1000, 420),
            rid=f"{PKG}:id/email",
            hint="Email",
            clickable=True,
            focusable=True,
        ),
        node(
            "android.widget.EditText",
            (100, 460, 1000, 580),
            rid=f"{PKG}:id/password",
            hint="Password",
            password=True,
            clickable=True,
            focusable=True,
        ),
        btn((100, 650, 500, 770), text="Sign in"),
    ),
    "home": hierarchy(title("Home"), node("android.widget.TextView", (40, 300, 1000, 360), text="Welcome")),
}


@pytest.fixture(autouse=True)
def fast(monkeypatch):
    monkeypatch.setattr(explorer_mod, "PIN_TOAST_SECONDS", 0)


def test_resolve_fills_placeholders_from_env():
    env = {"APP_PASSWORD": "pw", "USER": "qa"}
    assert resolve("${APP_PASSWORD}", env) == "pw"
    assert resolve("${USER}@example.com", env) == "qa@example.com"
    assert resolve("no placeholder $HOME", env) == "no placeholder $HOME"
    assert placeholders("${A}-${B_2}") == ["A", "B_2"]
    with pytest.raises(MissingSecret, match="APP_TOKEN"):
        resolve("${APP_TOKEN}", env)


def test_config_reports_unset_secrets(tmp_path):
    toml = tmp_path / "c.toml"
    toml.write_text('[inputs]\n"pass" = "${APP_PASSWORD}"\ndefault = "${APP_DEFAULT}"\n')
    cfg = CrawlConfig.load(toml)
    assert cfg.missing_secrets({}) == ["APP_DEFAULT", "APP_PASSWORD"]
    assert cfg.missing_secrets({"APP_PASSWORD": "x", "APP_DEFAULT": "y"}) == []
    # The placeholder, not a value, is what a run stores in run.config.
    assert cfg.to_dict()["inputs"]["pass"] == "${APP_PASSWORD}"


def test_crawl_types_the_secret_but_records_only_the_placeholder(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", SECRET)
    d = FakeDriver(FakeApp(LOGIN, {("login", "Sign in"): "home"}, start="login"))
    # User rules come first, ahead of the built-in ones (as CrawlConfig.load orders them).
    run_dir, _ = crawl(tmp_path, d, inputs={"pass": "${APP_PASSWORD}", **CrawlConfig().inputs})

    assert SECRET in d.app.typed  # the device got the real value
    export_run(run_dir)
    for f in run_dir.rglob("*"):
        if f.is_file() and f.suffix in (".json", ".jsonl", ".yaml", ".mmd", ".xml"):
            assert SECRET not in f.read_text(), f"secret leaked into {f.relative_to(run_dir)}"

    data = json.loads((run_dir / "map.json").read_text())
    login = next(s for s in data["screens"] if s["title"] == "Sign in")
    pw = next(f for f in login["autofill"] if "password" in f["rid"])
    assert pw["value"] == "${APP_PASSWORD}" and pw["secret"] is True
    email = next(f for f in login["autofill"] if "email" in f["rid"])
    assert email["secret"] is False

    home = next(s for s in data["screens"] if s["title"] == "Home")
    flow = (run_dir / "flows" / f"{home['id']}.yaml").read_text()
    assert '- inputText: "${APP_PASSWORD}"' in flow
    assert "# Needs: maestro test -e APP_PASSWORD=…" in flow
