# appscreenmap-core

The base every other package builds on. It imports nothing else from the repo.

| Module | What |
|---|---|
| `appscreenmap.core.model` | `map.json` read/write: `AppMap`, `Screen`, `Element`, `Transition` (the contract with the viewer, see `docs/MAP_SCHEMA.md`) |
| `appscreenmap.core.analyzer` | hierarchy XML → nodes, elements, screen signatures, UI patterns |
| `appscreenmap.core.config` | `CrawlConfig` and `appscreenmap.toml`, secret placeholders |
| `appscreenmap.core.runs` | run folders, `runs/index.json`, resolving a run id |
| `appscreenmap.core.notes` | viewer notes and triage (`notes.json`) |
| `appscreenmap.core.media` | screenshot thumbnails |

`appscreenmap.core.__version__` is the product version.
