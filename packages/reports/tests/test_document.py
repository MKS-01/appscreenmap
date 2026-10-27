from __future__ import annotations

import json
import re

from appscreenmap.reports.document import build_document, write_report
from appscreenmap.reports.fixes import tasks_from


def _screen(sid, title, **kw):
    return {"id": sid, "kind": "app", "title": title, "activity": "dev.alpha.MainActivity", "depth": 0,
            "elements": [], **kw}  # fmt: skip


def _canvas(tmp_path, a11y_issues=None, store=True, extra=None):
    run = tmp_path / "alpha"
    (run / "screens").mkdir(parents=True)
    (run / "screens" / "s001.png").write_bytes(b"\x89PNG fake")
    data = {
        "schema": 1,
        "run": {
            "id": "alpha-1",
            "app": {"package": "dev.alpha", "label": "Alpha", "version": "1.2"},
            "device": {"platform": "android", "name": "Pixel", "android": "17", "sdk": 37},
            "config": {"max_steps": 50},
            "steps": 10,
            "scenarios": [
                {"id": "sc1", "label": "First run", "run_id": "alpha-1", "screens": ["s001", "s002"]}
            ],
        },
        "screens": [_screen("s001", "Home", thumb="screens/s001.png"), _screen("s002", "Profile")],
        "transitions": [],
        "events": [{"step": 4, "type": "crash", "screen": "s002", "detail": "NPE"}],
        "stats": {"screens": 2, "transitions": 1, "max_depth": 1, "elements": {"done": 4, "pending": 1}},
    }
    (run / "map.json").write_text(json.dumps(data))
    (run / "titles.json").write_text(json.dumps({"language": "en", "titles": {"s002": "Your profile"}}))
    rule = {"sc": "1.1.1", "name": "Non-text Content", "level": "A", "severity": "warning", "why": "No label.",
            "fix": "Add a contentDescription."}  # fmt: skip
    issues = a11y_issues if a11y_issues is not None else [
        {"key": f"{s}::image-alt::x", "screen": s, "rule": "image-alt", "sc": "1.1.1", "level": "A",
         "severity": "warning", "rid": "dev.alpha:id/logo", "label": "logo", "triage": "open"}
        for s in ("s001", "s002")
    ]  # fmt: skip
    (run / "a11y.json").write_text(
        json.dumps(
            {
                "rules": {"image-alt": rule},
                "summary": {"by_criterion": {"1.1.1": len(issues)}},
                "issues": issues,
            }
        )
    )
    audits = run / "audits"
    audits.mkdir()
    if store:
        (audits / "store.json").write_text(json.dumps({
            "schema": 1, "audit": "store", "title": "Store readiness", "source": "run", "status": "fail", "score": 40,
            "summary": "Blocked.", "findings": [
                {"id": "store::target", "severity": "error", "title": "Targets API 30", "due": "2026-11-01",
                 "fix": "Raise targetSdk.", "refs": [{"title": "Target API", "url": "https://support.google.com/x"}]},
            ],
        }))  # fmt: skip
    (audits / "platform.json").write_text(json.dumps({
        "schema": 1, "audit": "platform", "title": "Platform changes", "source": "sample", "status": "warn",
        "summary": "Sample.", "findings": [{"id": "p1", "severity": "error", "title": "Sample finding"}],
    }))  # fmt: skip
    (audits / "security-evidence.json").write_text(json.dumps({"schema": 1, "sources": {}}))
    for aid, a in (extra or {}).items():
        (audits / f"{aid}.json").write_text(json.dumps(a))
    return run


def test_report_has_every_audit_in_order_and_skips_sample_data(tmp_path):
    run = _canvas(tmp_path)
    doc = build_document(run)
    assert [s["id"] for s in doc["sections"]] == ["coverage", "stability", "a11y", "perf", "store"]
    assert doc["cover"]["version"] == "1.2"
    # Built-in audits are written as files, like any tool's.
    assert json.loads((run / "audits" / "a11y.json").read_text())["audit"] == "a11y"
    # titles.json (English display titles) wins over map.json's own.
    a11y = next(s for s in doc["sections"] if s["id"] == "a11y")
    assert [w["title"] for w in a11y["findings"][0]["where"]] == ["Home", "Your profile"]
    assert doc["deadlines"][0]["due"] == "2026-11-01"
    assert all(f["audit"] != "coverage" for f in doc["top"])


def test_a_new_audit_file_gets_a_section_without_renderer_changes(tmp_path):
    madeup = {"schema": 1, "audit": "privacy", "title": "Privacy labels", "status": "warn", "score": 70,
              "summary": "One label missing.", "findings": [
                  {"id": "privacy::label", "severity": "warning", "title": "Data safety label missing", "screen": "s001"}]}  # fmt: skip
    run = _canvas(tmp_path, extra={"privacy": madeup})
    out = write_report(run, ["md", "html", "fixes"])
    md, page = out["md"].read_text(), out["html"].read_text()
    assert "## Privacy labels" in md and "Data safety label missing" in md
    assert 'id="privacy"' in page and "Data safety label missing" in page
    assert "privacy::label" in out["fixes"].read_text()


def test_markdown_and_html_keep_the_five_sections_in_order(tmp_path):
    out = write_report(_canvas(tmp_path), ["md", "html"])
    md = out["md"].read_text()
    heads = [h for h in re.findall(r"^## (.+)$", md, re.MULTILINE)]
    assert heads[0] == "Summary" and heads[1] == "Conditions" and heads[-1] == "Appendix"
    assert (out["md"].parent / "report-assets" / "s001.png").is_file()
    page = out["html"].read_text()
    assert (
        page.index('<h2 id="summary"')
        < page.index('<h2 id="conditions"')
        < page.index('id="coverage"')
        < page.index('<h2 id="appendix"')
    )
    assert "data:image/png;base64," in page  # thumbnails inlined: the file opens offline
    assert "--accent" in page  # design tokens inlined
    assert 'font-family:"Geist Variable"' in page  # and the fonts, so it looks the same offline


def test_profiles_and_audit_lists_pick_sections(tmp_path):
    run = _canvas(tmp_path)
    assert [s["id"] for s in build_document(run, profile="release")["sections"]] == ["store"]
    assert [s["id"] for s in build_document(run, only=["a11y", "perf"])["sections"]] == ["a11y", "perf"]


def test_fix_list_groups_orders_and_leaves_out_crawl_and_dismissed(tmp_path):
    doc = build_document(_canvas(tmp_path))
    tasks = tasks_from(doc)
    assert [t["task"] for t in tasks] == [
        "store::target",
        "stability::crash::s002::0",
        "a11y::image-alt",
    ]  # due date first
    a11y = tasks[-1]
    assert [w["id"] for w in a11y["where"]] == ["s001", "s002"]  # one task, every screen
    assert a11y["elements"][0]["rid"] == "dev.alpha:id/logo"

    dismissed = [
        {"key": "k", "screen": "s001", "rule": "image-alt", "sc": "1.1.1", "level": "A", "severity": "warning",
         "triage": "wontfix"}
    ]  # fmt: skip
    doc = build_document(_canvas(tmp_path / "b", a11y_issues=dismissed))
    assert "a11y::image-alt" not in [t["task"] for t in tasks_from(doc)]


def test_fix_list_ticks_a_task_once_its_finding_is_gone(tmp_path):
    run = _canvas(tmp_path)
    first = write_report(run, ["fixes"])["fixes"].read_text()
    assert "- [ ] **1. Targets API 30**" in first
    assert "**Check it's fixed:** Rebuild, then `appscreenmap store`" in first

    store = json.loads((run / "audits" / "store.json").read_text())
    store["findings"], store["status"] = [], "pass"
    (run / "audits" / "store.json").write_text(json.dumps(store))
    second = write_report(run, ["fixes"])["fixes"].read_text()
    assert "- [x] Targets API 30 · `store::target` · gone in `alpha-1`" in second
    assert "- [ ] **1. Targets API 30**" not in second


def test_a_task_whose_audit_did_not_run_again_is_not_ticked(tmp_path):
    run = _canvas(tmp_path)
    write_report(run, ["fixes"])
    (run / "audits" / "store.json").unlink()
    text = write_report(run, ["fixes"])["fixes"].read_text()
    assert "[x] Targets API 30" not in text


def _triage(run, statuses):
    """notes.json triage, as the viewer writes it, keyed like a11y.json issues."""
    (run / "notes.json").write_text(json.dumps({"a11y": {k: {"status": v} for k, v in statuses.items()}}))


def test_triage_in_notes_counts_without_rerunning_a11y_and_is_never_a_fix(tmp_path):
    run = _canvas(tmp_path)
    assert "a11y::image-alt" in write_report(run, ["fixes"])["fixes"].read_text()

    _triage(run, {"s001::image-alt::x": "wontfix", "s002::image-alt::x": "wontfix"})
    doc = build_document(run)
    assert all(f["audit"] != "a11y" for f in doc["top"])
    text = write_report(run, ["fixes"])["fixes"].read_text()
    assert "a11y::image-alt" not in text  # dismissed: neither open nor ticked as fixed
    state = json.loads((run / "reports" / "fixes.json").read_text())["tasks"]["a11y::image-alt"]
    assert state["dismissed"] == "wontfix" and "fixed_on" not in state


def test_mixed_triage_keeps_only_open_issues_as_where_to_fix(tmp_path):
    run = _canvas(tmp_path)
    _triage(run, {"s001::image-alt::x": "false_positive"})
    task = next(t for t in tasks_from(build_document(run)) if t["task"] == "a11y::image-alt")
    assert [w["id"] for w in task["where"]] == ["s002"]
    assert [e["screen"] for e in task["elements"]] == ["s002"]


def test_open_task_whose_audit_did_not_run_is_listed_as_not_rechecked(tmp_path):
    run = _canvas(tmp_path)
    write_report(run, ["fixes"])
    (run / "audits" / "store.json").unlink()
    text = write_report(run, ["fixes"])["fixes"].read_text()
    assert "## Not re-checked" in text and "`store::target`" in text


def test_another_tools_file_under_a_builtin_id_wins(tmp_path):
    theirs = {"schema": 1, "audit": "perf", "title": "Performance (Perfetto)", "tool": "perfetto 50",
              "status": "warn", "summary": "From a trace.", "findings": []}  # fmt: skip
    run = _canvas(tmp_path, extra={"perf": theirs})
    perf = next(s for s in build_document(run)["sections"] if s["id"] == "perf")
    assert perf["title"] == "Performance (Perfetto)"
    assert json.loads((run / "audits" / "perf.json").read_text())["tool"] == "perfetto 50"


def test_an_audit_holding_an_error_never_reads_as_passing():
    from appscreenmap.reports.builtin import perf

    data = {"run": {}, "screens": []}
    screens = [{"screen": f"s{i:03}", "title": f"S{i}", "median_ms": 300, "frames": 40, "janky_pct": 1,
                "rating": "good"} for i in range(19)]  # fmt: skip
    screens.append(
        {"screen": "s099", "title": "Web", "median_ms": 2700, "frames": 2, "janky_pct": 0, "rating": "slow"}
    )
    audit = perf(data, {"budget_ms": 1000, "screens": screens})
    assert audit["score"] == 95 and audit["status"] == "warn"


def test_the_same_crash_at_another_step_stays_the_same_task(tmp_path):
    run = _canvas(tmp_path)
    write_report(run, ["fixes"])
    data = json.loads((run / "map.json").read_text())
    data["events"] = [{"step": 9, "type": "crash", "screen": "s002", "detail": "NPE"}]
    (run / "map.json").write_text(json.dumps(data))
    text = write_report(run, ["fixes"])["fixes"].read_text()
    assert "Crash on Profile" in text and "## Fixed" not in text


def test_a11y_title_counts_only_issues_still_open(tmp_path):
    run = _canvas(tmp_path)
    _triage(run, {"s001::image-alt::x": "false_positive"})
    a11y = next(s for s in build_document(run)["sections"] if s["id"] == "a11y")
    assert a11y["findings"][0]["title"] == "Non-text Content (1 issue)"
