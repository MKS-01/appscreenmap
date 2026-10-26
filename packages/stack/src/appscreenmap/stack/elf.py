"""16 KB page-size support of an APK's native libraries: ELF LOAD segment alignment and, for libraries stored
uncompressed, their offset in the zip. Stdlib only; mirrors AOSP's `check_elf_file.py` and `zipalign -P 16`."""

from __future__ import annotations

import struct
import zipfile

PAGE_16K = 16 * 1024
ABIS_64 = ("arm64-v8a", "x86_64")  # 16 KB pages are a 64-bit feature; 32-bit libraries are not checked
_PT_LOAD = 1
_MAX_HEADERS = 1024 * 1024


def load_alignment(head: bytes) -> int | None:
    """The smallest p_align of the PT_LOAD segments of a 64-bit little-endian ELF; None if it isn't one."""
    if len(head) < 64 or head[:4] != b"\x7fELF" or head[4] != 2 or head[5] != 1:
        return None
    (phoff,) = struct.unpack_from("<Q", head, 32)
    phentsize, phnum = struct.unpack_from("<HH", head, 54)
    aligns = []
    for i in range(phnum):
        off = phoff + i * phentsize
        if off + 56 > len(head):
            return None
        if struct.unpack_from("<I", head, off)[0] == _PT_LOAD:
            aligns.append(struct.unpack_from("<Q", head, off + 48)[0])
    return min(aligns) if aligns else None


def _data_offset(z: zipfile.ZipFile, info: zipfile.ZipInfo) -> int:
    z.fp.seek(info.header_offset + 26)
    name_len, extra_len = struct.unpack("<HH", z.fp.read(4))
    return info.header_offset + 30 + name_len + extra_len


def check_16k(z: zipfile.ZipFile) -> list[dict]:
    """One row per 64-bit `.so`: {"path", "abi", "align", "elf_ok", "zip_ok"}; zip_ok is None for a compressed one."""
    rows = []
    for info in z.infolist():
        parts = info.filename.split("/")
        if len(parts) != 3 or parts[0] != "lib" or parts[1] not in ABIS_64 or not parts[2].endswith(".so"):
            continue
        with z.open(info) as f:
            head = f.read(64)
            if len(head) == 64 and head[:4] == b"\x7fELF" and head[4] == 2:
                (phoff,) = struct.unpack_from("<Q", head, 32)
                phentsize, phnum = struct.unpack_from("<HH", head, 54)
                end = min(phoff + phentsize * phnum, _MAX_HEADERS)  # the table usually follows the header
                head += f.read(max(0, end - 64))
        align = load_alignment(head)
        stored = info.compress_type == zipfile.ZIP_STORED
        rows.append(
            {
                "path": info.filename,
                "abi": parts[1],
                "align": align,
                "elf_ok": align is not None and align >= PAGE_16K,
                "zip_ok": _data_offset(z, info) % PAGE_16K == 0 if stored else None,
            }
        )
    return rows
