# appscreenmap-regression

Compares builds. Depends on `core`, `drivers`, `crawler`.

| Module | What |
|---|---|
| `appscreenmap.regression.verify` | `verify_run`: replays every screen of a run on a new build and compares it with the baseline screenshot and text |
| `appscreenmap.regression.visual` | `diff_runs`, `compare_images`, text diffs: what changed between two runs |
