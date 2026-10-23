"""Shared test setup: no real waiting for the "App pinned" toast, which only matters on a device."""

import importlib
import inspect
import re

import pytest


@pytest.fixture(autouse=True)
def no_pin_toast_wait(monkeypatch):
    for name in ("appscreenmap.crawler.explorer", "appscreenmap.crawler.replay"):
        try:
            monkeypatch.setattr(importlib.import_module(name), "PIN_TOAST_SECONDS", 0)
        except ImportError:  # a package that doesn't depend on the crawler
            pass


def _sources(item):
    """The test's own source and that of every fixture it uses."""
    funcs = [getattr(item, "function", None)]
    for defs in item._fixtureinfo.name2fixturedefs.values():
        funcs += [d.func for d in defs]
    out = []
    for f in funcs:
        try:
            out.append(inspect.getsource(f))
        except (OSError, TypeError):
            pass
    return "\n".join(out)


def pytest_collection_modifyitems(items):
    """Tests that run the fake app through the crawler take seconds each (76 of the suite's 88 s): mark them `slow`,
    so `make test-fast` (`-m "not slow"`) skips them and `make test` runs everything."""
    for item in items:
        if "fakedevice" in str(item.fspath) or re.search(r"\b(crawl|Explorer|Replayer|_explorer)\(|\bex\.run\(\)", _sources(item)):
            item.add_marker(pytest.mark.slow)
