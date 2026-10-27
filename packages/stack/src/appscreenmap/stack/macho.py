"""Mach-O load commands, read with `struct`: linked dylibs, the build version (min OS, SDK) and the encryption flag.

Thin 64- and 32-bit files and fat (universal) files; for a fat file the arm64 slice is read, else the first.
"""

from __future__ import annotations

import struct

_MH = {b"\xcf\xfa\xed\xfe": 32, b"\xce\xfa\xed\xfe": 28}  # little-endian 64- and 32-bit magic → header size
_FAT = {b"\xca\xfe\xba\xbe": (">IIIII", 20), b"\xca\xfe\xba\xbf": (">IIQQII", 32)}  # fat_arch, fat_arch_64
_ARM64 = 0x0100000C
_CPU = {0x0100000C: "arm64", 0x01000007: "x86_64", 12: "arm", 7: "i386"}
_DYLIB = {0xC, 0x20, 0x80000018, 0x8000001F, 0x80000023}  # load, lazy, weak, re-export, upward
_BUILD_VERSION, _VERSION_MIN_IPHONEOS = 0x32, 0x25
_ENCRYPTION = {0x21, 0x2C}
_PLATFORM = {
    1: "macos",
    2: "ios",
    3: "tvos",
    4: "watchos",
    6: "maccatalyst",
    7: "ios-simulator",
    11: "visionos",
}
_MAX_HEADERS = 4 * 1024 * 1024


def _version(v: int) -> str:
    """xxxx.yy.zz packed in nibbles: 0x120100 → 18.1 (the patch only when non-zero)."""
    major, minor, patch = v >> 16, (v >> 8) & 0xFF, v & 0xFF
    return f"{major}.{minor}" + (f".{patch}" if patch else "")


def fat_slice(head: bytes) -> tuple[int, int, list[str]] | None:
    """(offset, length, arches) of the slice to read in a fat file, from its header alone; None if `head` is not fat
    or its table is cut short."""
    fat = _FAT.get(head[:4])
    if not fat or len(head) < 8:
        return None
    fmt, size = fat
    (n,) = struct.unpack_from(">I", head, 4)
    n = min(n, 16)
    if n == 0 or len(head) < 8 + n * size:
        return None
    arches = [struct.unpack_from(fmt, head, 8 + i * size)[:4] for i in range(n)]
    _, _, offset, length = next((a for a in arches if a[0] == _ARM64), arches[0])
    return offset, length, [_arch(c, s) for c, s, _, _ in arches]


def _slice(data: bytes) -> tuple[bytes, list[str]]:
    """The thin Mach-O to read and every architecture the file holds."""
    if not _FAT.get(data[:4]):
        return data, []
    found = fat_slice(data)
    if found is None:
        return b"", []
    offset, length, arches = found
    return data[offset : offset + length], arches


def _arch(cpu: int, sub: int) -> str:
    return "arm64e" if cpu == _ARM64 and sub & 0xFF == 2 else _CPU.get(cpu, hex(cpu))


def parse(data: bytes) -> dict | None:
    """{"arch", "arches", "platform", "min_os", "sdk", "encrypted", "dylibs"}, or None if `data` is not Mach-O.

    `data` needs only the headers (the first few KB of a thin file); a fat file needs its slice's headers too.
    `encrypted` is None when the binary has no encryption command (simulator and development builds)."""
    thin, arches = _slice(data)
    head = _MH.get(thin[:4])
    if not head or len(thin) < head + 8:
        return None
    cpu, sub, _type, ncmds, sizeofcmds = struct.unpack_from("<IIIII", thin, 4)
    out = {
        "arch": _arch(cpu, sub),
        "arches": arches or [_arch(cpu, sub)],
        "platform": None,
        "min_os": None,
        "sdk": None,
        "encrypted": None,
        "dylibs": [],
    }
    pos, end = head, min(head + sizeofcmds, len(thin), _MAX_HEADERS)
    for _ in range(ncmds):
        if pos + 8 > end:
            break
        cmd, size = struct.unpack_from("<II", thin, pos)
        if size < 8:
            break
        if cmd in _DYLIB and pos + 12 <= end:
            (off,) = struct.unpack_from("<I", thin, pos + 8)
            raw = thin[pos + off : pos + size]
            out["dylibs"].append(raw.split(b"\0", 1)[0].decode(errors="replace"))
        elif cmd == _BUILD_VERSION and pos + 20 <= end:
            platform, minos, sdk = struct.unpack_from("<III", thin, pos + 8)
            out.update(
                platform=_PLATFORM.get(platform, str(platform)), min_os=_version(minos), sdk=_version(sdk)
            )
        elif cmd == _VERSION_MIN_IPHONEOS and pos + 16 <= end and out["min_os"] is None:
            minos, sdk = struct.unpack_from("<II", thin, pos + 8)
            out.update(platform="ios", min_os=_version(minos), sdk=_version(sdk))
        elif cmd in _ENCRYPTION and pos + 20 <= end:
            (cryptid,) = struct.unpack_from("<I", thin, pos + 16)
            out["encrypted"] = bool(out["encrypted"]) or cryptid != 0
        pos += size
    return out
