# appscreenmap-testkit

Dev-only helpers for tests in every package; never shipped.

- `appscreenmap.testkit.helpers`: `node()` / `hierarchy()` build uiautomator-style XML (Compose-like output via
  `compose_home()`), `PKG`, and `REPO` (the repo root, for tests that read `samples/` or skill docs).

`tests/test_layers.py` checks the package layers: a package may import only the `appscreenmap.*` packages its
`pyproject.toml` depends on.
