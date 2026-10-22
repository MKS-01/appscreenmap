"""`record` finds the touchscreen among the input devices."""

from __future__ import annotations

from appscreenmap.engine.cli.record import touch_device

GETEVENT = """add device 1: /dev/input/event12
  name:     "qwerty2"
  events:
    KEY (0001): KEY_ESC
add device 2: /dev/input/event3
  name:     "virtio_input_multi_touch_1"
  events:
    ABS (0003): ABS_MT_SLOT           : value 0, min 0, max 9, fuzz 0, flat 0, resolution 0
                ABS_MT_POSITION_X     : value 0, min 0, max 32767, fuzz 0, flat 0, resolution 0
                ABS_MT_POSITION_Y     : value 0, min 0, max 32767, fuzz 0, flat 0, resolution 0
"""


def test_the_touch_device_and_its_raw_range_are_read_from_getevent():
    assert touch_device(GETEVENT) == ("/dev/input/event3", (32767, 32767))
    assert touch_device("add device 1: /dev/input/event12\n  KEY (0001): KEY_ESC\n") is None
