"""The security rule catalogue stays valid and in step with its documentation."""

from __future__ import annotations

import json

import pytest

from appscreenmap.security.rules import PATH, RuleError, load_rules, rules_for
from appscreenmap.testkit.helpers import REPO

ROOT = REPO
DOC = ROOT / ".claude" / "skills" / "security-rules" / "reference" / "rules.md"


def test_the_catalogue_loads_and_every_rule_is_complete():
    rules = load_rules()
    assert len(rules) >= 12
    for r in rules:
        assert r.why.endswith(".") and r.fix.endswith("."), r.id
        assert r.refs and all(ref.url.startswith("https://") for ref in r.refs), r.id


def test_ids_are_unique_kebab_case():
    ids = [r.id for r in load_rules()]
    assert len(ids) == len(set(ids))
    assert all(i == i.lower() and " " not in i and "_" not in i for i in ids)


def test_platform_filter_includes_cross_platform_rules():
    android = {r.id for r in rules_for("android")}
    ios = {r.id for r in rules_for("ios")}
    assert "exported-component" in android and "exported-component" not in ios
    assert "ats-exceptions" in ios and "ats-exceptions" not in android
    assert "hardcoded-secret" in android & ios


def test_every_rule_is_in_the_skills_rules_page():
    text = DOC.read_text()
    missing = [r.id for r in load_rules() if f"`{r.id}`" not in text]
    assert not missing, f"add to {DOC.relative_to(ROOT)}: {missing}"


@pytest.mark.parametrize(
    ("patch", "message"),
    [
        ({"severity": "critical"}, "severity"),
        ({"platform": "windows"}, "platform"),
        ({"category": "nope"}, "category"),
        ({"refs": []}, "official reference"),
        ({"refs": [{"title": "Blog", "url": "https://example.com/post", "publisher": "x"}]}, "official"),
        (
            {"refs": [{"title": "Plain", "url": "http://developer.android.com/x", "publisher": "x"}]},
            "official",
        ),
    ],
)
def test_a_bad_rule_is_rejected(tmp_path, patch, message):
    data = json.loads(PATH.read_text())
    data["rules"][0].update(patch)
    f = tmp_path / "rules.json"
    f.write_text(json.dumps(data))
    with pytest.raises(RuleError, match=message):
        load_rules(f)


def test_duplicate_ids_are_rejected(tmp_path):
    data = json.loads(PATH.read_text())
    data["rules"].append(dict(data["rules"][0]))
    f = tmp_path / "rules.json"
    f.write_text(json.dumps(data))
    with pytest.raises(RuleError, match="duplicate"):
        load_rules(f)
