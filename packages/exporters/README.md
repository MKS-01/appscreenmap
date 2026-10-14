# appscreenmap-exporters

Turns a map into files other tools read. Depends on `core`.

| Module | What |
|---|---|
| `appscreenmap.exporters.maestro` | `maestro_flow`: one Maestro flow per screen that replays its path and asserts arrival |
| `appscreenmap.exporters.mermaid` | `mermaid`: a flowchart of every screen and transition |
| `appscreenmap.exporters.export` | `export_run`: writes all of them for a run (`flows/`, `map.mmd`) |

A new format (Appium, Espresso, …) is a module here plus a line in `export_run`; see the `add-exporter` skill.
