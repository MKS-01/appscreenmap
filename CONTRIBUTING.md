# Contributing to AppScreenMap

Thanks for helping. AppScreenMap is MIT-licensed and early alpha, so small, focused changes are the easiest to land.

## Set up

```bash
git clone https://github.com/MKS-01/appscreenmap && cd appscreenmap
uv sync                                   # Python 3.11+, crawler and tests
cd web && bun install && cd ..            # web viewer (Bun, not npm)
```

You don't need a device to develop: the crawler's tests run on synthetic hierarchies and a fake device.
To try a real crawl you need `adb` and an emulator (`uv run appscreenmap doctor` checks).

## Before you open a PR

```bash
uv run pytest -q
uv run ruff check src tests && uv run ruff format src
cd web && bun run build                   # tsc + vite must pass
```

CI runs the same checks.

## Where things live

| Area | Path | Notes |
|---|---|---|
| Crawler (Python) | `src/appscreenmap/` | Driver → analyzer → explorer → model → export/report → CLI |
| Web viewer | `web/` | React + TypeScript + Vite. UI rules: [`web/DESIGN.md`](web/DESIGN.md) |
| Data contract | `docs/MAP_SCHEMA.md` | `map.json` is the interface between crawler and viewer |
| Design and roadmap | `docs/PLAN.md` | |

## Ground rules

- **`map.json` schema 1 is additive.** Add fields; don't rename or remove them. Update `docs/MAP_SCHEMA.md`
  and `web/src/types.ts` in the same change.
- **Exploration fixes need a regression test** built from a synthetic hierarchy (`tests/helpers.py`) before you
  re-crawl a real app.
- **The crawl must stay inside the target app.** Don't add recovery that presses BACK out of the app or opens
  other apps.
- **UI changes follow the design system:** tokens in `web/src/tokens.css`, components and motion rules in
  `web/DESIGN.md`, live reference at `#/design`. Check light and dark, 1400 px and 390 px wide.
- **Don't commit secrets or private app data.** Crawls record text typed into forms and screenshots of whatever
  the app shows. Review `runs/` before committing a new sample, and use throwaway test accounts.
- Sample runs in `runs/` are for the app this repo ships maps of. Don't add runs of apps you don't have the
  right to publish screenshots of.

## Commits and PRs

Keep PRs small and say what you verified (tests, a crawl on an emulator, screenshots for UI). Describe the
user-visible change first. For larger features, open an issue to discuss the approach before building it.

## Reporting bugs and ideas

Use the issue templates. For crawl problems, include the Android version, the emulator or device, the
`appscreenmap --version`, and the output of `appscreenmap report <run>` if you have a run.

## Security

See [SECURITY.md](SECURITY.md). Please don't file vulnerabilities as public issues.

## Conduct

Be kind and constructive. See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## License

By contributing you agree your contribution is licensed under the project's [MIT license](LICENSE).
