"""Stack scan on synthetic APKs, ELF headers and dumpsys text: no device, no aapt2 needed."""

from __future__ import annotations

import struct
import zipfile

import pytest

from appscreenmap.stack import build_audit, fingerprint, parse_components, parse_dumpsys_package
from appscreenmap.stack.detect import detect, summarize
from appscreenmap.stack.elf import PAGE_16K, check_16k, load_alignment

DUMPSYS = """\
Packages:
  Package [dev.appscreenmap.playground] (8c1f2a1):
    userId=10190
    codePath=/data/app/~~x==/dev.appscreenmap.playground-y==
    extractNativeLibs=false
    primaryCpuAbi=arm64-v8a
    secondaryCpuAbi=null
    versionCode=2 minSdk=26 targetSdk=35
    versionName=2.0
    splits=[base, config.arm64_v8a]
    apkSigningVersion=2
    flags=[ HAS_CODE ALLOW_CLEAR_USER_DATA DEBUGGABLE ]
    installerPackageName=null
    firstInstallTime=2026-10-27 01:00:00
  Package [dev.appscreenmap.playground] (99aa):
    versionCode=1 minSdk=21 targetSdk=30
"""


def elf(align: int) -> bytes:
    """A 64-bit little-endian ELF header with one PT_LOAD program header."""
    header = b"\x7fELF" + bytes([2, 1, 1]) + bytes(9)
    header += struct.pack("<HHIQQQIHHHHHH", 3, 183, 1, 0, 64, 0, 0, 64, 56, 1, 64, 0, 0)
    phdr = struct.pack("<IIQQQQQQ", 1, 5, 0, 0, 0, 0x1000, 0x1000, align)
    return header + phdr


def apk(path, entries: dict[str, bytes], stored: tuple[str, ...] = ()):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in entries.items():
            z.writestr(
                name, data, compress_type=zipfile.ZIP_STORED if name in stored else zipfile.ZIP_DEFLATED
            )
    return path


def dex(*descriptors: str) -> bytes:
    return b"dex\n035\0" + b"".join(bytes([len(d)]) + d.encode() + b"\0" for d in descriptors)


@pytest.fixture(autouse=True)
def no_aapt2(monkeypatch):
    monkeypatch.setattr("appscreenmap.stack.apk.find_aapt2", lambda: None)


def test_dumpsys_reads_the_first_package_block_only():
    facts = parse_dumpsys_package(DUMPSYS, "dev.appscreenmap.playground")
    assert facts["version_code"] == 2 and facts["min_sdk"] == 26 and facts["target_sdk"] == 35
    assert facts["version"] == "2.0" and facts["primary_abi"] == "arm64-v8a"
    assert facts["debuggable"] is True and facts["signing_version"] == 2
    assert facts["splits"] == ["base", "config.arm64_v8a"] and facts["extract_native_libs"] is False
    assert "installer" not in facts  # "null" is not a value


def test_elf_alignment_reads_the_load_segment():
    assert load_alignment(elf(PAGE_16K)) == PAGE_16K
    assert load_alignment(elf(4096)) == 4096
    assert load_alignment(b"not an elf") is None


def test_16k_check_covers_64_bit_libraries_only(tmp_path):
    path = apk(
        tmp_path / "base.apk",
        {
            "lib/arm64-v8a/libgood.so": elf(PAGE_16K),
            "lib/arm64-v8a/libold.so": elf(4096),
            "lib/armeabi-v7a/libold.so": elf(4096),
        },
    )
    with zipfile.ZipFile(path) as z:
        rows = {r["path"]: r for r in check_16k(z)}
    assert set(rows) == {"lib/arm64-v8a/libgood.so", "lib/arm64-v8a/libold.so"}
    assert rows["lib/arm64-v8a/libgood.so"]["elf_ok"] and not rows["lib/arm64-v8a/libold.so"]["elf_ok"]
    assert rows["lib/arm64-v8a/libgood.so"]["zip_ok"] is None  # compressed: extracted at install, offset moot


def test_uncompressed_library_must_sit_on_a_16k_boundary(tmp_path):
    path = apk(
        tmp_path / "base.apk",
        {"lib/arm64-v8a/libgood.so": elf(PAGE_16K)},
        stored=("lib/arm64-v8a/libgood.so",),
    )
    with zipfile.ZipFile(path) as z:
        (row,) = check_16k(z)
    assert row["elf_ok"] and row["zip_ok"] is False  # written without zipalign -P 16


@pytest.mark.parametrize(
    ("libs", "paths", "descriptors", "summary"),
    [
        ({"libflutter.so", "libapp.so"}, ["assets/flutter_assets/AssetManifest.json"], [], "Flutter"),
        (
            {"libreactnative.so", "libhermes.so"},
            [],
            ["Lexpo/modules/kotlin/AppContext;"],
            "React Native (Expo, Hermes JS engine)",
        ),
        ({"libunity.so", "libil2cpp.so"}, [], [], "Unity (IL2CPP scripting backend)"),
        (
            {"libmonodroid.so"},
            [],
            ["Lmicrosoft/maui/PlatformInterop;"],
            ".NET for Android (Xamarin / MAUI) (.NET MAUI)",
        ),
        (set(), ["assets/capacitor.config.json"], ["Lcom/getcapacitor/Bridge;"], "Capacitor"),
        (set(), ["assets/www/cordova.js"], [], "Apache Cordova"),
        (
            set(),
            ["META-INF/androidx.compose.runtime_runtime.version"],
            ["Lkotlin/jvm/internal/Intrinsics;"],
            "Native Android: Kotlin, Jetpack Compose",
        ),
        (set(), [], [], "Native Android: Java, Android Views"),
        (
            set(),
            ["composeResources/app.generated.resources/drawable/logo.xml"],
            ["Lkotlin/jvm/internal/Intrinsics;", "Lorg/jetbrains/compose/resources/StringResource;"],
            "Kotlin Multiplatform: Compose Multiplatform UI, Kotlin",
        ),
        (
            set(),
            [],
            ["Lkotlin/jvm/internal/Intrinsics;", "Lio/ktor/client/HttpClient;"],
            "Native Android: Kotlin, Android Views (shared KMP code possible)",
        ),
    ],
)
def test_framework_rules(libs, paths, descriptors, summary):
    assert summarize(detect(libs, paths, dex(*descriptors)))["summary"] == summary


def test_kmp_on_android_is_never_more_than_a_hint():
    (s,) = detect(set(), [], dex("Lapp/cash/sqldelight/Query;"))
    assert (s["id"], s["confidence"], s["source"]) == ("kmp-libraries", "likely", "device")


def test_components_from_the_manifest_tree():
    tree = """N: android=http://schemas.android.com/apk/res/android
  E: manifest (line=2)
    A: package="dev.appscreenmap.playground" (Raw: "dev.appscreenmap.playground")
    E: application (line=10)
      E: activity (line=12)
        A: http://schemas.android.com/apk/res/android:name(0x01010003)=".MainActivity" (Raw: ".MainActivity")
      E: service (line=20)
        A: http://schemas.android.com/apk/res/android:name(0x01010003)="com.google.firebase.messaging.FirebaseMessagingService"
      E: meta-data (line=30)
        A: http://schemas.android.com/apk/res/android:name(0x01010003)="not.a.Component"
"""
    assert parse_components(tree) == [
        "com.google.firebase.messaging.FirebaseMessagingService",
        "dev.appscreenmap.playground.MainActivity",
    ]


def test_fingerprint_reads_base_and_splits(tmp_path):
    base = apk(
        tmp_path / "base.apk",
        {
            "classes.dex": dex("Lkotlin/jvm/internal/Intrinsics;", "Landroidx/compose/runtime/Composer;"),
            "META-INF/androidx.compose.ui_ui.version": b"1.7.5\n",
        },
    )
    split = apk(tmp_path / "split_config.arm64_v8a.apk", {"lib/arm64-v8a/libsqlite3.so": elf(4096)})
    fp = fingerprint([base, split])
    assert fp["apks"] == ["base.apk", "split_config.arm64_v8a.apk"]
    assert fp["abis"] == ["arm64-v8a"]
    assert fp["stack"] == {"kind": "native", "summary": "Native Android: Kotlin, Jetpack Compose"}
    assert {"name": "androidx.compose.ui:ui", "version": "1.7.5"} in fp["libraries"]
    assert fp["native_libs"][0]["name"] == "libsqlite3.so"
    assert any("aapt2" in n for n in fp["notes"])  # compileSdk unknown is said, never guessed
    assert fp["compile_sdk"] is None


def test_audit_flags_16k_as_an_error_from_target_35(tmp_path):
    split = apk(tmp_path / "split.apk", {"lib/arm64-v8a/libold.so": elf(4096)})
    fp = fingerprint([split])
    device = parse_dumpsys_package(DUMPSYS, "dev.appscreenmap.playground")
    audit = build_audit("dev.appscreenmap.playground", device, fp, "test")
    ids = {f["id"]: f["severity"] for f in audit["findings"]}
    assert ids == {"stack::page-16k": "error", "stack::debuggable": "info"}
    assert audit["status"] == "fail" and audit["audit"] == "stack" and audit["schema"] == 1
    assert audit["facts"]["target_sdk"] == 35  # the device's value
    assert all(s["source"] == "device" for s in audit["facts"]["signals"])


def test_32_bit_only_native_code_fails_the_64_bit_rule(tmp_path):
    fp = fingerprint([apk(tmp_path / "a.apk", {"lib/armeabi-v7a/libx.so": b"\x7fELF"})])
    audit = build_audit("p", {"target_sdk": 34}, fp, "test")
    assert [f["id"] for f in audit["findings"]] == ["stack::no-64-bit"]


def test_storage_map_says_where_and_whether_encrypted(tmp_path):
    base = apk(
        tmp_path / "base.apk",
        {
            "classes.dex": dex(
                "Lio/flutter/plugins/sharedpreferences/SharedPreferencesPlugin;",
                "Lcom/it_nomads/fluttersecurestorage/FlutterSecureStorage;",
            ),
            "META-INF/androidx.datastore_datastore-preferences.version": b"1.1.1",
            "lib/arm64-v8a/libmmkv.so": elf(PAGE_16K),
        },
    )
    storage = {s["id"]: s for s in fingerprint([base])["storage"]}
    assert set(storage) == {"datastore", "mmkv", "flutter-shared-preferences", "flutter-secure-storage"}
    assert storage["flutter-shared-preferences"]["locations"] == ["shared_prefs/FlutterSharedPreferences.xml"]
    assert storage["flutter-shared-preferences"]["encrypted"] is False
    assert storage["flutter-secure-storage"]["encrypted"] is True
    assert (
        storage["mmkv"]["encrypted"] is None
    )  # optional: set up by the app, so it's for the data scan to check
    assert all(s["confidence"] == "strong" and s["source"] == "device" for s in storage.values())


def test_framework_sqlite_lists_the_database_names_the_code_opens(tmp_path):
    """A release build shrunk by R8 hides SQLDelight's classes; the framework helper and the file names remain."""
    base = apk(
        tmp_path / "base.apk",
        {
            "classes.dex": dex(
                "Landroid/database/sqlite/SQLiteOpenHelper;", "notes.db", "x.db.bak", "cache.db"
            )
        },
    )
    (sqlite,) = fingerprint([base])["storage"]
    assert sqlite["id"] == "sqlite" and sqlite["encrypted"] is False
    assert sqlite["locations"] == ["databases/cache.db", "databases/notes.db"]


def test_kotlinx_datetime_alone_is_not_a_kmp_hint():
    """Calibration (2026-10-27): React Native apps bundle it through Android SDKs; it said "KMP possible" wrongly."""
    signals = detect({"libreactnative.so"}, [], dex("Lkotlinx/datetime/Instant;"))
    assert "kmp-libraries" not in {s["id"] for s in signals}
