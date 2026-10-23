"""Shared test setup: no real waiting for the "App pinned" toast, which only matters on a device."""

import importlib

import pytest


@pytest.fixture(autouse=True)
def no_pin_toast_wait(monkeypatch):
    for name in ("appscreenmap.crawler.explorer", "appscreenmap.crawler.replay"):
        try:
            monkeypatch.setattr(importlib.import_module(name), "PIN_TOAST_SECONDS", 0)
        except ImportError:  # a package that doesn't depend on the crawler
            pass
