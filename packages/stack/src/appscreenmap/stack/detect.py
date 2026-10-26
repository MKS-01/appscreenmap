"""Which framework, language and UI toolkit an APK uses, from what it contains: native library names, asset paths and
class names in the dex string table. Each rule names its confidence; nothing is decompiled.

`certain`: only that stack ships it (its runtime library). `strong`: a marker the stack's build always leaves, but
another stack could in principle carry. `likely`: a hint, e.g. libraries most often used from shared KMP code.
"""

from __future__ import annotations

RANK = {"certain": 3, "strong": 2, "likely": 1}

# (id, label, category, [(kind, pattern, confidence)]). kind: lib = a native library file name, lib-prefix = its
# start, path = an entry path prefix, dex = a class descriptor prefix in the dex string table.
RULES: list[tuple[str, str, str, list[tuple[str, str, str]]]] = [
    (
        "flutter",
        "Flutter",
        "framework",
        [("lib", "libflutter.so", "certain"), ("path", "assets/flutter_assets/", "certain")],
    ),
    (
        "react-native",
        "React Native",
        "framework",
        [
            ("lib", "libreactnative.so", "certain"),
            ("lib", "libreactnativejni.so", "certain"),
            ("dex", "Lcom/facebook/react/ReactActivity;", "strong"),
            ("path", "assets/index.android.bundle", "strong"),
        ],
    ),
    ("expo", "Expo", "framework", [("dex", "Lexpo/modules/", "certain")]),
    (
        "hermes",
        "Hermes JS engine",
        "runtime",
        [("lib", "libhermes.so", "certain"), ("lib", "libhermesvm.so", "certain")],
    ),
    ("jsc", "JavaScriptCore", "runtime", [("lib", "libjsc.so", "certain")]),
    ("unity", "Unity", "framework", [("lib", "libunity.so", "certain")]),
    ("il2cpp", "IL2CPP scripting backend", "runtime", [("lib", "libil2cpp.so", "certain")]),
    (
        "unreal",
        "Unreal Engine",
        "framework",
        [("lib", "libUE4.so", "certain"), ("lib", "libUnreal.so", "certain")],
    ),
    (
        "dotnet",
        ".NET for Android (Xamarin / MAUI)",
        "framework",
        [
            ("lib", "libmonodroid.so", "certain"),
            ("lib", "libmonosgen-2.0.so", "certain"),
            ("lib", "libxamarin-app.so", "certain"),
            ("path", "assemblies/", "strong"),
        ],
    ),
    ("maui", ".NET MAUI", "framework", [("dex", "Lmicrosoft/maui/", "strong")]),
    (
        "capacitor",
        "Capacitor",
        "framework",
        [("dex", "Lcom/getcapacitor/", "certain"), ("path", "assets/capacitor.config.json", "certain")],
    ),
    (
        "cordova",
        "Apache Cordova",
        "framework",
        [("path", "assets/www/cordova.js", "certain"), ("dex", "Lorg/apache/cordova/", "certain")],
    ),
    ("nativescript", "NativeScript", "framework", [("lib", "libNativeScript.so", "certain")]),
    (
        "qt",
        "Qt",
        "framework",
        [("lib-prefix", "libQt5Core", "certain"), ("lib-prefix", "libQt6Core", "certain")],
    ),
    (
        "compose-multiplatform",
        "Compose Multiplatform",
        "kmp",
        [
            ("dex", "Lorg/jetbrains/compose/resources/", "strong"),
            ("path", "assets/composeResources/", "strong"),
            ("path", "composeResources/", "strong"),
        ],
    ),
    (
        "kmp-libraries",
        "Kotlin Multiplatform libraries",
        "kmp",
        [
            ("dex", "Lio/ktor/client/", "likely"),
            ("dex", "Lapp/cash/sqldelight/", "likely"),
            ("dex", "Lkotlinx/datetime/", "likely"),
            ("dex", "Lco/touchlab/", "likely"),
            ("dex", "Ldev/icerock/moko/", "likely"),
        ],
    ),
    (
        "kotlin",
        "Kotlin",
        "language",
        [("dex", "Lkotlin/jvm/internal/Intrinsics;", "strong"), ("path", "kotlin/", "strong")],
    ),
    (
        "compose",
        "Jetpack Compose",
        "ui",
        [
            ("path", "META-INF/androidx.compose.runtime_runtime.version", "certain"),
            ("dex", "Landroidx/compose/runtime/", "strong"),
        ],
    ),
]

CROSS_PLATFORM = {
    "flutter",
    "react-native",
    "unity",
    "unreal",
    "dotnet",
    "capacitor",
    "cordova",
    "nativescript",
    "qt",
}


def _matches(kind: str, pattern: str, libs: set[str], paths: list[str], dex: bytes) -> list[str]:
    if kind == "lib":
        return [pattern] if pattern in libs else []
    if kind == "lib-prefix":
        return sorted(lib for lib in libs if lib.startswith(pattern))[:3]
    if kind == "path":
        return next(([p] for p in paths if p.startswith(pattern)), [])
    return [pattern.strip("L;").replace("/", ".")] if pattern.encode() in dex else []


def detect(libs: set[str], paths: list[str], dex: bytes) -> list[dict]:
    """Signals found: [{"id", "label", "category", "confidence", "evidence", "source": "device"}]."""
    out = []
    for rid, label, category, checks in RULES:
        hits = [(conf, ev) for kind, pat, conf in checks for ev in _matches(kind, pat, libs, paths, dex)]
        if not hits:
            continue
        best = max(hits, key=lambda h: RANK[h[0]])[0]
        out.append(
            {
                "id": rid,
                "label": label,
                "category": category,
                "confidence": best,
                "evidence": [ev for _, ev in hits],
                "source": "device",
            }
        )
    return out


def summarize(signals: list[dict]) -> dict:
    """{"kind": native | cross-platform | kmp, "summary": "…"}: the one line the overview card shows."""
    ids = {s["id"]: s for s in signals}
    frameworks = [s for s in signals if s["id"] in CROSS_PLATFORM]
    if frameworks:
        main = max(frameworks, key=lambda s: RANK[s["confidence"]])
        extra = [ids[i]["label"] for i in ("expo", "maui", "hermes", "jsc", "il2cpp") if i in ids]
        return {
            "kind": "cross-platform",
            "summary": main["label"] + (f" ({', '.join(extra)})" if extra else ""),
        }
    lang = "Kotlin" if "kotlin" in ids else "Java"
    ui = "Jetpack Compose" if "compose" in ids else "Android Views"
    if "compose-multiplatform" in ids:
        return {"kind": "kmp", "summary": f"Kotlin Multiplatform: Compose Multiplatform UI, {lang}"}
    if "kmp-libraries" in ids:
        return {"kind": "native", "summary": f"Native Android: {lang}, {ui} (shared KMP code possible)"}
    return {"kind": "native", "summary": f"Native Android: {lang}, {ui}"}
