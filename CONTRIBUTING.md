# Contributing to AppScreenMap

Thanks for helping. AppScreenMap is MIT-licensed and early alpha, so small, focused changes are the easiest to land.

## Set up

```bash
git clone https://github.com/MKS-01/appscreenmap && cd appscreenmap
uv sync                                   # Python 3.11+, crawler and tests
cd web && bun install && cd ..            # web viewer (Bun, not npm)
```

You don't need a device to develop: the crawler's tests run on synthetic hierarchies and a fake device.
To try a real crawl you need `adb` and an Android emulator, or on macOS a booted iOS Simulator with `idb`
(`uv run appscreenmap doctor` checks both). The [sample apps](samples/README.md) are the easiest targets.

## Before you open a PR

```bash
uv run pytest -q
uv run ruff check && uv run ruff format
cd web && bun run build                   # tsc + vite must pass
```

Or `make check` (Python lint + tests) and `make viewer`; `make` targets cover setup, tests, lint and the demo.

CI runs the same checks.

## Where things live

| Area | Path | Notes |
|---|---|---|
| Crawler (Python) | `apps/engine/src/appscreenmap/` | Drivers (Android, iOS Simulator) → analyzer → explorer → model → export/report → CLI |
| Web viewer | `web/` | React + TypeScript + Vite. UI rules: [`web/DESIGN.md`](web/DESIGN.md) |
| Design tokens | `design/tokens.css` | Colour, type, space and motion shared by the viewer and the HTML reports |
| Data contract | `docs/MAP_SCHEMA.md` | `map.json` is the interface between crawler and viewer |
| Setup and architecture | `docs/SETUP.md`, `docs/ARCHITECTURE.md` | Commands, platforms, how the crawl works |
| Design and roadmap | `docs/PLAN.md` | |
| Sample apps | `samples/` | Playground and sample-app, with `demo.sh` to crawl them |

## Ground rules

- **`map.json` schema 1 is additive.** Add fields; don't rename or remove them. Update `docs/MAP_SCHEMA.md`
  and `web/src/types.ts` in the same change.
- **Exploration fixes need a regression test** built from a synthetic hierarchy (`packages/testkit/src/appscreenmap/testkit/helpers.py`) before you
  re-crawl a real app.
- **The crawl must stay inside the target app.** Don't add recovery that presses BACK out of the app or opens
  other apps.
- **UI changes follow the design system:** tokens in `design/tokens.css` (never a hard-coded colour), components
  and motion rules in `web/DESIGN.md`, live reference at `#/design`. The viewer is dark only; check 1400 px and
  390 px wide.
- **Don't commit secrets or private app data.** Crawls record text typed into forms and screenshots of whatever
  the app shows. Use throwaway test accounts. `runs/` is git-ignored; keep it that way, and don't
  share a run of an app you don't have the right to publish screenshots of.

## Commits and PRs

Keep PRs small and say what you verified (tests, a crawl on an emulator, screenshots for UI). Describe the
user-visible change first. For larger features, open an issue to discuss the approach before building it.

## Reporting bugs and ideas

Use the issue templates. For crawl problems, include the platform (Android or iOS Simulator) and its OS version,
the emulator or device, the `appscreenmap --version`, and the output of `appscreenmap report <run>` if you have a run.

## Security

See [SECURITY.md](SECURITY.md). Please don't file vulnerabilities as public issues.

## Conduct

Be kind and constructive. See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## License

By contributing you agree your contribution is licensed under the project's [MIT license](LICENSE).
