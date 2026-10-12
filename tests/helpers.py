"""Tiny builder for uiautomator-style hierarchy XML used across tests."""

from __future__ import annotations

from xml.sax.saxutils import quoteattr

PKG = "com.example.app"


def node(cls="android.view.View", bounds=(0, 0, 1080, 2400), children=(), **attrs) -> str:
    a = {
        "text": "",
        "resource-id": "",
        "class": cls,
        "package": PKG,
        "content-desc": "",
        "checkable": "false",
        "checked": "false",
        "clickable": "false",
        "enabled": "true",
        "focusable": "false",
        "scrollable": "false",
        "long-clickable": "false",
        "password": "false",
        "selected": "false",
        "hint": "",
        "bounds": "[{},{}][{},{}]".format(*bounds),
    }
    for k, v in attrs.items():
        key = {"rid": "resource-id", "desc": "content-desc", "long_clickable": "long-clickable"}.get(k, k)
        a[key] = ("true" if v else "false") if isinstance(v, bool) else str(v)
    head = "<node " + " ".join(f"{k}={quoteattr(v)}" for k, v in a.items())
    inner = "".join(children)
    return f"{head}>{inner}</node>" if inner else f"{head} />"


def hierarchy(*children: str) -> str:
    return (
        "<?xml version='1.0' encoding='UTF-8' standalone='yes' ?><hierarchy rotation=\"0\">"
        + node("android.widget.FrameLayout", children=children)
        + "</hierarchy>"
    )


def card(y: int, site: str, title: str) -> str:
    """A Compose-style feed card: clickable container with texts and a nested 'MORE' button."""
    return node(
        bounds=(42, y, 1038, y + 600),
        clickable=True,
        children=[
            node("android.widget.TextView", (84, y + 40, 900, y + 100), text=site),
            node("android.widget.TextView", (84, y + 140, 996, y + 260), text=title),
            node("android.widget.TextView", (882, y + 500, 1008, y + 580), text="MORE", clickable=True),
        ],
    )


def bottom_nav(selected: str | None = None) -> str:
    items = ["Home", "Following", "Saved", "Theme"]
    return node(
        bounds=(240, 2190, 840, 2340),
        children=[
            node(
                bounds=(250 + i * 140, 2200, 380 + i * 140, 2330),
                clickable=True,
                selected=(label == selected),
                children=[node(bounds=(290 + i * 140, 2240, 340 + i * 140, 2290), desc=label)],
            )
            for i, label in enumerate(items)
        ],
    )


def compose_home(
    greeting="Hello, Reader", cards=(("example.com", "First story"), ("blog.dev", "Second story"))
):
    """Compose LazyColumn flattened into leaf siblings, then cards, plus a bottom bar."""
    leaves = [
        node("android.widget.TextView", (42, 197, 900, 260), text=greeting),
        node("android.widget.ImageView", (931, 166, 1057, 292), desc="Settings", clickable=True),
        node("android.widget.TextView", (42, 330, 200, 370), text="FOCUS"),
        node("android.widget.TextView", (559, 396, 708, 522), text="15 MIN", clickable=True),
        node("android.widget.TextView", (724, 396, 873, 522), text="25 MIN", clickable=True),
        node("android.widget.TextView", (889, 396, 1038, 522), text="30 MIN", clickable=True),
        node("android.widget.TextView", (42, 600, 158, 642), text="LATEST"),
    ]
    feed = [card(700 + i * 640, site, title) for i, (site, title) in enumerate(cards)]
    scroller = node(bounds=(0, 121, 1080, 2180), scrollable=True, children=leaves + feed)
    return hierarchy(scroller, bottom_nav("Home"))
