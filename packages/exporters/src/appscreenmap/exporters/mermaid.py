"""A Mermaid flowchart of every screen and transition in map.json."""

from __future__ import annotations


def mermaid(data: dict) -> str:
    out = ["flowchart LR"]
    for s in data["screens"]:
        title = (s.get("title") or s["id"]).replace('"', "'")
        nid = s["id"].replace(":", "_").replace(".", "_")
        shape = f'{nid}(["{title}"])' if s["kind"] != "app" else f'{nid}["{s["id"]} · {title}"]'
        out.append(f"  {shape}")
    for t in data["transitions"]:
        a = t["from"].replace(":", "_").replace(".", "_")
        b = t["to"].replace(":", "_").replace(".", "_")
        label = (t.get("label") or t["action"]).replace('"', "'")[:30]
        out.append(f'  {a} -->|"{label}"| {b}')
    return "\n".join(out) + "\n"
