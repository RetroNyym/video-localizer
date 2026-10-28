from __future__ import annotations

import json
import os
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field

PIPER_REPO = "https://huggingface.co/rhasspy/piper-voices"
PIPER_RESOLVE = PIPER_REPO + "/resolve/main/"
PIPER_CATALOG_URL = PIPER_RESOLVE + "voices.json"
LOCAL_DATA_URLS = "https://huggingface.co/rhasspy/piper-voices/tree/main"

TR_VOICE_KEY = "tr_TR-dfki-medium"

TR_LICENSE = "CC BY-NC-SA 4.0"
TR_LICENSE_NOTE = (
    "DFKI Türkçe sesi: model kartındaki veri lisansı CC BY-NC-SA 4.0 — "
    "ticari kullanım için uygun değildir, atıf (attribution) zorunludur."
)
GENERIC_LICENSE = "Model kartını kontrol edin"
GENERIC_LICENSE_NOTE = (
    "Lisans koşulu ve atıf gerekliliği için sesin model kartını kontrol edin."
)

KOKORO_INFO = {
    "id": "kokoro",
    "name": "Kokoro",
    "license": "Apache-2.0",
    "license_note": "Apache-2.0 lisanslı model; Türkçe desteklenmiyor.",
    "turkish_supported": False,
    "languages": ["en-US", "en-GB", "ja", "es", "fr", "hi", "it", "pt-BR", "zh"],
    "model_url": (
        "https://github.com/thewh1teagle/kokoro-onnx/releases/download/"
        "model-files-v1.1/kokoro-v1.0.int8.onnx"
    ),
    "voices_url": (
        "https://github.com/thewh1teagle/kokoro-onnx/releases/download/"
        "model-files-v1.1/voices-v1.0.bin"
    ),
    "model_size_mb": 108,
    "voices_size_mb": 26,
    "source": "https://github.com/thewh1teagle/kokoro-onnx/releases/tag/model-files-v1.1",
    "model_card": "https://huggingface.co/hexgrad/Kokoro-82M",
}

KOKORO_LANGS = {
    "en-US": "English (US)",
    "en-GB": "English (UK)",
    "es": "Español",
    "fr": "Français",
    "hi": "हिन्दी",
    "it": "Italiano",
    "ja": "日本語",
    "pt-BR": "Português (BR)",
    "zh": "中文",
}

# Kokoro v1.1 konuşmacı listesi: (ses kimliği, ad, dil)
KOKORO_VOICES: list[tuple[str, str, str]] = [
    ("af_heart", "Heart", "en-US"),
    ("af_alloy", "Alloy", "en-US"),
    ("af_aoede", "Aoede", "en-US"),
    ("af_bella", "Bella", "en-US"),
    ("af_jessica", "Jessica", "en-US"),
    ("af_kore", "Kore", "en-US"),
    ("af_nicole", "Nicole", "en-US"),
    ("af_nova", "Nova", "en-US"),
    ("af_river", "River", "en-US"),
    ("af_sarah", "Sarah", "en-US"),
    ("af_sky", "Sky", "en-US"),
    ("am_adam", "Adam", "en-US"),
    ("am_echo", "Echo", "en-US"),
    ("am_eric", "Eric", "en-US"),
    ("am_fenrir", "Fenrir", "en-US"),
    ("am_liam", "Liam", "en-US"),
    ("am_michael", "Michael", "en-US"),
    ("am_onyx", "Onyx", "en-US"),
    ("am_puck", "Puck", "en-US"),
    ("am_santa", "Santa", "en-US"),
    ("bf_alice", "Alice", "en-GB"),
    ("bf_emma", "Emma", "en-GB"),
    ("bf_isabella", "Isabella", "en-GB"),
    ("bf_lily", "Lily", "en-GB"),
    ("bm_daniel", "Daniel", "en-GB"),
    ("bm_fable", "Fable", "en-GB"),
    ("bm_george", "George", "en-GB"),
    ("bm_lewis", "Lewis", "en-GB"),
    ("ef_dora", "Dora", "es"),
    ("em_alex", "Alex", "es"),
    ("em_santa", "Santa", "es"),
    ("ff_siwis", "Siwis", "fr"),
    ("hf_alpha", "Alpha", "hi"),
    ("hf_beta", "Beta", "hi"),
    ("hm_omega", "Omega", "hi"),
    ("hm_psi", "Psi", "hi"),
    ("if_sara", "Sara", "it"),
    ("im_nicola", "Nicola", "it"),
    ("jf_alpha", "Alpha", "ja"),
    ("jf_gongitsune", "Gongitsune", "ja"),
    ("jf_nezumi", "Nezumi", "ja"),
    ("jf_tebukuro", "Tebukuro", "ja"),
    ("jm_kumo", "Kumo", "ja"),
    ("pf_dora", "Dora", "pt-BR"),
    ("pm_alex", "Alex", "pt-BR"),
    ("pm_santa", "Santa", "pt-BR"),
    ("zf_xiaobei", "Xiaobei", "zh"),
    ("zf_xiaoni", "Xiaoni", "zh"),
    ("zf_xiaoxiao", "Xiaoxiao", "zh"),
    ("zf_xiaoyi", "Xiaoyi", "zh"),
    ("zm_yunjian", "Yunjian", "zh"),
    ("zm_yunxi", "Yunxi", "zh"),
    ("zm_yunxia", "Yunxia", "zh"),
    ("zm_yunyang", "Yunyang", "zh"),
]

COMMONVOICE_INFO = {
    "id": "commonvoice-tr",
    "name": "Mozilla Common Voice — Türkçe",
    "locale": "tr",
    "api": "https://commonvoice.mozilla.org/api/v1/languages",
    "page": "https://commonvoice.mozilla.org/tr",
    "target_sentence_count": 5000,
    "is_contributable": 1,
    "is_translated": 1,
    "note": (
        "Hazır seslendirme değil, konuşma veri kümesi. "
        "Kendi TTS modelinizi eğitmek için değerlendirilebilir."
    ),
    "refreshed": "2026-10-21",
}


def voices_root() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "VideoLocalizer", "voices")


def piper_dir() -> str:
    return os.path.join(voices_root(), "piper")


def kokoro_dir() -> str:
    return os.path.join(voices_root(), "kokoro")


def _download(url: str, dst: str, progress: Callable[[int, int], None] | None = None) -> str:
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "VideoLocalizer/0.1"})
    with urllib.request.urlopen(req, timeout=600) as resp, open(dst + ".part", "wb") as fh:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            fh.write(chunk)
            done += len(chunk)
            if progress:
                progress(done, total)
    os.replace(dst + ".part", dst)
    return dst


@dataclass
class VoiceInfo:
    engine: str
    id: str
    name: str
    language: str
    language_native: str = ""
    quality: str = ""
    num_speakers: int = 1
    size_mb: float = 0.0
    license: str = GENERIC_LICENSE
    license_note: str = GENERIC_LICENSE_NOTE
    source_url: str = PIPER_REPO
    installed: bool = False
    featured: bool = False
    installed_path: str | None = None
    languages: list[str] = field(default_factory=list)


def _load_piper_catalog() -> list[dict]:
    bundled = os.path.join(os.path.dirname(__file__), "data", "piper-voices.json")
    try:
        with open(bundled, encoding="utf-8") as fh:
            data = json.load(fh)
        return list(data.values())
    except Exception:
        return []


def refresh_piper_catalog() -> bool:
    try:
        with urllib.request.urlopen(
            urllib.request.Request(PIPER_CATALOG_URL, headers={"User-Agent": "VideoLocalizer/0.1"}),
            timeout=60,
        ) as resp:
            raw = resp.read().decode("utf-8")
        json.loads(raw)
        bundled = os.path.join(os.path.dirname(__file__), "data", "piper-voices.json")
        with open(bundled, "w", encoding="utf-8") as fh:
            fh.write(raw)
        return True
    except Exception:
        return False


def installed_piper_voices() -> dict[str, str]:
    out: dict[str, str] = {}
    folder = piper_dir()
    if not os.path.isdir(folder):
        return out
    for name in os.listdir(folder):
        if name.endswith(".onnx"):
            out[name[:-5]] = os.path.join(folder, name)
    return out


def piper_voice_files(key: str) -> list[str]:
    for entry in _load_piper_catalog():
        if entry.get("key") == key:
            return sorted(entry.get("files", {}).keys())
    return []


def piper_voice_size_mb(key: str) -> float:
    for entry in _load_piper_catalog():
        if entry.get("key") == key:
            total = sum(int(v.get("size_bytes", 0)) for v in entry.get("files", {}).values())
            return round(total / (1 << 20), 1)
    return 0.0


def download_piper_voice(key: str, progress: Callable[[str, int, int], None] | None = None) -> str:
    files = piper_voice_files(key)
    if not files:
        raise FileNotFoundError(f"Piper sesi bulunamadı: {key}")
    local = installed_piper_voices()
    target = local.get(key)
    if target:
        return target
    folder = piper_dir()
    os.makedirs(folder, exist_ok=True)
    for rel in files:
        name = os.path.basename(rel)
        dst = os.path.join(folder, name)
        if os.path.exists(dst) and os.path.getsize(dst) > 0:
            continue
        _download(
            PIPER_RESOLVE + rel,
            dst,
            (lambda n, t, r=rel: progress(r, n, t)) if progress else None,
        )
    return os.path.join(folder, f"{key}.onnx")


def piper_catalog(installed_only: bool = False) -> list[VoiceInfo]:
    installed = installed_piper_voices()
    out: list[VoiceInfo] = []
    for entry in _load_piper_catalog():
        key = entry.get("key", "")
        lang = entry.get("language", {})
        code = lang.get("code", "")
        if installed_only and key not in installed:
            continue
        is_tr = key == TR_VOICE_KEY
        out.append(
            VoiceInfo(
                engine="piper",
                id=key,
                name=f"Piper · {code} · {entry.get('quality', '')}",
                language=code,
                language_native=lang.get("name_native", ""),
                quality=entry.get("quality", ""),
                num_speakers=int(entry.get("num_speakers", 1)),
                size_mb=piper_voice_size_mb(key),
                license=TR_LICENSE if is_tr else GENERIC_LICENSE,
                license_note=TR_LICENSE_NOTE if is_tr else GENERIC_LICENSE_NOTE,
                source_url=f"{LOCAL_DATA_URLS}/{code.split('_')[0] if code else ''}",
                installed=key in installed,
                featured=is_tr,
                installed_path=installed.get(key),
            )
        )
    out.sort(key=lambda v: (not v.featured, not v.installed, v.language, v.name))
    return out


def sapi_catalog() -> list[VoiceInfo]:
    try:
        from . import tts as tts_mod

        voices = tts_mod.list_voices()
    except Exception:
        return []
    out: list[VoiceInfo] = []
    for vid, name in voices:
        low = name.lower()
        lang = "tr_TR" if "turk" in low else "en_US" if "english" in low else "unknown"
        out.append(
            VoiceInfo(
                engine="sapi",
                id=vid,
                name=f"Windows SAPI · {name}",
                language=lang,
                license="Windows dahili",
                license_note="Windows SAPI sesleri işletim sistemiyle gelir; model kartı yoktur.",
                source_url="https://learn.microsoft.com/windows/speech/",
                installed=True,
            )
        )
    return out


def kokoro_installed() -> tuple[bool, bool]:
    try:
        import kokoro_onnx  # noqa: F401
    except Exception:
        return False, False
    folder = kokoro_dir()
    model = os.path.join(folder, "kokoro-v1.0.int8.onnx")
    voices = os.path.join(folder, "voices-v1.0.bin")
    return True, (os.path.exists(model) and os.path.exists(voices))


def download_kokoro_models(progress: Callable[[str, int, int], None] | None = None) -> None:
    folder = kokoro_dir()
    os.makedirs(folder, exist_ok=True)
    for url, name in ((KOKORO_INFO["model_url"], "kokoro-v1.0.int8.onnx"),
                      (KOKORO_INFO["voices_url"], "voices-v1.0.bin")):
        dst = os.path.join(folder, name)
        if os.path.exists(dst) and os.path.getsize(dst) > 0:
            continue
        _download(url, dst, (lambda n, t, r=name: progress(r, n, t)) if progress else None)


def kokoro_catalog(installed_only: bool = False) -> list[VoiceInfo]:
    _lib_ok, ready = kokoro_installed()
    if installed_only and not ready:
        return []
    out: list[VoiceInfo] = []
    for vid, name, lang in KOKORO_VOICES:
        out.append(
            VoiceInfo(
                engine="kokoro",
                id=vid,
                name=f"Kokoro · {name}",
                language=lang,
                language_native=KOKORO_LANGS.get(lang, ""),
                license=KOKORO_INFO["license"],
                license_note=KOKORO_INFO["license_note"],
                source_url=KOKORO_INFO["source"],
                installed=ready,
                size_mb=0.0,
            )
        )
    return out


def refresh_commonvoice() -> dict:
    try:
        with urllib.request.urlopen(
            urllib.request.Request(COMMONVOICE_INFO["api"], headers={"User-Agent": "VideoLocalizer/0.1"}),
            timeout=30,
        ) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        for item in data:
            if item.get("name") == COMMONVOICE_INFO["locale"]:
                snapshot = dict(COMMONVOICE_INFO)
                snapshot.update(
                    {
                        "target_sentence_count": item.get("target_sentence_count"),
                        "is_contributable": item.get("is_contributable"),
                        "is_translated": item.get("is_translated"),
                    }
                )
                import datetime

                snapshot["refreshed"] = datetime.date.today().isoformat()
                return snapshot
    except Exception:
        pass
    return dict(COMMONVOICE_INFO)


def search_voices(query: str = "", engine: str = "", installed_only: bool = False) -> list[VoiceInfo]:
    result: list[VoiceInfo] = []
    if not engine or engine == "piper":
        result += piper_catalog(installed_only=installed_only)
    if not engine or engine == "sapi":
        result += sapi_catalog()
    if not engine or engine == "kokoro":
        result += kokoro_catalog(installed_only=installed_only)
    q = query.strip().lower()
    if q:
        result = [
            v for v in result
            if q in v.name.lower() or q in v.language.lower() or q in v.id.lower()
        ]
    return result
