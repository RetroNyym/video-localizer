from __future__ import annotations

LANGUAGES: dict[str, str] = {
    "Türkçe": "tr",
    "İngilizce": "en",
    "Arapça": "ar",
    "Almanca": "de",
    "Fransızca": "fr",
    "İspanyolca": "es",
    "İtalyanca": "it",
    "Portekizce (Brezilya)": "pt",
    "Rusça": "ru",
    "Farsça": "fa",
    "İbranice": "he",
    "Felemenkçe": "nl",
    "Lehçe": "pl",
    "Ukraynaca": "uk",
    "Çekçe": "cs",
    "Romence": "ro",
    "Macarca": "hu",
    "Bulgarca": "bg",
    "Yunanca": "el",
    "İsveççe": "sv",
    "Norveççe": "no",
    "Danca": "da",
    "Fince": "fi",
    "Sırpça": "sr",
    "Hırvatça": "hr",
    "Endonezce": "id",
    "Vietnamca": "vi",
    "Tayca": "th",
    "Malayca": "ms",
    "Japonca": "ja",
    "Korece": "ko",
    "Çince (Basitleştirilmiş)": "zh-CN",
    "Çince (Geleneksel)": "zh-TW",
    "Hintçe": "hi",
    "Bengalce": "bn",
    "Filipince": "fil",
    "Svahili": "sw",
}

CODE_TO_NAME: dict[str, str] = {code: name for name, code in LANGUAGES.items()}

AUTO_CODE = "auto"


def display_name(code: str) -> str:
    if code == AUTO_CODE:
        return "Otomatik algıla"
    return CODE_TO_NAME.get(code, code)
