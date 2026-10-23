"""Crawl safety and form-fill words in many languages, the resource-id check, the saved test account."""

from __future__ import annotations

import json
import stat

import pytest

from appscreenmap.core import accounts, locales
from appscreenmap.core.config import CrawlConfig, validate_playbook

# One destructive label per language that the default config must refuse to tap.
DESTRUCTIVE = {
    "es": ["Cerrar sesión", "Eliminar cuenta", "Pagar ahora"],
    "fr": ["Déconnexion", "Supprimer le compte", "Acheter"],
    "de": ["Abmelden", "Konto löschen", "Jetzt kaufen"],
    "pt": ["Sair da conta", "Excluir conta", "Comprar"],
    "it": ["Esci", "Elimina account", "Acquista"],
    "nl": ["Uitloggen", "Account verwijderen", "Betalen"],
    "sv": ["Logga ut", "Ta bort konto", "Betala"],
    "pl": ["Wyloguj się", "Usuń konto", "Kup teraz"],
    "tr": ["Çıkış yap", "Hesabı sil", "Satın al"],
    "ru": ["Выйти из аккаунта", "Удалить аккаунт", "Оплатить"],
    "uk": ["Вийти з акаунта", "Видалити акаунт", "Оплатити"],
    "ar": ["تسجيل الخروج", "حذف الحساب", "شراء"],
    "he": ["התנתק", "מחק חשבון", "תשלום"],
    "hi": ["लॉग आउट", "खाता हटाएं", "खरीदें"],
    "bn": ["লগ আউট", "অ্যাকাউন্ট মুছুন", "কিনুন"],
    "id": ["Keluar dari akun", "Hapus akun", "Beli sekarang"],
    "ms": ["Log keluar", "Padam akaun", "Beli sekarang"],
    "vi": ["Đăng xuất", "Xóa tài khoản", "Thanh toán"],
    "th": ["ออกจากระบบ", "ลบบัญชี", "ชำระเงิน"],
    "zh-Hans": ["退出登录", "删除账号", "立即购买"],
    "zh-Hant": ["登出", "刪除帳號", "立即購買"],
    "ja": ["ログアウト", "アカウント削除", "今すぐ購入"],
    "ko": ["로그아웃", "계정 삭제", "구독"],
}
# Everyday labels, including the opposite of log out (log in), that must stay tappable.
BENIGN = {
    "es": ["Inicio", "Buscar", "Ajustes", "Perfil", "Siguiente", "Cancelar", "Iniciar sesión", "Aceptar"],
    "fr": ["Accueil", "Rechercher", "Paramètres", "Profil", "Suivant", "Annuler", "Connexion", "Continuer"],
    "de": [
        "Startseite",
        "Suche",
        "Einstellungen",
        "Profil",
        "Weiter",
        "Abbrechen",
        "Anmelden",
        "Registrieren",
    ],
    "pt": ["Início", "Pesquisar", "Configurações", "Perfil", "Próximo", "Cancelar", "Entrar", "Continuar"],
    "it": ["Home", "Cerca", "Impostazioni", "Profilo", "Avanti", "Annulla", "Accedi", "Continua"],
    "nl": ["Start", "Zoeken", "Instellingen", "Profiel", "Volgende", "Annuleren", "Inloggen", "Doorgaan"],
    "sv": ["Hem", "Sök", "Inställningar", "Profil", "Nästa", "Avbryt", "Logga in", "Fortsätt"],
    "pl": ["Start", "Szukaj", "Ustawienia", "Profil", "Dalej", "Anuluj", "Zaloguj się", "Kontynuuj"],
    "tr": ["Ana sayfa", "Ara", "Ayarlar", "Profil", "İleri", "İptal", "Giriş yap", "Devam"],
    "ru": ["Главная", "Поиск", "Настройки", "Профиль", "Далее", "Отмена", "Войти", "Продолжить"],
    "uk": ["Головна", "Пошук", "Налаштування", "Профіль", "Далі", "Скасувати", "Увійти", "Продовжити"],
    "ar": ["الرئيسية", "الإعدادات", "الملف الشخصي", "التالي", "إلغاء", "تسجيل الدخول", "متابعة"],
    "he": ["בית", "הגדרות", "פרופיל", "הבא", "ביטול", "התחברות", "המשך"],
    "hi": ["होम", "सेटिंग्स", "प्रोफ़ाइल", "आगे", "रद्द करें", "लॉग इन", "जारी रखें"],
    "bn": ["হোম", "সেটিংস", "প্রোফাইল", "পরবর্তী", "বাতিল", "লগ ইন", "চালিয়ে যান"],
    "id": ["Beranda", "Pengaturan", "Profil", "Berikutnya", "Batal", "Masuk", "Lanjutkan"],
    "ms": ["Laman utama", "Tetapan", "Profil", "Seterusnya", "Batal", "Log masuk", "Teruskan"],
    "vi": ["Trang chủ", "Cài đặt", "Hồ sơ", "Tiếp theo", "Hủy", "Đăng nhập", "Tiếp tục"],
    "th": ["หน้าแรก", "การตั้งค่า", "โปรไฟล์", "ถัดไป", "ยกเลิก", "เข้าสู่ระบบ", "ดำเนินการต่อ"],
    "zh-Hans": ["首页", "设置", "个人资料", "下一步", "取消", "登录", "继续"],
    "zh-Hant": ["首頁", "設定", "個人資料", "下一步", "取消", "登入", "繼續"],
    "ja": ["ホーム", "設定", "プロフィール", "次へ", "キャンセル", "ログイン", "続ける"],
    "ko": ["홈", "설정", "프로필", "다음", "취소", "로그인", "계속"],
}


def test_catalogue_loads_and_every_language_is_covered_by_the_tests():
    codes = [lang.code for lang in locales.load_languages()]
    assert len(codes) == len(set(codes)) >= 23
    assert set(codes) == set(DESTRUCTIVE) == set(BENIGN)
    assert all(len(lang.blocked) >= 8 for lang in locales.load_languages())


def test_destructive_labels_are_blocked_in_every_language():
    cfg = CrawlConfig()
    missed = {code: [x for x in labels if not cfg.is_blocked(x)] for code, labels in DESTRUCTIVE.items()}
    assert {code: m for code, m in missed.items() if m} == {}


def test_everyday_labels_stay_tappable_in_every_language():
    cfg = CrawlConfig()
    blocked = {code: [x for x in labels if cfg.is_blocked(x)] for code, labels in BENIGN.items()}
    assert {code: b for code, b in blocked.items() if b} == {}


def test_english_and_user_rules_still_apply_and_languages_can_be_limited():
    assert CrawlConfig().is_blocked("Log out") and CrawlConfig().is_blocked("Sign out")
    only_es = CrawlConfig(languages=["es"])
    assert only_es.is_blocked("Cerrar sesión") and not only_es.is_blocked("ログアウト")
    assert not CrawlConfig(languages=["fr"]).is_blocked("Cerrar sesión")
    assert CrawlConfig(blocked_text=[r"\bmeinwort\b"]).is_blocked("meinwort")


def test_form_fields_get_sensible_values_in_other_languages():
    cfg = CrawlConfig()
    assert cfg.input_for("Correo electrónico") == "qa.tester@example.com"
    assert cfg.input_for("メールアドレス") == "qa.tester@example.com"
    assert cfg.input_for("Teléfono") == "5551234567"
    assert cfg.input_for("邮编") == "94105"
    assert cfg.input_for("Passwort bestätigen") == "Passw0rd!"
    assert cfg.input_for("Nachname") == "Tester"
    assert cfg.input_for("something unrelated") == "test"


def test_locale_values_match_the_english_defaults():
    from appscreenmap.core.config import DEFAULT_INPUTS, LOCALE_INPUT_VALUES

    assert set(LOCALE_INPUT_VALUES.values()) <= set(DEFAULT_INPUTS.values())


def test_known_languages_are_covered():
    tags = ["en", "en-GB", "fr-CA", "pt-BR", "zh-CN", "zh-TW", "zh-Hant", "ja", "ar", "iw", ""]
    # iw is Android's old tag for Hebrew: not matched, documented below
    assert [t for t in tags if not (locales.covers(t) or t == "iw")] == []


def test_languages_without_words_are_not_covered():
    assert not locales.covers("sw") and not locales.covers("el-GR") and not locales.covers("fa")
    assert locales.covers("en-XA")  # the English pseudo-locale


def test_resource_ids_block_whatever_the_screen_language():
    ids = ["app:id/btn_logout", "deleteAccount", "log_out_button", "app:id/signOut", "buy_now", "pay_now_btn"]
    assert [r for r in ids if not CrawlConfig().is_blocked_id(r)] == []


def test_ordinary_resource_ids_are_not_blocked():
    ids = ["call_to_action", "report_list", "unsubscribe", "payment_methods", "ContinueButton", ""]
    assert [r for r in ids if CrawlConfig().is_blocked_id(r)] == []


def test_bad_word_lists_are_rejected(tmp_path):
    def load(doc):
        f = tmp_path / "l.json"
        f.write_text(json.dumps({"schema": 1, "languages": doc}))
        locales.load_languages.cache_clear()
        return locales.load_languages(f)

    good = {"code": "xx", "name": "X", "boundary": True, "blocked": ["abc"]}
    assert load([good])[0].code == "xx"
    with pytest.raises(locales.LocaleError, match="duplicate"):
        load([good, good])
    with pytest.raises(locales.LocaleError, match="at least two"):
        load([{**good, "blocked": ["a"]}])
    with pytest.raises(locales.LocaleError, match="unknown input kind"):
        load([{**good, "inputs": {"shoe": ["abc"]}}])
    with pytest.raises(locales.LocaleError, match="no blocked"):
        load([{**good, "blocked": []}])
    locales.load_languages.cache_clear()


# ── test account ─────────────────────────────────────────────────────────────
def test_account_is_made_once_kept_private_and_reused(tmp_path):
    first = accounts.load_or_create("co.example.app", root=tmp_path)
    assert first["new"] and first["email"].startswith("asm+") and first["email"].endswith("@example.com")
    assert len(first["password"]) >= 16 and first["status"] == "new"
    path = accounts.vault_path("co.example.app", tmp_path)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    again = accounts.load_or_create("co.example.app", root=tmp_path)
    assert not again["new"] and (again["email"], again["password"]) == (first["email"], first["password"])
    other = accounts.load_or_create("co.example.other", "qa-{rand}@corp.test", tmp_path)
    assert other["email"].endswith("@corp.test") and other["email"] != first["email"]
    accounts.mark("co.example.app", "created", tmp_path)
    assert accounts.load_or_create("co.example.app", root=tmp_path)["status"] == "created"
    assert accounts.env_for(first) == {"ACCOUNT_EMAIL": first["email"], "ACCOUNT_PASSWORD": first["password"]}


def test_playbook_config_is_parsed_validated_and_account_aware(tmp_path):
    toml = tmp_path / "c.toml"
    toml.write_text(
        '[account]\nemail = "t+{rand}@x.test"\n'
        '[[playbook.before]]\ntap = "B2BSignUp"\n'
        '[[playbook.before]]\ntype = "AccessCode"\nvalue = "ALLTABS"\n'
        '[[playbook.before]]\ntype = "EmailInput"\nvalue = "${ACCOUNT_EMAIL}"\n'
        '[[playbook.after]]\nscroll = "end"\n'
    )
    cfg = CrawlConfig.load(toml)
    assert cfg.account_email == "t+{rand}@x.test" and len(cfg.playbook["before"]) == 3
    assert cfg.uses_account() and cfg.missing_secrets({}) == []
    assert not CrawlConfig().uses_account()
    for bad in (
        {"before": [{"tap": "x", "back": True}]},
        {"before": [{"type": "x"}]},
        {"before": [{"scroll": "sideways"}]},
        {"middle": [{"tap": "x"}]},
        {"after": [{}]},
    ):
        with pytest.raises(ValueError):
            validate_playbook(bad)
