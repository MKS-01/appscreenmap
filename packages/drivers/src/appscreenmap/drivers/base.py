"""What every driver shares: the error type and one raw observation of the screen."""

from __future__ import annotations

from dataclasses import dataclass


class DriverError(RuntimeError):
    pass


@dataclass
class Snapshot:
    """One raw observation of the device: hierarchy XML plus the foreground activity."""

    xml: str
    package: str | None
    activity: str | None
