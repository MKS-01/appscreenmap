---
name: maintain-crawler
description: Maintain and scale the AppScreenMap crawler — upgrade Python deps or tooling, verify against a new Android/emulator version, fix adb/dumpsys format breakage, evolve the map.json schema with a migration, keep CI green, and prepare the repo for open-source contributors. Use for upkeep, compatibility, or "something broke after an update" tasks.
---

# Maintain the crawler

## Health check (run first)

```bash
uv sync && uv run pytest -q && uv run ruff check && uv run ruff format --check
uv run appscreenmap doctor
```

Then a short real crawl as a smoke test (budget 40 steps is enough):
`uv run appscreenmap crawl --package dev.mks.duskread --clear-data --max-steps 40` and
`uv run appscreenmap report runs/<project>/<run-id>`. Compare with the last good run.

## Dependency upgrades

```bash
uv lock --upgrade && uv sync && uv run pytest -q
```

Runtime deps are deliberately tiny (Pillow only). Before adding a dependency, ask whether the
standard library would do. Ruff rules come from the user's global config, so fix the code rather
than adding ignores.

## New Android / emulator version: compatibility points

All device-format parsing lives in `driver.py`. When a new Android version breaks something,
check these one by one on the device:

| What | Command | Parsed by |
|---|---|---|
| Hierarchy dump | `adb shell uiautomator dump /sdcard/x.xml && adb shell cat /sdcard/x.xml` | `AdbDriver.snapshot()` (expects `<hierarchy>`; attributes incl. `hint`) |
| Foreground activity + task id | `adb shell dumpsys activity activities \| grep -m1 topResumedActivity` | `_ACTIVITY_RE`, `top_task_id()` |
| Screen size | `adb shell wm size` | `screen_size()` (override wins) |
| Keyboard shown | `adb shell dumpsys input_method \| grep mInputShown` | `keyboard_shown()` |
| Pinning | `adb shell am task lock <task>`; `dumpsys activity activities \| grep mLockTaskModeState` | `pin()` / `unpin()` |
| Launcher activity | `adb shell cmd package resolve-activity --brief -c android.intent.category.LAUNCHER <pkg>` | `resolve_launch_activity()` |
| Permission dialog ids | dump while a dialog shows | `analyzer.PERMISSION_ALLOW_IDS`, `PERMISSION_PACKAGES` |
| Crash dialog | dump while "keeps stopping" shows | `analyzer.is_crash_dialog()` |
| APK facts | `aapt2 dump badging` / `xmltree` | `apkinfo.py` (latest build-tools picked automatically) |

When a format changes, keep the old parse path working (users run old emulators too) and add
the new one. Add a unit test with both formats as literal strings.

## Schema evolution (`map.json`)

- **Additive changes** stay in schema 1: add the field, document it in `docs/MAP_SCHEMA.md`, and
  tell the user so the web session can use it.
- **Breaking changes** (rename, remove, change meaning): bump `model.SCHEMA_VERSION`, add a
  `migrate_v1_to_v2(data)` function used by `load_map()` so old runs keep loading, document both
  versions, and agree the change with the web session (via the user) before merging.

## Scaling

- **Speed**: device I/O dominates (dump ≈ 2 s, analysis < 1 ms). The upgrade path is an on-device
  agent driver (uiautomator2) via `extend-crawler`, not a language rewrite.
- **Big apps**: raise `max_steps`, keep `stop_after_no_new`, and tune `max_list_items`.
  Use `report` to confirm steps/screen stays low.
- **Many devices / apps**: one crawl per `--serial` in parallel. Run directories are timestamped
  and grouped per project (`runs/<project>/`); `runs/index.json` is rebuilt from disk
  (`runs.update_index`), and old flat `runs/<run-id>/` folders are still read.
- **CI**: `.github/workflows/crawler.yml` runs lint and tests on 3.11 and 3.13, path-filtered to
  crawler files. Device crawls don't run in CI.

## Open-source hygiene

- `runs/` is **git-ignored** (generated locally, one folder per project: `runs/<project>/<run-id>/`); `samples/demo.sh` makes sample ones.
  Keep it curated: one or two good runs per sample app (duskread), no broken, `running`, or
  throwaway runs, and no third-party apps. Watch repo size (PNG screenshots are ~100–300 KB each);
  if it grows, prune old runs or move samples to Git LFS. Tests still use synthetic XML only.
- Keep README commands working: when a CLI flag changes, update README and
  `examples/appscreenmap.toml` in the same change.
- No git tags or releases until the user asks.
- Record lessons that would stop the next person from re-breaking something in the
  `tune-crawler` skill's "Lessons" list.
