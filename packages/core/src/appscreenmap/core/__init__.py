"""AppScreenMap core: the map.json model, hierarchy analysis, crawl config, run folders, notes and media."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("appscreenmap-core")
except PackageNotFoundError:  # running from a source tree that isn't installed
    __version__ = "0.0.0+unknown"
