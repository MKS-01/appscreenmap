# Handoff → viewer session: Network & Logs (variant A)

From the crawler session, 2026-10-22. Branch `mitmproxy-network`. This is `docs/PLAN.md` §8.5 stage 5, and it is next
for `apps/viewer/`. Delete this file once it ships: the plan entry and `docs/MAP_SCHEMA.md` stay the homes of these facts.

**Design:** canvas "AppScreenMap redesign", artboard **Variant A · Network & Logs per screen**
(https://claude.ai/artifact/4SFYfivAGfxggUnZyrvKKq#artboard-1b0bc4e14014). Variant B (run console + replay) is for later.
Build it through the `web-ui` skill and the tokens in `packages/design-tokens/tokens.css`. The artboard's hexes
are drawn from those tokens: use the tokens, never the hexes.

## What to build

**One button, two ways.** The logger must be one click away from wherever the developer is, so the run header gets
a **Network · Logs** button (with its count). It opens one panel with two modes, using the same table and log list in both:

| Mode | Rows | Follows |
|---|---|---|
| **Replay** | the crawl's captures (`network.jsonl` / `logs.jsonl` of the run or canvas scenario) | the Replay tab's current step: stepping to a screen scrolls to that screen's rows (e.g. replay the Profile flow and see what Profile called) |
| **Debug** (manual) | a `watch` session's rows | live while a session is recording (poll the files as they grow, as Replay follows a live crawl); a past session when one is picked from Sessions |

In Debug mode a **Start debugging** button starts a manual session and **Stop** ends it (done 2026-10-22, `serve`
only, local pages only):

```jsonc
POST /api/sessions  {"run": "<canvas id>", "network": true, "serial"?: "emulator-5554"}
  201 → session.json + "path", "stoppable": true   // status "recording"; then poll its files as they grow
  409 → {"error": "a session is already recording: <id>"}   // one at a time: say so, offer that session's Stop
  422 → {"error": "…"}   // no device, no mitmproxy (the error names `uv tool install mitmproxy`), watch failed
POST /api/sessions/<id>/stop
  200 → the final session.json (status "done", rows now tied to screens)   404 → not recording from this dashboard
```

`/api/captures` marks each session `"stoppable": true` while this dashboard is recording it. Show Stop only then. A
session started from the terminal (`appscreenmap watch`) shows as `recording` but can only be stopped there, so say
that instead of showing Stop. Starting a session changes the device's proxy setting until Stop, so the button says
so in one line. With a static host (no `serve`), show the command to copy: `appscreenmap watch <canvas> --network`.

1. **Screen detail: Network and Logs tabs** (`views/ScreenDetail.tsx`, beside Elements · Accessibility · Transitions …).
   Each tab shows its row count, and appears only when the run has captures (below).
   - **Network**: the artboard's heading and stat line (requests, hosts, cleartext, slowest), the
     "measured at the proxy · bodies and header values are never stored" note, then the table: STATUS · REQUEST · SIZE ·
     TIME. A selected row opens the detail panel (query keys, content type, source, "Body: not stored, by design").
   - **Logs**: the app's own lines while the screen was showing: time · level · tag · message, in mono.
     `warn`/`error`/`fatal` use the warn/bad tokens. Masked values (`••••`, `[jwt · sha 3f9a1c2e]`) render as faint
     text, as drawn.
2. **Hosts strip** at the foot of the Network tab: one chip per host with its flags (HTTP for cleartext, failures).
   Clicking a chip filters the table to that host.
3. **Entry points** (today nothing in the UI leads to app logs, and the top bar's Logs page is the engine's own
   command log, so don't reuse that name for this):
   - the run page gets a **Network · Logs** link when `/api/captures` reports any capture, opening a run-level view
     with the same table and log list (every row, with a Screen column) and the full hosts strip;
   - a **Sessions** list for `watch` recordings (date, duration, screens visited, line and host counts). Opening one
     shows its timeline of screens, then its rows.

## Data (all exists today; row formats are in `docs/MAP_SCHEMA.md`, not repeated here)

- `GET /api/captures?run=<run-id>`, served by `appscreenmap serve` only:
  ```jsonc
  { "run": "<id>",
    "network": { "log": "network.jsonl", "events": 33,
                 "hosts": [{ "host", "requests", "tunnels", "cleartext", "failed" }],   // busiest first
                 "cleartext_hosts": ["cdn.playground.test"] } | null,
    "logs": { "log": "logs.jsonl", "lines": 42 } | null,
    "sessions": [{ ...session.json, "network": {…} | null, "logs": {…} | null, "path": "sessions/<id>" }] }  // newest first
  ```
  A 404 (static hosting, an old engine) means no captures: hide every entry point, never show an error.
- The rows themselves are plain files: `/runs/<run-id>/network.jsonl`, `/runs/<run-id>/logs.jsonl`, and
  `/runs/<run-id>/<session path>/{network,logs,timeline}.jsonl`. Skip any line without `"asm": 1`.
- On a canvas, crawl rows carry `scenario` (`run.scenarios[].network` / `.logs` hold that scenario's summary).
  Session rows carry `screen` and `screen_title`. Their screen ids are the canvas's ids (`session.json.run`).

## Rules the UI must keep

- **Say "not seen", never "none".** The proxy sees only traffic that uses the system proxy. An empty Network tab
  reads "Nothing seen on this screen", plus one line that apps that bypass the proxy leave no rows.
- **Every timing is proxy-measured**, and labelled so. A request's time is `t_end - t`. A `connect` row has no
  duration: show it as `CONNECT` · host only, as the artboard's TLS row does.
- Network `t` is the host clock and log `t` is the device clock. Show times relative to the session start, or to the
  screen's arrival, and never mix the two lists into one sorted timeline (that is variant B, later).
- **Show only fields that are present.** The artboard draws later stages: the DNS/connect/TLS/TTFB phase bar, GraphQL
  operation names, TLS version and pinning (stage 6), the 1st/3rd-party label and "N screens" per host
  (`audits/network.json`, stage 2), HAR export (stage 7). Render each only when its field exists, and leave no
  placeholder, so the UI fills in as the engine adds them. The data is additive within schema 1.
- Status cell: `request` with `status` → the code (warn colour when `scheme` is `http`); `request` with `error`, or
  `connect_failed` → **FAILED** (bad token), with the error as its title. The artboard has no failed state, so draw one.
  The Playground's sample hosts never resolve, so every row of the known-answer run looks like this.
- Rows hold metadata only. Never render or fetch anything beyond these files.

## Known gaps on the engine side (not for the viewer to work around)

- **Crawl rows carry `screen`, `screen_title` and `step` (stage 3, done 2026-10-22)** for crawls from that date on.
  Older rows (the canvas's `sc2`) have none: list those under the run-level view by scenario only. Don't attribute
  them in the viewer from timestamps. Per-screen totals and the slowest request are in `perf.json` → `network`.
- `request` rows may carry `timing` (`connect`, `tls`, `send`, `wait`, `receive` ms): that's the artboard's phase bar.
- The capture is device-wide, so a crawl also records the emulator's own Google traffic (`*.googleapis.com`). Show
  it as captured. Filtering it is engine work.

## Test data

`runs/playground/playground-v1-20261013-031007` (git-ignored, local). Scenario `sc3` ("Network check v2 --network"):
8 rows and 4 `PlaygroundNet` log lines, all on `s044 Network check` at step 234, so it's the per-screen and Replay case.
Scenario `sc2` ("Network check v1 --network") has 33
network rows. Five are the Playground's own hosts: `api.playground.test` (failed), `cdn.playground.test` (http, failed,
cleartext), `events.tracker.test` (failed). Session `session-20261022-003638` has 3 log lines and 2 network rows on
`s021 Discover`.

## Done when

1. With `appscreenmap serve` on, the canvas above shows a Network · Logs link, and its run-level view lists all 41 rows (33 in `sc2`, 8 in `sc3`),
   with `cdn.playground.test` flagged HTTP and the `.test` hosts as FAILED.
2. The session is listed under Sessions. `s021`'s Network tab shows its row and its Logs tab its 3 lines.
3. A run with no captures, and the viewer on a static host, show no Network or Logs entry points and no errors.
4. An empty tab says "Nothing seen…", not "No requests".
5. Fields from later stages render when present and leave no placeholder when absent.
6. From any run page, the logger is one click away. In Replay mode, stepping onto a screen shows that screen's rows.
   Replaying `sc3` onto `s044 Network check` shows its 8 rows and 4 log lines. In Debug mode, Start → use the app → Stop shows the new session live, then lists it under Sessions.
7. `bun run build` in `apps/viewer` passes. Screenshots in dark at desktop and 390 px (`shot.ts`), reviewed by
   `design-reviewer` against the artboard.
