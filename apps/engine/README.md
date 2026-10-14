# appscreenmap-engine

`appscreenmap.engine`: the command line and the MCP server, on top of every package in `packages/`.

| Module | Commands |
|---|---|
| `engine.cli.crawl` | `doctor`, `crawl` |
| `engine.cli.verify` | `export`, `diff`, `verify` |
| `engine.cli.analyse` | `report`, `perf`, `a11y` |
| `engine.cli.security` | `security` |
| `engine.cli.serve` | `serve` (viewer + notes endpoint), `mcp` |
| `engine.mcp_server` | the MCP tools behind `appscreenmap mcp` |

Each `cli` module holds its `cmd_*` functions and a `register(sub)` that adds their parsers; `cli/__init__.py`
only builds the parser from `GROUPS` and runs the command. The CLI parses and prints; logic lives in the packages.

It installs two commands, `appscreenmap-engine` and, until the Bun CLI in `apps/cli` takes the name, `appscreenmap`
(also `python -m appscreenmap.engine`). From the repo root: `uv sync`, then `uv run appscreenmap --help`.
Layout and plan: [docs/MONOREPO.md](../../docs/MONOREPO.md).
