import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from videoloc import voices  # noqa: E402


def test_piper_catalog_loads_and_features_turkish():
    catalog = voices.piper_catalog()
    assert len(catalog) > 100
    tr = [v for v in catalog if v.id == voices.TR_VOICE_KEY]
    assert len(tr) == 1
    assert tr[0].featured
    assert tr[0].license == "CC BY-NC-SA 4.0"
    assert "ticari" in tr[0].license_note
    assert tr[0].language == "tr_TR"


def test_piper_turkish_voice_files_present_in_bundled_catalog():
    files = voices.piper_voice_files(voices.TR_VOICE_KEY)
    assert any(f.endswith(".onnx") for f in files)
    assert any(f.endswith(".onnx.json") for f in files)
    assert all(f.startswith("tr/") for f in files)
    assert voices.piper_voice_size_mb(voices.TR_VOICE_KEY) > 50


def test_kokoro_info_has_no_turkish_and_apache_license():
    info = voices.KOKORO_INFO
    assert info["license"] == "Apache-2.0"
    assert info["turkish_supported"] is False
    assert "tr" not in [x[:2] for x in info["languages"]]
    assert info["model_url"].startswith("https://")
    assert info["voices_url"].startswith("https://")


def test_commonvoice_snapshot_for_turkish():
    cv = voices.COMMONVOICE_INFO
    assert cv["locale"] == "tr"
    assert cv["target_sentence_count"] == 5000
    assert "veri kümesi" in cv["note"]
    assert cv["page"].startswith("https://commonvoice.mozilla.org")


def test_refresh_commonvoice_falls_back_to_snapshot(monkeypatch):
    def boom(*_args, **_kwargs):
        raise OSError("offline")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    data = voices.refresh_commonvoice()
    assert data["locale"] == "tr"
    assert data["target_sentence_count"] == 5000


def test_download_url_structure():
    files = voices.piper_voice_files(voices.TR_VOICE_KEY)
    assert voices.PIPER_RESOLVE.startswith("https://huggingface.co/")
    for rel in files:
        assert not rel.startswith("/")
    assert "kokoro-onnx/releases" in voices.KOKORO_INFO["model_url"]


def test_search_voices_filters_by_language():
    hits = voices.search_voices(query="tr_TR")
    assert any(v.id == voices.TR_VOICE_KEY for v in hits)
    hits2 = voices.search_voices(query="zzz-none")
    assert hits2 == []


def test_kokoro_roster_complete_and_unique():
    catalog = voices.kokoro_catalog()
    assert len(catalog) == 54
    ids = [v.id for v in catalog]
    assert len(set(ids)) == len(ids)
    names = {v.name.replace("Kokoro · ", "") for v in catalog}
    assert {"Heart", "Bella", "Emma", "Dora", "Siwis", "Xiaoxiao"} <= names
    langs = {v.language for v in catalog}
    assert langs == set(voices.KOKORO_LANGS)
    assert "tr_TR" not in langs


def test_kokoro_voices_map_to_espeak_language_codes():
    from videoloc import tts

    for vid, _name, _lang in voices.KOKORO_VOICES:
        assert vid[:2] in tts._KOKORO_LANG_BY_PREFIX, vid
    assert tts._KOKORO_LANG_BY_PREFIX["ff"] == "fr-fr"
    assert tts._KOKORO_LANG_BY_PREFIX["zf"] == "cmn"


def test_search_voices_can_filter_kokoro_and_finds_by_name():
    only_kokoro = voices.search_voices(engine="kokoro")
    assert len(only_kokoro) == 54
    assert all(v.engine == "kokoro" for v in only_kokoro)
    bella = voices.search_voices(query="bella")
    assert {v.id for v in bella} == {"af_bella", "bf_isabella"}
    assert voices.search_voices(engine="piper") and all(
        v.engine == "piper" for v in voices.search_voices(engine="piper")
    )

