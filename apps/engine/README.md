# appscreenmap-engine

The Python engine behind AppScreenMap: the `crawl`, `a11y`, `security`, `perf`, `report`, `verify`, `diff`,
`export`, `serve` and `mcp` commands. It installs two commands, `appscreenmap-engine` and, until the Bun CLI in
`apps/cli` takes the name, `appscreenmap`.

From the repo root: `uv sync`, then `uv run appscreenmap --help`. Layout and plan: [docs/MONOREPO.md](../../docs/MONOREPO.md).
