# Demo tab (first-time user)

Spec for the viewer session (`apps/viewer/`). The engine side is done; nothing here edits the viewer.

## Goal

A first-time user opens the dashboard with an empty `runs/` and sees how AppScreenMap works on one real,
finished sample, with no emulator and no setup.

## The sample

`samples/demo-runs/` is a runs folder (same layout and `index.json` as `runs/`) holding one run:
`playground/playground-20261015-011121`, a 25-step crawl of the Android Playground v1 (7 screens, 17 transitions,
7 Maestro flows, 45 a11y findings, 1.6 MB). It is the only sample committed; every other run stays git-ignored.
Regenerate it with a crawl of `samples/playground-app/apk/playground-v1.apk`, copy the run folder, then re-index:
`update_index(Path("samples/demo-runs"))` (`appscreenmap.core.runs`).

## Serving it

- `appscreenmap serve --runs samples/demo-runs` already shows it (runs resolve by flat run id).
- Proposed engine flag, not built yet: `serve --demo`, or the Demo tab reading a second runs root, so the sample
  appears next to the user's own runs without being copied into `runs/`. In a release, `samples/demo-runs/`
  would ride along in the viewer bundle (`viewer-<version>.tar.gz`) or as its own release file.

## The tab

- Shown first when `runs/index.json` has no runs; after that it sits last in the nav and can be hidden.
- Content, top to bottom: one sentence on what the tool does; the sample's map (reuse the existing How it works
  view, which already reads a run); three steps with the command for each (`appscreenmap crawl`, `report`, `serve`);
  a link into the sample's Accessibility and Insights tabs; "Crawl your own app" opens the Crawl tab.
- Mark everything from the sample "sample data", like the sample audits.
- Follow the `design-system` and `web-ui` skills; mock up before code.

## Open

- Whether to replace the 25-step run with a fuller one (about 60 steps reaches Profile and Reports).
- Whether the iOS Playground gets its own demo run once its tab bar is crawlable (`samples/playground-ios/README.md`).
