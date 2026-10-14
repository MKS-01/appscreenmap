# @appscreenmap/cli

The `appscreenmap` command (Bun + [Ink](https://github.com/vadimdemedes/ink), compiled to one binary). With no
arguments it opens a **terminal home**: it starts the dashboard and opens it in your browser, shows what's connected
(Android devices, booted iOS simulators), lists your runs, and suggests the next command or agent prompt. Every other
command goes to the Python engine unchanged, so `appscreenmap crawl …` behaves exactly as before. Built and tested on
macOS for now (Terminal, iTerm2); the Linux code paths exist but aren't tested.

```bash
appscreenmap                 # terminal home + dashboard (same as `appscreenmap start`)
appscreenmap start --runs runs --port 8765 --no-open
appscreenmap setup           # install or repair: uv (asks first), the engine, the dashboard
appscreenmap update          # newest release's cli, engine and dashboard (--check: only report; or name one part)
appscreenmap paths           # where things live
appscreenmap clean           # old dashboard versions, download cache, old logs (--runs: old runs too; asks first)
appscreenmap version         # CLI, engine, dashboard and map schema versions
appscreenmap crawl --apk app.apk --clear-data   # … and every other engine command
```

## Install

From a release (macOS; the first release isn't published yet):

```bash
curl -fsSL https://github.com/MKS-01/appscreenmap/releases/latest/download/install.sh | sh
```

`install.sh` puts the binary in `~/.local/bin` (checked against the release's `SHA256SUMS`) and runs `appscreenmap
setup`, which installs the engine as a uv tool from the release's wheels and the dashboard into the home folder. From a
source checkout: `make setup`, then `make cli`.

**Home folder** (`~/Library/Application Support/appscreenmap`, or `$APPSCREENMAP_HOME`): `config.json`
(`updateCheck`, `releaseUrl`), `viewer/<version>/` with a `current` link, `cache/` (downloads, the daily update check),
and `dashboard.json` (the dashboard this CLI started, so a second terminal home reuses it only for the same runs
folder, and one left behind by a killed terminal home is stopped on the next start).

**Updates.** The terminal home checks the release at most once a day and only shows a notice; it never installs by
itself. Off with `APPSCREENMAP_NO_UPDATE_CHECK=1`, in CI, or `"updateCheck": false`. A dashboard is installed only if it
reads this CLI's map schema. In a source checkout, update with `git pull && make setup`.

**Releases** are a flat folder: `manifest.json` (versions and the SHA-256 of every file), `SHA256SUMS`, the macOS
binaries, the engine's wheels, `viewer-<version>.tar.gz` and `install.sh`. `make release-local` builds one in
`dist/release/`; point the CLI at it with `APPSCREENMAP_RELEASE_URL=file://…/dist/release/` to test `install.sh`,
`setup` and `update` without publishing anything.

| Key | In the terminal home |
|---|---|
| `1`–`4`, `←` `→` | Home · Crawl · Runs · Agent |
| `↑` `↓` | select a command or a run |
| `c` | copy the selected command |
| `x` / `s` | Crawl: run the selected command here (output in `runs/.logs/`) / stop it like Ctrl-C (the run is saved as `stopped`) |
| `↵` | Runs: open the run in the dashboard; elsewhere: copy |
| `o` | open the dashboard |
| `t` | open a new terminal window here for an agent session (macOS Terminal, iTerm2; elsewhere it copies `cd <dir>`) |
| `r` / `q` | refresh / quit (stops what this CLI started: a crawl saves first, then the dashboard) |

**Live crawls.** The Crawl tab follows whichever crawl is running in the runs folder, started here or by an agent in
another terminal: budget bar, step and time, screens, transitions, crashes, and the latest steps with screen titles
and outcomes (★ new screen, → known, · same screen, ↗ left the app, ✘ crash). It reads what the engine already writes
(`runs/index.json`, the run's `map.json` and `trace.jsonl`) once a second, so no engine change or event stream is
needed. A run starting or finishing shows on the bottom line from any tab. In a source checkout the first Crawl entry
is a ready-to-run Playground crawl.

**The dashboard** is the engine's `serve` (viewer, `runs/`, the notes endpoint), run in the background: one
implementation of that contract, in the engine. A dashboard already running on the port is reused; a busy port moves
to the next free one.

**Finding the engine**, in order: `$APPSCREENMAP_ENGINE` (a command line), the checkout this CLI was built from
(`uv run --project <checkout> appscreenmap-engine`; `make cli` bakes the path into the binary), then
`appscreenmap-engine` on `PATH`.

**Colours** come from `@appscreenmap/design-tokens` (`src/theme.ts` reads `tokens.css` at build time), with the
dashboard's rules: blue only for what you can act on, status always with a word or glyph.

## Develop

```bash
bun run dev                  # from source (bun run dev -- start --no-open, bun run dev -- version, …)
bun test && bun run typecheck
make cli                     # from the repo root: dist/appscreenmap, wired to this checkout's engine
make release-local           # from the repo root: dist/release/, to test install.sh, setup and update
```

`react-devtools-core` is a dev dependency only so the binary compiles (Ink imports it for `DEV=true`).
