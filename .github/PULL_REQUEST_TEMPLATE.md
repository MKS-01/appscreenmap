## What and why

<!-- User-visible change first. Link the issue if there is one. -->

## How I checked it

- [ ] `uv run pytest -q`, `ruff check src tests`, `ruff format --check src`
- [ ] `cd web && bun run build`
- [ ] Crawled on an emulator (if the crawler changed): <!-- app, Android version -->
- [ ] Screenshots, light and dark, desktop and phone width (if the UI changed)

## Checklist

- [ ] `map.json` changes are additive, and `docs/MAP_SCHEMA.md` + `web/src/types.ts` are updated
- [ ] New exploration behaviour has a synthetic regression test
- [ ] No secrets or private app data in `runs/`, screenshots or logs
