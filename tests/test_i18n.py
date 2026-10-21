import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from videoloc import i18n  # noqa: E402


def test_tr_and_en_have_identical_keys():
    tr_keys = set(i18n.S["tr"])
    en_keys = set(i18n.S["en"])
    assert tr_keys == en_keys, f"eksik: {tr_keys ^ en_keys}"


def test_t_returns_string_for_every_key_in_both_languages():
    for lang in i18n.S:
        for key in i18n.S[lang]:
            value = i18n.t(key, lang)
            assert isinstance(value, str) and value


def test_format_placeholders_present():
    assert "{engine}" in i18n.t("tog2_s", "en")
    assert "{engine}" in i18n.t("tog2_s", "tr")
    out = i18n.t("m_across", "en", n=5)
    assert "5" in out


def test_unknown_key_returns_key():
    assert i18n.t("yok_boyle_key", "tr") == "yok_boyle_key"


def test_languages_ui_codes():
    assert set(i18n.LANGUAGES_UI) == {"tr", "en"}
