"""Turn an iOS accessibility tree (from `idb ui describe-all`) into the uiautomator-style XML the analyzer reads.

The explorer, analyzer, exporters and viewer were written against Android's hierarchy. Rather than fork them,
the iOS driver translates what VoiceOver sees into the same shape: class names the analyzer already recognises,
`resource-id` from the accessibility identifier, `bounds` in points. Everything downstream then works unchanged.

What iOS exposes is what an assistive-technology user gets, so the tree is also an accessibility signal: a control
with no label or identifier simply isn't there (see tests/test_ios_hierarchy.py: the floating tab bar).
"""

from __future__ import annotations

from xml.sax.saxutils import quoteattr

# idb element type → the Android class the analyzer keys its kinds and patterns on.
_CLASS = {
    "Application": "android.widget.FrameLayout",
    "Window": "android.widget.FrameLayout",
    "StaticText": "android.widget.TextView",
    "Button": "android.widget.Button",
    "Link": "android.widget.Button",
    "Tab": "android.widget.Button",
    "TextField": "android.widget.EditText",
    "SecureTextField": "android.widget.EditText",
    "TextView": "android.widget.EditText",
    "SearchField": "android.widget.EditText",
    "Switch": "android.widget.Switch",
    "Toggle": "android.widget.Switch",
    "CheckBox": "android.widget.CheckBox",
    "Slider": "android.widget.SeekBar",
    "Image": "android.widget.ImageView",
    "Icon": "android.widget.ImageView",
    "ScrollView": "android.widget.ScrollView",
    "Table": "android.widget.ListView",
    "CollectionView": "androidx.recyclerview.widget.RecyclerView",
    "List": "android.widget.ListView",
    "Cell": "android.view.ViewGroup",
    "WebView": "android.webkit.WebView",
    "TabBar": "android.widget.LinearLayout",
    "NavigationBar": "android.widget.LinearLayout",
    "Toolbar": "android.widget.LinearLayout",
}
_CLICKABLE = {"Button", "Link", "Tab", "Cell", "Switch", "Toggle", "CheckBox", "MenuItem"}
_SCROLLABLE = {"ScrollView", "Table", "CollectionView", "List"}
_CHECKABLE = {"Switch", "Toggle", "CheckBox"}
_EDITABLE = {"TextField", "SecureTextField", "TextView", "SearchField"}


def element_type(node: dict) -> str:
    """idb's `type`, falling back to the AX role with its `AX` prefix removed."""
    return node.get("type") or str(node.get("role") or "").removeprefix("AX") or "Other"


def _frame(node: dict) -> tuple[float, float, float, float]:
    f = node.get("frame") or {}
    return float(f.get("x", 0)), float(f.get("y", 0)), float(f.get("width", 0)), float(f.get("height", 0))


def _clip(frame, width: int, height: int) -> tuple[int, int, int, int] | None:
    x, y, w, h = frame
    x1, y1, x2, y2 = max(0.0, x), max(0.0, y), min(float(width), x + w), min(float(height), y + h)
    if x2 <= x1 or y2 <= y1:
        return None  # off screen, or zero-sized: idb lists the whole scroll content, uiautomator only what's drawn
    return round(x1), round(y1), round(x2), round(y2)


def _checked(node: dict) -> bool:
    return str(node.get("AXValue") or "").strip().lower() in {"1", "on", "true", "checked", "selected"}


def idb_to_xml(nodes: list[dict], width: int, height: int, bundle_id: str) -> str:
    """`nodes` is idb's flat `describe-all` output (the first entry is the application). Returns hierarchy XML."""
    rows = []
    for n in nodes:
        t = element_type(n)
        if t == "Application":
            continue
        box = _clip(_frame(n), width, height)
        if box is None:
            continue
        traits = set(n.get("traits") or [])
        label = (n.get("AXLabel") or "").strip()
        value = n.get("AXValue")
        value = value.strip() if isinstance(value, str) else ""
        ident = (n.get("AXUniqueId") or "").strip()
        editable = t in _EDITABLE
        clickable = t in _CLICKABLE or "Button" in traits or "Link" in traits
        # Text fields: the typed text is the value; the label is what names the field (Android's hint).
        text = (value or "") if editable else label
        hint = label if editable else ""
        attrs = {
            "index": str(len(rows)),
            "text": text,
            "resource-id": f"{bundle_id}:id/{ident}" if ident else "",
            "class": _CLASS.get(t, "android.view.View"),
            "package": bundle_id,
            "content-desc": "",
            "hint": hint,
            "checkable": "true" if t in _CHECKABLE else "false",
            "checked": "true" if t in _CHECKABLE and _checked(n) else "false",
            "clickable": "true" if clickable else "false",
            "enabled": "false" if ("NotEnabled" in traits or n.get("enabled") is False) else "true",
            "focusable": "true" if clickable or editable else "false",
            "long-clickable": "false",
            "password": "true" if t == "SecureTextField" else "false",
            "scrollable": "true" if t in _SCROLLABLE else "false",
            "selected": "true" if "Selected" in traits else "false",
            "bounds": "[{},{}][{},{}]".format(*box),
        }
        rows.append("  " + "<node " + " ".join(f"{k}={quoteattr(v)}" for k, v in attrs.items()) + " />")

    root = (
        f'<node index="0" text="" resource-id="" class="android.widget.FrameLayout" package={quoteattr(bundle_id)} '
        'content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" '
        'long-clickable="false" password="false" scrollable="false" selected="false" '
        f'bounds="[0,0][{width},{height}]">'
    )
    return (
        "<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>\n<hierarchy rotation=\"0\">\n"
        + root
        + "\n"
        + "\n".join(rows)
        + "\n</node>\n</hierarchy>"
    )


def is_out_of_process(nodes: list[dict]) -> bool:
    """True when the screen is something the accessibility tree can't see into.

    An in-app browser (SFSafariViewController), a system sheet or a share extension runs in another process, so the
    tree is just the host application's one node. The crawler must treat that as leaving the app, not as a blank screen.
    """
    return len([n for n in nodes if element_type(n) != "Application"]) == 0


_TAB_TYPES = {"Tab", "RadioButton"}


def collapsed_tab_bar(nodes: list[dict]) -> tuple[float, float, float, float] | None:
    """The frame of a tab bar that `describe-all` listed without its tabs, else None.

    idb returns a UITabBar as one "Tab Bar" group; its tab buttons (`RadioButton`, subrole `AXTabButton`) exist and
    `describe-point` finds them, but they are missing from the list, so a crawl would never leave the first tab."""
    for bar in nodes:
        if bar.get("AXLabel") != "Tab Bar" and element_type(bar) != "TabBar":
            continue
        bx, by, bw, bh = _frame(bar)
        if bw <= 0 or bh <= 0:
            continue
        for n in nodes:
            x, y, w, h = _frame(n)
            if (
                n is not bar
                and element_type(n) in _TAB_TYPES
                and bx <= x + w / 2 <= bx + bw
                and by <= y + h / 2 <= by + bh
            ):
                break
        else:
            return bx, by, bw, bh
    return None


def tab_from_point(node: dict | None) -> dict | None:
    """A tab button found by `describe-point`, as the `Tab` node the rest of the pipeline understands."""
    if not node or not (node.get("subrole") == "AXTabButton" or "TabButton" in (node.get("traits") or [])):
        return None
    selected = str(node.get("AXValue")).strip().lower() in {"1", "true"}
    return {
        "type": "Tab",
        "AXLabel": node.get("AXLabel"),
        "AXUniqueId": node.get("AXUniqueId"),
        "frame": node.get("frame"),
        "traits": ["Button", "Selected"] if selected else ["Button"],
        "pid": node.get("pid"),
    }
