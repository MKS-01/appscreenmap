"""iOS stack scan on synthetic Mach-O headers and `.app` folders: no simulator, no Xcode needed."""

from __future__ import annotations

import plistlib
import struct

import pytest

from appscreenmap.stack import build_ios_audit, fingerprint_app
from appscreenmap.stack.macho import parse

SWIFT = "/usr/lib/swift/libswiftCore.dylib"
SWIFTUI = "/System/Library/Frameworks/SwiftUI.framework/SwiftUI"
UIKIT = "/System/Library/Frameworks/UIKit.framework/UIKit"
SQLITE = "/usr/lib/libsqlite3.dylib"


def _ver(v: tuple[int, int]) -> int:
    return v[0] << 16 | v[1] << 8


def macho(
    dylibs=(),
    minos=(18, 0),
    sdk=(27, 0),
    platform=7,
    cryptid: int | None = None,
    strings: bytes = b"",
    cpu=0x0100000C,
) -> bytes:
    """A thin 64-bit Mach-O: one LC_LOAD_DYLIB per dylib, LC_BUILD_VERSION, optional LC_ENCRYPTION_INFO_64, then
    `strings` as the file's body."""
    cmds = [struct.pack("<IIIIII", 0x32, 24, platform, _ver(minos), _ver(sdk), 0)]
    for d in dylibs:
        name = d.encode() + b"\0"
        name += b"\0" * (-(24 + len(name)) % 8)
        cmds.append(struct.pack("<IIIIII", 0xC, 24 + len(name), 24, 2, 0x10000, 0x10000) + name)
    if cryptid is not None:
        cmds.append(struct.pack("<IIIIII", 0x2C, 24, 0x4000, 0x1000, cryptid, 0))
    body = b"".join(cmds)
    head = struct.pack("<IIIIIIII", 0xFEEDFACF, cpu, 0, 2, len(cmds), len(body), 0, 0)
    return head + body + strings


def fat(*slices: tuple[int, bytes]) -> bytes:
    """A universal binary holding (cputype, thin Mach-O) slices, each at a 4 KB boundary."""
    out, offset, table = b"", 4096, b""
    for cpu, data in slices:
        table += struct.pack(">IIIII", cpu, 0, offset, len(data), 12)
        out += data + b"\0" * (-len(data) % 4096)
        offset += len(data) + (-len(data) % 4096)
    head = struct.pack(">II", 0xCAFEBABE, len(slices)) + table
    return head + b"\0" * (4096 - len(head)) + out


def app(
    tmp_path,
    name="Alpha",
    binary: bytes | None = None,
    files: dict[str, bytes] | None = None,
    frameworks=(),
    debug: bytes | None = None,
    bundle="dev.appscreenmap.alpha",
):
    """A `.app` folder: Info.plist, the main executable, optional debug dylib, embedded frameworks and files."""
    d = tmp_path / f"{name}.app"
    d.mkdir()
    info = {
        "CFBundleIdentifier": bundle,
        "CFBundleExecutable": name,
        "CFBundleShortVersionString": "2.0",
        "CFBundleVersion": "7",
        "CFBundleName": name,
        "MinimumOSVersion": "17.0",
        "DTSDKName": "iphonesimulator27.0",
        "DTXcode": "2700",
    }
    (d / "Info.plist").write_bytes(plistlib.dumps(info))
    (d / name).write_bytes(binary if binary is not None else macho([SWIFT, UIKIT]))
    if debug is not None:
        (d / f"{name}.debug.dylib").write_bytes(debug)
    for fw in frameworks:
        f = d / "Frameworks" / f"{fw}.framework"
        f.mkdir(parents=True)
        (f / "Info.plist").write_bytes(
            plistlib.dumps({"CFBundleExecutable": fw, "CFBundleShortVersionString": "1.0"})
        )
        (f / fw).write_bytes(macho([]))
    for path, data in (files or {}).items():
        (d / path).parent.mkdir(parents=True, exist_ok=True)
        (d / path).write_bytes(data)
    return d


# ── Mach-O ──────────────────────────────────────────────────────────────────


def test_macho_reads_dylibs_build_version_and_no_encryption():
    mo = parse(macho([SWIFT, SWIFTUI], minos=(18, 0), sdk=(27, 1)))
    assert mo["dylibs"] == [SWIFT, SWIFTUI]
    assert (mo["platform"], mo["min_os"], mo["sdk"], mo["arch"]) == ("ios-simulator", "18.0", "27.1", "arm64")
    assert mo["encrypted"] is None


@pytest.mark.parametrize(("cryptid", "encrypted"), [(1, True), (0, False)])
def test_macho_reads_the_encryption_flag(cryptid, encrypted):
    assert parse(macho([], platform=2, cryptid=cryptid))["encrypted"] is encrypted


def test_a_fat_binary_reads_its_arm64_slice():
    x86 = macho([UIKIT], minos=(15, 0), cpu=0x01000007)
    arm = macho([SWIFTUI], minos=(17, 0))
    mo = parse(fat((0x01000007, x86), (0x0100000C, arm)))
    assert mo["arches"] == ["x86_64", "arm64"] and mo["dylibs"] == [SWIFTUI] and mo["min_os"] == "17.0"


def test_not_macho_is_none():
    assert parse(b"\x7fELF" + bytes(60)) is None
    assert parse(b"") is None
    assert parse(b"\xca\xfe\xba\xbe\0\0\0\x05") is None  # a fat table cut short
    assert parse(b"\xcf\xfa\xed\xfe" + bytes(28)) is None  # a header with no room for commands


def test_a_huge_fat_binary_is_read_at_its_slice(tmp_path, monkeypatch):
    monkeypatch.setattr("appscreenmap.stack.ios._MAX_BINARY", 1024)
    binary = fat(
        (0x01000007, macho([UIKIT], cpu=0x01000007)), (0x0100000C, macho([SWIFT, SWIFTUI], minos=(17, 0)))
    )
    fp = fingerprint_app(app(tmp_path, binary=binary))
    assert fp["min_os"] == "17.0" and fp["stack"]["summary"] == "Native iOS: Swift, SwiftUI"
    assert any("only its headers" in n for n in fp["notes"])


def test_net_assemblies_are_found_anywhere_in_the_bundle(tmp_path):
    files = {".xamarin/iossimulator-arm64/Microsoft.iOS.dll": b"MZ"}
    assert fingerprint_app(app(tmp_path, files=files))["stack"]["kind"] == "cross-platform"


# ── frameworks ──────────────────────────────────────────────────────────────

CASES = {
    "flutter": (
        {
            "frameworks": ["Flutter", "App"],
            "files": {"Frameworks/App.framework/flutter_assets/AssetManifest.json": b"{}"},
        },
        "cross-platform",
        "Flutter",
    ),
    "react-native-hermes": (
        {
            "frameworks": ["hermes"],
            "files": {"main.jsbundle": b"x"},
            "binary": macho([SWIFT, UIKIT], strings=b"RCTBridge\0"),
        },
        "cross-platform",
        "React Native (Hermes JS engine)",
    ),
    "expo": (
        {"frameworks": ["hermesvm", "ExpoModulesCore"], "files": {"main.jsbundle": b"x"}},
        "cross-platform",
        "React Native (Expo, Hermes JS engine)",
    ),
    "unity": ({"frameworks": ["UnityFramework"]}, "cross-platform", "Unity"),
    "maui": (
        {"files": {"Microsoft.iOS.dll": b"MZ", "Microsoft.Maui.dll": b"MZ"}},
        "cross-platform",
        ".NET for iOS (Xamarin / MAUI) (.NET MAUI)",
    ),
    "capacitor": (
        {"frameworks": ["Capacitor"], "files": {"capacitor.config.json": b"{}", "public/index.html": b""}},
        "cross-platform",
        "Capacitor",
    ),
    "kmp-compose": (
        {
            "files": {"compose-resources/values/strings.xml": b""},
            "binary": macho([SWIFT, UIKIT], strings=b"kfun:main\0skiko\0"),
        },
        "kmp",
        "Kotlin Multiplatform: Compose Multiplatform UI",
    ),
    "kmp-swiftui": (
        {
            "frameworks": ["Shared"],
            "binary": macho([SWIFT, SWIFTUI, UIKIT], strings=b"kfun:dev.example.Repo#load\0"),
        },
        "kmp",
        "Kotlin Multiplatform: shared Kotlin, SwiftUI UI",
    ),
    "swiftui": ({"binary": macho([SWIFT, SWIFTUI, UIKIT])}, "native", "Native iOS: Swift, SwiftUI"),
    "objc-uikit": (
        {"binary": macho(["/usr/lib/libobjc.A.dylib", UIKIT])},
        "native",
        "Native iOS: Objective-C, UIKit",
    ),
}


@pytest.mark.parametrize("case", CASES)
def test_each_stack_reads_as_itself(tmp_path, case):
    kwargs, kind, summary = CASES[case]
    fp = fingerprint_app(app(tmp_path, **kwargs))
    assert fp["stack"] == {"kind": kind, "summary": summary}


def test_kotlin_native_in_a_framework_counts(tmp_path):
    d = app(tmp_path, frameworks=["Shared"])
    (d / "Frameworks" / "Shared.framework" / "Shared").write_bytes(
        macho([], strings=b"kfun:dev.example#main\0")
    )
    signal = next(s for s in fingerprint_app(d)["signals"] if s["id"] == "kotlin-native")
    assert signal["confidence"] == "certain" and signal["evidence"] == ["kfun: in Shared"]


def test_a_debug_build_is_read_through_its_debug_dylib(tmp_path):
    stub = macho(["@rpath/Alpha.debug.dylib", "/usr/lib/libSystem.B.dylib"])
    code = macho([SWIFT, SWIFTUI, UIKIT, SQLITE], strings=b"kfun:main\0org.jetbrains.compose\0")
    fp = fingerprint_app(app(tmp_path, binary=stub, debug=code))
    assert fp["debug_build"] and fp["stack"]["kind"] == "kmp"
    assert {s["id"] for s in fp["storage"]} == {"sqlite"}


def test_an_encrypted_binary_gives_no_code_markers(tmp_path):
    binary = macho([SWIFT, UIKIT], platform=2, cryptid=1, strings=b"kfun:main\0NSUserDefaults\0")
    fp = fingerprint_app(app(tmp_path, binary=binary))
    assert fp["encrypted"] is True
    assert "kotlin-native" not in {s["id"] for s in fp["signals"]}
    assert fp["storage"] == [] and any("encrypted" in n for n in fp["notes"])
    assert fp["stack"]["summary"] == "Native iOS: Swift, UIKit"  # linked libraries are still readable


def test_build_facts_come_from_info_plist_and_the_binary(tmp_path):
    fp = fingerprint_app(app(tmp_path, binary=macho([SWIFT, UIKIT], minos=(17, 0), sdk=(27, 0))))
    assert (fp["bundle_id"], fp["version"], fp["build"]) == ("dev.appscreenmap.alpha", "2.0", "7")
    assert (fp["deployment_target"], fp["build_sdk"], fp["xcode"]) == ("17.0", "27.0", "27.0")
    assert (fp["min_os"], fp["sdk"], fp["simulator_build"]) == ("17.0", "27.0", True)


def test_embedded_frameworks_are_listed_with_their_version(tmp_path):
    fp = fingerprint_app(app(tmp_path, frameworks=["Flutter"]))
    assert fp["frameworks"] == [{"name": "Flutter", "version": "1.0"}]


def test_a_folder_without_info_plist_says_so(tmp_path):
    d = tmp_path / "Broken.app"
    d.mkdir()
    fp = fingerprint_app(d)
    assert fp["bundle_id"] is None and any("Info.plist" in n for n in fp["notes"])


# ── storage ─────────────────────────────────────────────────────────────────


def test_storage_paths_are_under_the_data_container(tmp_path):
    binary = macho(
        [SWIFT, SWIFTUI, SQLITE, "/System/Library/Frameworks/CoreData.framework/CoreData"],
        strings=b"NSUserDefaults\0SecItemAdd\0",
    )
    fp = fingerprint_app(app(tmp_path, binary=binary))
    rows = {s["id"]: s for s in fp["storage"]}
    assert rows["user-defaults"]["locations"] == ["Library/Preferences/dev.appscreenmap.alpha.plist"]
    assert rows["core-data"]["locations"] == ["Library/Application Support/"]
    assert rows["keychain"]["locations"] == [] and rows["keychain"]["encrypted"] is True
    assert all(r["confidence"] == "strong" for r in rows.values())


def test_database_names_come_from_utf8_and_kotlin_native_utf16_strings(tmp_path):
    utf16 = "\0alpha.db\0".encode("utf-16le")
    package = "com.example.db".encode("utf-16le")  # a Kotlin package, not a file
    binary = macho([SWIFT, UIKIT, SQLITE], strings=b"\0bravo.sqlite\0" + utf16 + package)
    rows = {s["id"]: s for s in fingerprint_app(app(tmp_path, binary=binary))["storage"]}
    assert rows["sqlite"]["locations"] == ["**/alpha.db", "**/bravo.sqlite"]


# ── audit ───────────────────────────────────────────────────────────────────


def test_the_ios_audit_has_ios_facts_and_metrics(tmp_path):
    stub = macho(["@rpath/Alpha.debug.dylib"])
    fp = fingerprint_app(app(tmp_path, binary=stub, debug=macho([SWIFT, SWIFTUI, UIKIT])))
    audit = build_ios_audit(fp, "test", "/tmp/data")
    facts = audit["facts"]
    assert (facts["platform"], facts["package"], facts["data_container"]) == (
        "ios",
        "dev.appscreenmap.alpha",
        "/tmp/data",
    )
    assert audit["summary"] == "Native iOS: Swift, SwiftUI" and audit["status"] == "info"
    assert [m["label"] for m in audit["metrics"]] == [
        "deployment target",
        "build SDK",
        "Xcode",
        "frameworks",
        "storage",
    ]
    assert [f["id"] for f in audit["findings"]] == ["stack::debuggable"]
    assert all(f["platform"] == "ios" for f in audit["findings"])


def test_kotlin_native_databases_are_in_application_support_databases(tmp_path):
    binary = macho([SWIFT, UIKIT, SQLITE], strings=b"kfun:main\0" + "\0alpha.db\0".encode("utf-16le"))
    rows = {s["id"]: s for s in fingerprint_app(app(tmp_path, binary=binary))["storage"]}
    assert rows["sqlite"]["locations"] == ["Library/Application Support/databases/alpha.db"]
