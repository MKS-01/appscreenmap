import json
from pathlib import Path

from appscreenmap.a11y import RULES, audit_run, format_audit
from appscreenmap.drivers.apkinfo import parse_manifest_activities
from appscreenmap.testkit.helpers import PKG, hierarchy, node

ACT = f"{PKG}.MainActivity"
DPI = 160  # 1 px = 1 dp keeps the geometry readable


def _screen(sid, title="Home", elements=(), autofill=(), reach_path=()):
    return {
        "id": sid,
        "kind": "app",
        "title": title,
        "activity": ACT,
        "package": PKG,
        "width": 1080,
        "height": 2400,
        "hierarchy": f"screens/{sid}.xml",
        "elements": list(elements),
        "autofill": list(autofill),
        "reach_path": list(reach_path),
    }


def _el(label, kind="button", rid="", x=0):
    return {"label": label, "kind": kind, "rid": rid, "action": "click", "bounds": [x, 2200, x + 100, 2300]}


def make_run(tmp: Path, screens: list[tuple[dict, str]], events=(), app_extra=None) -> Path:
    run = tmp / "proj" / "proj-1"
    (run / "screens").mkdir(parents=True)
    for s, xml in screens:
        (run / s["hierarchy"]).write_text(xml)
    (run / "map.json").write_text(
        json.dumps(
            {
                "schema": 1,
                "run": {
                    "id": "proj-1",
                    "app": {"package": PKG, **(app_extra or {})},
                    "device": {"width": 1080, "height": 2400, "density": DPI, "font_scale": 1.0},
                },
                "screens": [s for s, _ in screens],
                "transitions": [],
                "events": list(events),
                "stats": {},
            }
        )
    )
    return run


def rules_of(rep):
    return {i["rule"] for i in rep["issues"]}


def btn(bounds, **kw):
    kw.setdefault("focusable", True)
    return node("android.widget.Button", bounds, clickable=True, **kw)


def test_target_size_uses_wcag_spacing_exception(tmp_path):
    crowded = hierarchy(btn((100, 500, 116, 516), desc="A"), btn((120, 500, 136, 516), desc="B"))
    spaced = hierarchy(btn((100, 500, 116, 516), desc="A"), btn((400, 500, 416, 516), desc="B"))
    big = hierarchy(btn((100, 500, 148, 548), desc="A"), btn((150, 500, 198, 548), desc="B"))
    run = make_run(
        tmp_path,
        [(_screen("s001"), crowded), (_screen("s002", "Two"), spaced), (_screen("s003", "Three"), big)],
    )
    rep = audit_run(run)
    hits = [i for i in rep["issues"] if i["rule"] == "target-size-min"]
    assert {i["screen"] for i in hits} == {"s001"} and len(hits) == 2
    assert hits[0]["sc"] == "2.5.8" and hits[0]["level"] == "AA"
    assert (run / "a11y.json").is_file()


def test_label_in_name_focusable_and_role(tmp_path):
    xml = hierarchy(
        node(
            "android.widget.Button",
            (0, 300, 400, 420),
            clickable=True,
            focusable=True,
            text="Send",
            desc="Submit form",
        ),
        node("android.widget.Button", (0, 500, 400, 620), clickable=True, focusable=False, text="Next"),
        node(
            "android.view.View",
            (0, 700, 400, 820),
            clickable=True,
            focusable=True,
            children=[node("android.widget.TextView", (10, 710, 390, 810), text="Card")],
        ),
    )
    rep = audit_run(make_run(tmp_path, [(_screen("s001"), xml)]))
    by_rule = {i["rule"]: i for i in rep["issues"]}
    assert by_rule["label-in-name"]["label"] == "Submit form"
    assert by_rule["not-focusable"]["label"] == "Next"
    assert by_rule["no-role"]["label"] == "Card"


def test_cross_screen_navigation_and_identification(tmp_path):
    nav = [_el(x, "nav", x=i * 200) for i, x in enumerate(["Home", "Search", "Saved", "Profile"])]
    shuffled = [_el(x, "nav", x=i * 200) for i, x in enumerate(["Search", "Home", "Saved", "Profile"])]
    player = [_el(x, "nav", x=i * 200) for i, x in enumerate(["Play", "Pause", "Stop"])]
    screens = [
        (_screen("s001", elements=[*nav, _el("Settings", rid=f"{PKG}:id/settings")]), hierarchy()),
        (_screen("s002", "B", elements=[*nav, _el("Preferences", rid=f"{PKG}:id/settings")]), hierarchy()),
        (_screen("s003", "C", elements=nav), hierarchy()),
        (_screen("s004", "D", elements=shuffled), hierarchy()),
        (_screen("s005", "Player", elements=player), hierarchy()),  # its own control row, not the app nav
    ]
    rep = audit_run(make_run(tmp_path, screens))
    nav_issues = [i for i in rep["issues"] if i["rule"] == "nav-inconsistent"]
    assert [i["screen"] for i in nav_issues] == ["s004"] and "different order" in nav_issues[0]["detail"]
    ident = [i for i in rep["issues"] if i["rule"] == "identification-inconsistent"]
    assert len(ident) == 1 and "preferences" in ident[0]["detail"]


def test_flow_checks_redundant_entry_and_change_on_input(tmp_path):
    email = {"label": "Email", "value": "a@b.c", "selector": {}}
    s1 = _screen("s001", "Sign up", autofill=[email])
    s2 = _screen("s002", "Confirm", autofill=[email], reach_path=[{"screen": "s001"}])
    events = [
        {"step": 3, "type": "change_on_input", "screen": "s001", "detail": "typing into Search opened s002"}
    ]
    rep = audit_run(make_run(tmp_path, [(s1, hierarchy()), (s2, hierarchy())], events=events))
    assert {"redundant-entry", "change-on-input"} <= rules_of(rep)
    red = next(i for i in rep["issues"] if i["rule"] == "redundant-entry")
    assert red["screen"] == "s002" and red["kind"] == "review"


def test_review_flags_auth_dragging_title_and_orientation(tmp_path):
    xml = hierarchy(
        node("android.widget.EditText", (0, 300, 1000, 420), password=True, focusable=True, hint="Password"),
        node("android.widget.SeekBar", (0, 600, 1000, 680), focusable=True),
    )
    rep = audit_run(
        make_run(
            tmp_path,
            [(_screen("s001", title="MainActivity"), xml)],
            app_extra={"orientation_locked": {ACT: "portrait"}},
        )
    )
    assert {"auth-cognitive", "dragging", "screen-title", "orientation-locked"} <= rules_of(rep)


def test_focus_obscured_by_sticky_bottom_bar(tmp_path):
    bar = node(
        bounds=(0, 2300, 1080, 2400),  # 100 dp tall bar pinned to the bottom
        children=[btn((0, 2310, 300, 2390), desc="Home"), btn((300, 2310, 600, 2390), desc="Saved")],
    )
    content = node(
        bounds=(0, 0, 1080, 2400), scrollable=True, children=[btn((100, 2320, 500, 2380), text="Load more")]
    )
    rep = audit_run(make_run(tmp_path, [(_screen("s001"), hierarchy(content, bar))]))
    hit = [i for i in rep["issues"] if i["rule"] == "focus-obscured"]
    assert [i["label"] for i in hit] == ["Load more"]


def test_triage_from_notes_and_formatting(tmp_path):
    xml = hierarchy(btn((0, 500, 400, 620), focusable=False, text="Next"))
    run = make_run(tmp_path, [(_screen("s001"), xml)])
    key = next(i["key"] for i in audit_run(run)["issues"] if i["rule"] == "not-focusable")
    (run / "notes.json").write_text(
        json.dumps({"appscreenmap_notes": 1, "notes": {}, "a11y": {key: {"status": "false_positive"}}})
    )
    rep = audit_run(run)
    assert next(i for i in rep["issues"] if i["key"] == key)["triage"] == "false_positive"
    assert "2.1.1" not in format_audit(rep, "AA")  # triaged as false positive → hidden


def test_every_rule_names_a_wcag22_criterion():
    new_in_22 = {"2.4.11", "2.5.7", "2.5.8", "3.2.6", "3.3.7", "3.3.8"}
    assert new_in_22 <= {r.sc for r in RULES.values()}
    assert all(r.level in ("A", "AA", "AAA") and r.kind in ("automated", "review") for r in RULES.values())


def test_parse_manifest_orientation():
    tree = """N: android=http://schemas.android.com/apk/res/android
  E: manifest (line=2)
    A: package="com.example.app" (Raw: "com.example.app")
      E: activity (line=10)
        A: http://schemas.android.com/apk/res/android:name(0x01010003)=".Main" (Raw: ".Main")
        A: http://schemas.android.com/apk/res/android:screenOrientation(0x0101001e)=1
          E: intent-filter (line=12)
            A: http://schemas.android.com/apk/res/android:name(0x01010003)="x"
      E: activity (line=20)
        A: http://schemas.android.com/apk/res/android:name(0x01010003)="com.example.app.Free" (Raw: "x")
"""
    acts = parse_manifest_activities(tree)
    assert acts == [
        {"name": "com.example.app.Main", "orientation": 1},
        {"name": "com.example.app.Free", "orientation": None},
    ]


# ── report ──────────────────────────────────────────────────────────────────


def _report_run(tmp_path, notes=None, font_scale=1.0):
    from PIL import Image

    nav = node(
        bounds=(0, 2300, 1080, 2400),
        children=[
            node(
                "android.view.View",
                (i * 270, 2310, i * 270 + 260, 2390),
                clickable=True,
                focusable=True,
                children=[node(bounds=(i * 270 + 100, 2320, i * 270 + 160, 2380), desc=d)],
            )
            for i, d in enumerate(["Home", "Saved", "Search", "Profile"])
        ],
    )
    screens = [(_screen(f"s00{i}", title=f"Screen {i}"), hierarchy(nav)) for i in (1, 2)]
    run = make_run(tmp_path, screens)
    data = json.loads((run / "map.json").read_text())
    data["run"]["device"]["font_scale"] = font_scale
    for s in data["screens"]:
        s["screenshot"] = s["thumb"] = f"screens/{s['id']}.png"
        Image.new("RGB", (1080, 2400), "white").save(run / s["screenshot"])
    (run / "map.json").write_text(json.dumps(data))
    if notes:
        (run / "notes.json").write_text(json.dumps({"appscreenmap_notes": 1, "notes": {}, "a11y": notes}))
    return run


def test_report_groups_repeated_elements_and_marks_untested(tmp_path):
    from appscreenmap.a11y_report import build_model

    m = build_model(_report_run(tmp_path))
    groups = m["findings_by_sc"]["4.1.2"]
    assert len(groups) == 4  # four nav items, each on two screens
    assert all(g["screens"] == ["s001", "s002"] and g["instances"] == 2 for g in groups)
    rows = {r["sc"]: r for r in m["rows"]}
    assert rows["4.1.2"]["status"] == "review"  # info-level automated → needs review
    assert rows["1.4.4"]["status"] == "not_tested" and "font-scale" in rows["1.4.4"]["note"]
    assert rows["1.3.4"]["status"] == "not_tested"  # manifest not read
    assert rows["2.5.3"]["status"] == "pass_auto"
    assert rows["1.4.3"]["status"] == "viewer"
    assert rows["1.2.2"]["status"] == "not_tested"
    assert len(m["rows"]) == 55  # all WCAG 2.2 A + AA criteria
    assert sum(m["status_counts"].values()) == 55


def test_report_imports_confirmed_viewer_findings_and_font_scale_pass(tmp_path):
    from appscreenmap.a11y_report import build_model

    notes = {
        "s001::contrast::TextView::Fine print::40,600": {"status": "confirmed", "note": "2.9:1"},
        "s001::label-missing::ImageView::ImageView::10,10": {"status": "false_positive"},
        "s002::touch-target::View::Home::270,2310": {"status": "confirmed"},
    }
    m = build_model(_report_run(tmp_path, notes, font_scale=2.0))
    rows = {r["sc"]: r for r in m["rows"]}
    assert rows["1.4.3"]["status"] == "fail"
    assert m["findings_by_sc"]["1.4.3"][0]["detail"].endswith("(2.9:1)")
    assert rows["4.1.2"]["status"] == "review"  # the false-positive viewer finding is not imported
    assert [f["rule"] for f in m["best_practice"]] == ["touch-target"]  # 48 dp is a guideline, not WCAG
    assert rows["1.4.4"]["status"] == "pass_auto" and m["viewer_imported"] == 2


def test_reports_render(tmp_path):
    from appscreenmap.a11y_report import write_reports

    run = _report_run(tmp_path)
    out = write_reports(run)
    page = Path(out["html"]).read_text()
    assert page.startswith("<!doctype html>") and "not a conformance claim" in page
    assert "data:image/jpeg;base64," in page and "4.1.2 Name, Role, Value" in page
    md = Path(out["md"]).read_text()
    assert "| 2 screens: s001, s002 | Home |" in md and (run / "a11y" / "crops" / "001.jpg").is_file()
