from appscreenmap.drivers.device import (
    PROBE,
    build_info,
    caveats,
    describe,
    os_skin,
    parse_getprop,
    parse_probe,
    rows,
    window_class,
)


def getprop(**props) -> str:
    return "\n".join(f"[{k.replace('__', '.')}]: [{v}]" for k, v in props.items())


def probe(**sections) -> str:
    """What PROBE prints: one marker line per section, then the command's output."""
    names = [part.split("@@ASM@@")[1].split(";")[0] for part in PROBE.split("echo ")[1:]]
    return "".join(f"@@ASM@@{n}\n{sections.get(n, '')}\n" for n in names)


EMULATOR_PROPS = {
    "ro.product.model": "sdk_gphone16k_arm64",
    "ro.product.manufacturer": "Google",
    "ro.product.brand": "google",
    "ro.product.device": "emu64a16k",
    "ro.build.version.release": "17",
    "ro.build.version.sdk": "37",
    "ro.build.version.codename": "REL",
    "ro.build.fingerprint": "google/sdk_gphone16k_arm64/emu64a16k:17/AP4A/123:userdebug/dev-keys",
    "ro.build.type": "userdebug",
    "ro.kernel.qemu": "1",
    "ro.hardware": "ranchu",
    "ro.boot.qemu.avd_name": "Pixel_8_API_37",
    "ro.product.cpu.abi": "arm64-v8a",
    "ro.product.cpu.abilist": "arm64-v8a",
    "persist.sys.locale": "en-US",
    "persist.sys.timezone": "Europe/London",
}

PHONE_PROBE = {
    "wm_size": "Physical size: 1080x2400",
    "wm_density": "Physical density: 420",
    "font_scale": "1.0",
    "features": "feature:android.hardware.touchscreen\nfeature:android.hardware.telephony",
    "meminfo": "MemTotal:        8029676 kB",
    "df": "/dev/block/dm-48  115119256  20147596  94840276  18% /data",
    "kernel": "6.6.30-android15",
    "night": "Night mode: no",
    "navigation_mode": "2",
    "a11y_services": "null",
    "bold_text": "0",
    "high_contrast": "0",
    "inversion": "null",
    "animator_scale": "1.0",
    "low_power": "0",
    "airplane": "0",
    "battery": "Current Battery Service state:\n  AC powered: false\n  USB powered: true\n  level: 87",
    "webview": "Current WebView package (name, version): (com.google.android.webview, 141.0.7390.43)",
    "gms": "    versionName=25.38.32 (190400-812345678)",
}


def test_parse_getprop_and_probe_roundtrip():
    props = parse_getprop("[ro.product.model]: [Pixel 8]\n[empty]: []\nnoise line\n")
    assert props == {"ro.product.model": "Pixel 8", "empty": ""}
    p = parse_probe(probe(wm_size="Physical size: 1080x2400", kernel="6.1"))
    assert p["wm_size"] == "Physical size: 1080x2400" and p["kernel"] == "6.1" and p["gms"] == ""


def test_emulator_is_named_by_avd_and_flagged():
    info = build_info(
        "emulator-5554", parse_getprop(getprop(**EMULATOR_PROPS)), parse_probe(probe(**PHONE_PROBE))
    )
    # original keys keep their meaning
    assert info["model"] == "sdk_gphone16k_arm64" and info["android"] == "17" and info["sdk"] == "37"
    assert (info["width"], info["height"], info["density"], info["font_scale"]) == (1080, 2400, 420, 1.0)
    assert info["type"] == "emulator" and info["connection"] == "emulator"
    assert info["name"] == "Android Emulator (Pixel_8_API_37)" and info["avd"] == "Pixel_8_API_37"
    assert info["form_factor"] == "phone"
    assert info["os"]["build_type"] == "userdebug" and info["os"]["skin"] is None
    assert info["display"]["width_dp"] == 411 and info["display"]["window_class"] == "compact"
    assert info["hardware"]["ram_mb"] == 7841 and info["hardware"]["storage_free_mb"] == 92617
    st = info["settings"]
    assert st["navigation"] == "gesture" and st["dark_mode"] is False and st["talkback"] is False
    assert st["battery"] == 87 and st["charging"] is True and st["locale"] == "en-US"
    assert info["software"] == {
        "webview": "com.google.android.webview 141.0.7390.43",
        "play_services": "25.38.32",
    }
    assert "emulator" in caveats(info)[0]


def test_emulator_detected_without_qemu_props():
    props = {"ro.product.model": "Android SDK built for x86", "ro.product.manufacturer": "unknown"}
    assert build_info("emulator-5556", props, {})["type"] == "emulator"
    assert build_info("192.168.1.20:5555", {"ro.genymotion.version": "3.6"}, {})["name"] == "Genymotion"


def test_real_samsung_gets_brand_model_and_one_ui():
    props = {
        "ro.product.model": "SM-S911B",
        "ro.product.manufacturer": "samsung",
        "ro.product.brand": "samsung",
        "ro.product.device": "dm1q",
        "ro.build.version.release": "14",
        "ro.build.version.sdk": "34",
        "ro.build.version.codename": "REL",
        "ro.build.version.oneui": "60100",
        "ro.build.version.security_patch": "2024-09-01",
        "ro.build.type": "user",
        "ro.hardware": "qcom",
        "ro.soc.manufacturer": "QTI",
        "ro.soc.model": "SM8550",
    }
    p = dict(
        PHONE_PROBE,
        night="Night mode: yes",
        a11y_services="com.google.android.marvin.talkback/.TalkBackService",
    )
    info = build_info("R5CW1234ABC", props, parse_probe(probe(**p)))
    assert info["type"] == "physical" and info["connection"] == "usb"
    assert info["name"] == "Samsung SM-S911B" and info["brand"] == "samsung" and info["codename"] == "dm1q"
    assert info["os"]["skin"] == "One UI 6.1" and info["hardware"]["soc"] == "QTI SM8550"
    assert info["settings"]["dark_mode"] is True and info["settings"]["talkback"] is True
    assert describe(info) == "Samsung SM-S911B · physical phone · Android 14 (SDK 34), One UI 6.1"
    c = caveats(info)
    assert any("TalkBack" in x for x in c) and any("dark mode" in x for x in c)
    assert not any("emulator" in x for x in c)


def test_marketing_name_wins_and_is_not_double_branded():
    props = {
        "ro.product.model": "2211133G",
        "ro.product.marketname": "Xiaomi 13",
        "ro.product.manufacturer": "Xiaomi",
        "ro.product.brand": "Xiaomi",
        "ro.mi.os.version.name": "OS1.0",
        "ro.build.version.release": "14",
        "ro.build.version.sdk": "34",
    }
    info = build_info("abc123", props, {})
    assert info["name"] == "Xiaomi 13" and info["os"]["skin"] == "HyperOS 1.0"
    assert describe(info).startswith("Xiaomi 13 (2211133G) · physical")
    pixel = build_info("x", {"ro.product.model": "Pixel 8 Pro", "ro.product.manufacturer": "Google"}, {})
    assert pixel["name"] == "Google Pixel 8 Pro"


def test_form_factor_and_window_class():
    fold = build_info(
        "x",
        {"ro.product.model": "Pixel Fold"},
        parse_probe(
            probe(
                wm_size="Physical size: 2208x1840",
                wm_density="Physical density: 420",
                features="feature:android.hardware.sensor.hinge_angle",
            )
        ),
    )
    assert fold["form_factor"] == "foldable" and fold["display"]["window_class"] == "expanded"
    tablet = build_info(
        "x",
        {"ro.build.characteristics": "tablet"},
        parse_probe(
            probe(
                wm_size="Physical size: 1600x2560\nOverride size: 1200x1920",
                wm_density="Physical density: 320",
            )
        ),
    )
    assert tablet["form_factor"] == "tablet"
    assert (tablet["width"], tablet["display"]["physical_width"]) == (1200, 1600)  # override wins
    assert [window_class(w) for w in (411, 600, 839, 840, None)] == [
        "compact",
        "medium",
        "medium",
        "expanded",
        None,
    ]


def test_skins():
    assert os_skin({"ro.build.version.oneui": "50101"}) == "One UI 5.1.1"
    assert os_skin({"ro.miui.ui.version.name": "V14"}) == "MIUI 14"
    assert os_skin({"ro.build.version.oplusrom": "V14.0", "ro.product.brand": "OnePlus"}) == "OxygenOS 14.0"
    assert os_skin({"ro.build.version.oplusrom": "V14.0", "ro.product.brand": "OPPO"}) == "ColorOS 14.0"
    assert os_skin({"ro.build.version.release": "15"}) is None


def test_caveats_for_conditions_that_skew_results():
    dev = {
        "type": "physical",
        "font_scale": 2.0,
        "os": {"codename": "Baklava"},
        "settings": {"power_saver": True, "battery": 9, "charging": False, "airplane_mode": True},
        "hardware": {"storage_free_mb": 120},
    }
    text = " | ".join(caveats(dev))
    for want in ("power saver", "battery at 9%", "font scale 2", "airplane", "preview build", "120 MB"):
        assert want in text


def test_old_runs_without_new_fields_still_describe():
    old = {"serial": "emulator-5554", "model": "sdk_gphone16k_arm64", "manufacturer": "Google", "android": "17",
           "sdk": "37", "width": 1080, "height": 2400, "density": 420, "font_scale": 1.0}  # fmt: skip
    assert describe(old) == "Google sdk_gphone16k_arm64 · Android 17 (SDK 37)"
    r = dict(rows(old))
    assert r["Device"] == "Google sdk_gphone16k_arm64" and r["Screen"] == "1080×2400 px, 420 dpi"
    assert "TalkBack" not in r and caveats(old) == []
    assert dict(rows({}))["Font scale"] == "1.0 (assumed)"
