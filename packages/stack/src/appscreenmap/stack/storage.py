"""Where an app keeps data on the device, from the storage libraries it bundles: the map a data-at-rest scan reads.

Each rule names the library, the paths it writes under the app's data folder (`/data/data/<pkg>/`), and whether it
encrypts what it stores (None: optional, depends on how the app sets it up). A bundled library may still be unused,
so every hit is `strong` at most; the Frida probe confirms which ones run.
"""

from __future__ import annotations

import re

from .detect import RANK, _matches

# A dex string is its length byte, the text, then NUL: database file names the code opens by name.
_DB_NAME = re.compile(rb"([\x04-\x40])([A-Za-z0-9_][A-Za-z0-9_.-]{0,62}\.db)\x00")

# (id, label, encrypted, locations, [(kind, pattern, confidence)]) — kinds as in detect.RULES
STORAGE: list[tuple[str, str, bool | None, list[str], list[tuple[str, str, str]]]] = [
    (
        "datastore",
        "Jetpack DataStore",
        False,
        ["files/datastore/"],
        [
            ("path", "META-INF/androidx.datastore_datastore", "strong"),
            ("dex", "Landroidx/datastore/", "strong"),
        ],
    ),
    (
        "room",
        "Room (SQLite)",
        False,
        ["databases/"],
        [
            ("path", "META-INF/androidx.room_room-runtime.version", "strong"),
            ("dex", "Landroidx/room/RoomDatabase;", "strong"),
        ],
    ),
    (
        "sqlite",
        "SQLite (framework; also under Room and SQLDelight)",
        False,
        ["databases/"],
        [("dex", "Landroid/database/sqlite/SQLiteOpenHelper;", "strong")],
    ),
    (
        "sqlcipher",
        "SQLCipher",
        True,
        ["databases/"],
        [("lib", "libsqlcipher.so", "strong"), ("dex", "Lnet/zetetic/database/", "strong")],
    ),
    (
        "encrypted-prefs",
        "EncryptedSharedPreferences",
        True,
        ["shared_prefs/"],
        [
            ("path", "META-INF/androidx.security_security-crypto.version", "strong"),
            ("dex", "Landroidx/security/crypto/EncryptedSharedPreferences;", "strong"),
        ],
    ),
    ("tink", "Tink", True, ["shared_prefs/"], [("dex", "Lcom/google/crypto/tink/", "strong")]),
    (
        "android-keystore",
        "Android Keystore keys",
        True,
        [],
        [("dex", "Landroid/security/keystore/KeyGenParameterSpec;", "strong")],
    ),
    (
        "mmkv",
        "MMKV",
        None,
        ["files/mmkv/"],
        [("lib", "libmmkv.so", "strong"), ("dex", "Lcom/tencent/mmkv/", "strong")],
    ),
    ("realm", "Realm", None, ["files/"], [("lib", "librealm-jni.so", "strong")]),
    ("objectbox", "ObjectBox", False, ["files/objectbox/"], [("lib", "libobjectbox-jni.so", "strong")]),
    (
        "rn-async-storage",
        "React Native AsyncStorage",
        False,
        ["databases/RKStorage"],
        [("dex", "Lcom/reactnativecommunity/asyncstorage/", "strong")],
    ),
    (
        "rn-keychain",
        "react-native-keychain",
        True,
        ["shared_prefs/RN_KEYCHAIN.xml"],
        [("dex", "Lcom/oblador/keychain/", "strong")],
    ),
    (
        "expo-secure-store",
        "Expo SecureStore",
        True,
        ["shared_prefs/SecureStore.xml"],
        [("dex", "Lexpo/modules/securestore/", "strong")],
    ),
    (
        "flutter-shared-preferences",
        "Flutter shared_preferences",
        False,
        ["shared_prefs/FlutterSharedPreferences.xml"],
        [("dex", "Lio/flutter/plugins/sharedpreferences/", "strong")],
    ),
    (
        "flutter-secure-storage",
        "flutter_secure_storage",
        True,
        ["shared_prefs/FlutterSecureStorage.xml"],
        [("dex", "Lcom/it_nomads/fluttersecurestorage/", "strong")],
    ),
]


# iOS: paths under the app's data container (`simctl get_app_container <udid> <bundle> data`); `{bundle}` is the
# bundle id. Keychain items live in the simulator's shared keychain, not in the container, so they have no path.
IOS_STORAGE: list[tuple[str, str, bool | None, list[str], list[tuple[str, str, str]]]] = [
    (
        "user-defaults",
        "UserDefaults",
        False,
        ["Library/Preferences/{bundle}.plist"],
        [("symbol", "NSUserDefaults", "strong")],
    ),
    (
        "core-data",
        "Core Data",
        False,
        ["Library/Application Support/"],
        [("dylib", "/CoreData.framework/", "strong")],
    ),
    (
        "swiftdata",
        "SwiftData",
        False,
        ["Library/Application Support/default.store"],
        [("dylib", "/SwiftData.framework/", "strong")],
    ),
    (
        "sqlite",
        "SQLite (system library; also under Core Data and SQLDelight)",
        False,
        ["Library/Application Support/", "Documents/"],
        [("dylib", "/libsqlite3.dylib", "strong")],
    ),
    (
        "sqlcipher",
        "SQLCipher",
        True,
        ["Library/Application Support/", "Documents/"],
        [("framework", "SQLCipher", "strong"), ("symbol", "sqlcipher_export", "strong")],
    ),
    (
        "realm",
        "Realm",
        None,
        ["Documents/default.realm"],
        [("framework", "Realm", "strong"), ("framework", "RealmSwift", "strong")],
    ),
    (
        "mmkv",
        "MMKV",
        None,
        ["Documents/mmkv/"],
        [
            ("framework", "MMKV", "strong"),
            ("framework", "MMKVCore", "strong"),
            ("symbol", "MMKVCore", "strong"),
        ],
    ),
    (
        "rn-async-storage",
        "React Native AsyncStorage",
        False,
        ["Library/Application Support/{bundle}/RCTAsyncLocalStorage_V1/"],
        [("symbol", "RNCAsyncStorage", "strong")],
    ),
    (
        "flutter-shared-preferences",
        "Flutter shared_preferences (UserDefaults, keys prefixed flutter.)",
        False,
        ["Library/Preferences/{bundle}.plist"],
        [("framework", "shared_preferences_foundation", "strong")],
    ),
    (
        "keychain",
        "Keychain (not in the data container)",
        True,
        [],
        [
            ("symbol", "SecItemAdd", "strong"),
            ("framework", "flutter_secure_storage", "strong"),
            ("symbol", "RNKeychainManager", "strong"),
            ("framework", "ExpoSecureStore", "strong"),
        ],
    ),
]


def detect_storage(libs: set[str], paths: list[str], dex: bytes) -> list[dict]:
    """[{"id", "label", "encrypted", "locations", "confidence", "evidence", "source": "device"}]."""
    out = []
    names = sorted({m.group(2).decode() for m in _DB_NAME.finditer(dex) if m.group(1)[0] == len(m.group(2))})
    for sid, label, encrypted, locations, checks in STORAGE:
        if sid == "sqlite" and names:
            locations = [f"databases/{n}" for n in names[:20]]
        hits = [(conf, ev) for kind, pat, conf in checks for ev in _matches(kind, pat, libs, paths, dex)]
        if hits:
            out.append(
                {
                    "id": sid,
                    "label": label,
                    "encrypted": encrypted,
                    "locations": locations,
                    "confidence": max(hits, key=lambda h: RANK[h[0]])[0],
                    "evidence": [ev for _, ev in hits],
                    "source": "device",
                }
            )
    return out
