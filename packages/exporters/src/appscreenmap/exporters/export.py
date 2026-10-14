"""Write every export for a run: Maestro flows in `flows/` and `map.mmd`."""

from __future__ import annotations

from pathlib import Path

from appscreenmap.core.model import load_map

from .maestro import maestro_flow
from .mermaid import mermaid


def export_run(run_dir: str | Path) -> dict:
    run_dir = Path(run_dir)
    data = load_map(run_dir)
    flows = run_dir / "flows"
    flows.mkdir(exist_ok=True)
    count, skipped = 0, []
    for s in data["screens"]:
        if s["kind"] != "app":
            continue
        if s.get("origin") == "unknown":
            skipped.append(s["id"])  # no recorded path: a flow would only launch the app
            (flows / f"{s['id']}.yaml").unlink(missing_ok=True)
            continue
        (flows / f"{s['id']}.yaml").write_text(maestro_flow(data, s))
        count += 1
    (run_dir / "map.mmd").write_text(mermaid(data))
    return {"flows": count, "skipped": skipped, "mermaid": str(run_dir / "map.mmd")}
