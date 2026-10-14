# @appscreenmap/cli

The `appscreenmap` command (Bun + [Ink](https://github.com/vadimdemedes/ink), compiled to one binary). With no
arguments it opens a **terminal home**: it starts the dashboard and opens it in your browser, shows what's connected
(Android devices, booted iOS simulators), lists your runs, and suggests the next command or agent prompt. Every other
command goes to the Python engine unchanged, so `appscreenmap crawl …` behaves exactly as before. Built and tested on
macOS for now (Terminal, iTerm2); the Linux code paths exist but aren't tested.

```bash
appscreenmap                 # terminal home + dashboard (same as `appscreenmap start`)
appscreenmap start --runs runs --port 8765 --no-open
appscreenmap version         # CLI, engine and map schema versions
appscreenmap crawl --apk app.apk --clear-data   # … and every other engine command
```

| Key | In the terminal home |
|---|---|
| `1`–`4`, `←` `→` | Home · Crawl · Runs · Agent |
| `↑` `↓` | select a command or a run |
| `c` | copy the selected command |
| `↵` | Runs: open the run in the dashboard; elsewhere: copy |
| `o` | open the dashboard |
| `t` | open a new terminal window here for an agent session (macOS Terminal, iTerm2; elsewhere it copies `cd <dir>`) |
| `r` / `q` | refresh / quit (stops the dashboard if this CLI started it) |

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
```

`react-devtools-core` is a dev dependency only so the binary compiles (Ink imports it for `DEV=true`).
