from __future__ import annotations

import os
import re
import shutil
import struct
import subprocess
import time
import wave
from collections.abc import Callable

from .srt import Cue

Progress = Callable[[int, int, str], None]

_TAG_RE = re.compile(r"\{[^}]*\}|</?[A-Za-z][^<>]*>")


class TTSError(RuntimeError):
    pass


def available() -> bool:
    try:
        import pyttsx3  # noqa: F401
    except Exception:
        return False
    return True


def list_voices() -> list[tuple[str, str]]:
    if not available():
        raise TTSError("pyttsx3 kurulu değil. Kurulum: pip install pyttsx3")
    import pyttsx3

    engine = pyttsx3.init()
    try:
        voices = engine.getProperty("voices") or []
        return [(v.id, v.name) for v in voices]
    finally:
        try:
            engine.stop()
        except Exception:
            pass


def clean_for_tts(text: str) -> str:
    cleaned = _TAG_RE.sub(" ", text)
    cleaned = " ".join(cleaned.split())
    return cleaned


def _new_engine(voice: str | None, rate: int | None):
    import pyttsx3

    engine = pyttsx3.init()
    if voice:
        engine.setProperty("voice", voice)
    if rate:
        engine.setProperty("rate", rate)
    return engine


ENGINE_IDS = ("piper", "sapi", "kokoro")

_PIPER_CACHE: dict[str, object] = {}
_KOKORO_CACHE: dict[str, object] = {}

_KOKORO_LANG_BY_PREFIX = {
    "af": "en-us", "am": "en-us", "bf": "en-gb", "bm": "en-gb",
    "ef": "es", "em": "es", "ff": "fr-fr", "fm": "fr-fr",
    "hf": "hi", "hm": "hi", "if": "it", "im": "it",
    "jf": "ja", "jm": "ja", "pf": "pt-br", "pm": "pt-br",
    "zf": "cmn", "zm": "cmn",
}


def piper_available() -> bool:
    try:
        import piper  # noqa: F401
    except Exception:
        return False
    return True


def kokoro_lib_available() -> bool:
    try:
        import kokoro_onnx  # noqa: F401
    except Exception:
        return False
    return True


def default_engine() -> str:
    if piper_available():
        return "piper"
    if available():
        return "sapi"
    return "sapi"


def _prepare_paths(cues: list[Cue], out_dir: str, prefix: str) -> tuple[list[str], list[tuple[int, str, str]]]:
    os.makedirs(out_dir, exist_ok=True)
    paths: list[str] = []
    pending: list[tuple[int, str, str]] = []
    for i, cue in enumerate(cues):
        path = os.path.join(out_dir, f"{prefix}_{i:05d}.wav")
        paths.append(path)
        if os.path.exists(path):
            os.remove(path)
        text = clean_for_tts(cue.text)
        if not text:
            open(path, "wb").close()
        else:
            pending.append((i, path, text))
    return paths, pending


def _sapi_run(
    pending: list[tuple[int, str, str]],
    total: int,
    voice: str | None,
    rate: int | None,
    progress: Progress | None,
) -> None:
    rounds = 3
    for attempt in range(rounds):
        if not pending:
            break
        engine_obj = _new_engine(voice, rate)
        try:
            for _i, path, text in pending:
                engine_obj.save_to_file(text, path)
            engine_obj.runAndWait()
        except Exception:
            try:
                engine_obj.stop()
            except Exception:
                pass
        finally:
            try:
                engine_obj.stop()
            except Exception:
                pass
        pending = [
            (i, path, text)
            for i, path, text in pending
            if not (os.path.exists(path) and os.path.getsize(path) > 0)
        ]
        if progress:
            done = total - len(pending)
            progress(done, total, f"{done}/{total}")
        if pending and attempt < rounds - 1:
            time.sleep(0.3)


def _resolve_piper_voice(voice: str | None, log: Callable[[str], None] | None = None) -> str:
    from .voices import TR_VOICE_KEY, download_piper_voice, installed_piper_voices

    key = voice or TR_VOICE_KEY
    if key.endswith(".onnx"):
        return key
    installed = installed_piper_voices()
    if key in installed:
        return installed[key]
    if log:
        log(f"[tts] Piper sesi indiriliyor: {key}")
    return download_piper_voice(key)


def _piper_run(
    pending: list[tuple[int, str, str]],
    total: int,
    voice: str | None,
    rate: int | None,
    progress: Progress | None,
    log: Callable[[str], None] | None = None,
) -> None:
    if not piper_available():
        raise TTSError("piper-tts kurulu değil. Kurulum: pip install piper-tts")
    from piper import PiperVoice
    from piper.config import SynthesisConfig

    model_path = _resolve_piper_voice(voice, log)
    cache_key = os.path.abspath(model_path)
    if cache_key not in _PIPER_CACHE:
        _PIPER_CACHE[cache_key] = PiperVoice.load(model_path)
    voice_obj = _PIPER_CACHE[cache_key]
    syn_config = None
    if rate:
        syn_config = SynthesisConfig(length_scale=max(0.5, min(2.0, 170.0 / max(1, rate))))
    failed: list[str] = []
    for n, (_i, path, text) in enumerate(pending, start=1):
        try:
            with wave.open(path, "wb") as wf:
                voice_obj.synthesize_wav(text, wf, syn_config=syn_config)
        except Exception:
            failed.append(os.path.basename(path))
        if progress:
            progress(n, total, f"{n}/{total}")
    if failed:
        raise TTSError(f"Piper sentezi başarısız: {', '.join(failed[:5])}")


class _FloatSpeedSession:
    """ONNX Runtime oturumu sarmalayıcısı.

    Bazı kokoro-onnx sürümleri `speed` girişini int32 gönderiyor; model ise
    float32 bekliyor. Sarmalayıcı bu değeri konuşmacı modelinden bağımsız olarak
    doğru tipe çevirir.
    """

    def __init__(self, session) -> None:
        self._session = session

    def __getattr__(self, name):
        return getattr(self._session, name)

    def run(self, output_names, input_feed, *args, **kwargs):
        import numpy as np

        feed = dict(input_feed)
        if "speed" in feed:
            feed["speed"] = np.asarray(feed["speed"], dtype=np.float32)
        if "input_ids" in feed:
            feed["input_ids"] = np.asarray(feed["input_ids"], dtype=np.int64)
        return self._session.run(output_names, feed, *args, **kwargs)


def _kokoro_run(
    pending: list[tuple[int, str, str]],
    total: int,
    voice: str | None,
    rate: int | None,
    progress: Progress | None,
    log: Callable[[str], None] | None = None,
) -> None:
    if not kokoro_lib_available():
        raise TTSError(
            "kokoro-onnx kurulu değil (Türkçe desteklenmiyor). Kurulum: pip install kokoro-onnx"
        )
    from .voices import download_kokoro_models, kokoro_dir, kokoro_installed

    _lib, ready = kokoro_installed()
    if not ready:
        if log:
            log("[tts] Kokoro modelleri indiriliyor (~134 MB)...")
        download_kokoro_models(
            (lambda name, n, t, _l=log: _l(f"[tts] {name}: {n // (1 << 20)}/{max(1, t // (1 << 20))} MB"))
        )
    folder = kokoro_dir()
    model_path = os.path.join(folder, "kokoro-v1.0.int8.onnx")
    voices_path = os.path.join(folder, "voices-v1.0.bin")
    if "main" not in _KOKORO_CACHE:
        from kokoro_onnx import Kokoro

        koko = Kokoro(model_path, voices_path)
        koko.sess = _FloatSpeedSession(koko.sess)
        _KOKORO_CACHE["main"] = koko
    koko = _KOKORO_CACHE["main"]
    voice_name = voice or "af_heart"
    lang = _KOKORO_LANG_BY_PREFIX.get(voice_name[:2], "en-us")
    speed = max(0.5, min(2.0, (rate / 170.0) if rate else 1.0))
    failed: list[str] = []
    for n, (_i, path, text) in enumerate(pending, start=1):
        try:
            samples, sample_rate = koko.create(text, voice=voice_name, speed=speed, lang=lang)
            import numpy as np

            pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2").tobytes()
            with wave.open(path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                wf.writeframes(pcm)
        except Exception:
            failed.append(os.path.basename(path))
        if progress:
            progress(n, total, f"{n}/{total}")
    if failed:
        raise TTSError(f"Kokoro sentezi başarısız: {', '.join(failed[:5])}")


def synthesize_cues(
    cues: list[Cue],
    out_dir: str,
    voice: str | None = None,
    rate: int | None = None,
    progress: Progress | None = None,
    prefix: str = "cue",
    engine: str | None = None,
    log: Callable[[str], None] | None = None,
) -> list[str]:
    engine = engine or default_engine()
    if engine not in ENGINE_IDS:
        raise TTSError(f"Bilinmeyen TTS motoru: {engine}")
    if engine == "sapi" and not available():
        raise TTSError("pyttsx3 kurulu değil. Kurulum: pip install pyttsx3")
    paths, pending = _prepare_paths(cues, out_dir, prefix)
    if engine == "sapi":
        _sapi_run(pending, len(cues), voice, rate, progress)
    elif engine == "piper":
        _piper_run(pending, len(cues), voice, rate, progress, log)
    elif engine == "kokoro":
        _kokoro_run(pending, len(cues), voice, rate, progress, log)

    still_missing = [
        path for _i, path, _t in pending if not (os.path.exists(path) and os.path.getsize(path) > 0)
    ]
    if still_missing:
        names = ", ".join(os.path.basename(path) for path in still_missing[:5])
        raise TTSError(f"Konuşma sentezi başarısız oldu: {names}")
    if progress:
        progress(len(cues), len(cues), f"{len(cues)}/{len(cues)}")
    return paths


def preview_sample(
    out_path: str,
    engine: str | None = None,
    voice: str | None = None,
    rate: int | None = None,
    text: str = "Merhaba, bu yerel seslendirme önizlemesidir. Hello, this is a local voice preview.",
    log: Callable[[str], None] | None = None,
) -> str:
    cue = Cue(index=1, start=0, end=10_000, text=text)
    out_dir = os.path.dirname(os.path.abspath(out_path))
    parts = synthesize_cues(
        [cue], out_dir, voice=voice, rate=rate, prefix="preview", engine=engine, log=log
    )
    if os.path.abspath(parts[0]) != os.path.abspath(out_path):
        shutil.move(parts[0], out_path)
    return out_path


def _read_wav(path: str) -> tuple[tuple[int, int, int, int], bytes]:
    if os.path.getsize(path) == 0:
        return (1, 2, 22050, 0), b""
    with wave.open(path, "rb") as wf:
        params = wf.getparams()
        frames = wf.readframes(params.nframes)
    return (params.nchannels, params.sampwidth, params.framerate, params.nframes), frames


def _to_pcm16(frames: bytes, channels: int, sampwidth: int, rate: int, target_rate: int) -> bytes:
    if not frames:
        return b""
    samples: list[int] = []
    frame_size = channels * sampwidth
    count = len(frames) // frame_size
    for i in range(count):
        base = i * frame_size
        if sampwidth == 1:
            value = (frames[base] - 128) << 8
        elif sampwidth == 2:
            value = struct.unpack_from("<h", frames, base)[0]
        elif sampwidth == 3:
            raw = frames[base : base + 3]
            value = int.from_bytes(raw, "little", signed=True) >> 8
        elif sampwidth == 4:
            value = struct.unpack_from("<i", frames, base)[0] >> 16
        else:
            raise TTSError(f"Desteklenmeyen örnek genişliği: {sampwidth}")
        if channels > 1:
            total = 0
            for ch in range(channels):
                ch_base = base + ch * sampwidth
                if sampwidth == 1:
                    total += (frames[ch_base] - 128) << 8
                elif sampwidth == 2:
                    total += struct.unpack_from("<h", frames, ch_base)[0]
                elif sampwidth == 3:
                    raw = frames[ch_base : ch_base + 3]
                    total += int.from_bytes(raw, "little", signed=True) >> 8
                else:
                    total += struct.unpack_from("<i", frames, ch_base)[0] >> 16
            value = total // channels
        samples.append(max(-32768, min(32767, value)))
    if target_rate != rate and samples:
        samples = _resample(samples, rate, target_rate)
    return struct.pack(f"<{len(samples)}h", *samples) if samples else b""


def _resample(samples: list[int], src_rate: int, dst_rate: int) -> list[int]:
    if src_rate == dst_rate or not samples:
        return samples
    out_len = max(1, int(len(samples) * dst_rate / src_rate))
    out: list[int] = []
    ratio = (len(samples) - 1) / max(1, out_len - 1)
    for i in range(out_len):
        pos = i * ratio
        left = int(pos)
        right = min(left + 1, len(samples) - 1)
        frac = pos - left
        value = samples[left] * (1 - frac) + samples[right] * frac
        out.append(int(max(-32768, min(32767, value))))
    return out


def build_track(
    cues: list[Cue],
    parts: list[str],
    out_path: str,
    padding_ms: int = 250,
    progress: Progress | None = None,
) -> str:
    if len(cues) != len(parts):
        raise TTSError("Altyazı ve ses dosyası sayısı eşleşmiyor.")
    target_rate = 22050
    for path in parts:
        if os.path.exists(path) and os.path.getsize(path) > 0:
            params, _frames = _read_wav(path)
            target_rate = params[2]
            break
    end_ms = max((cue.end for cue in cues), default=0) + padding_ms
    total_samples = int(end_ms * target_rate / 1000)
    track = bytearray(total_samples * 2)

    for i, (cue, path) in enumerate(zip(cues, parts, strict=True)):
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            if progress:
                progress(i + 1, len(cues), f"{i + 1}/{len(cues)}")
            continue
        (channels, sampwidth, rate, _), frames = _read_wav(path)
        pcm = _to_pcm16(frames, channels, sampwidth, rate, target_rate)
        start_sample = int(cue.start * target_rate / 1000)
        limit_ms = cues[i + 1].start if i + 1 < len(cues) else end_ms
        max_bytes = max(0, int((limit_ms - cue.start) * target_rate / 1000) * 2)
        pcm = pcm[:max_bytes] if max_bytes >= 0 else b""
        offset = start_sample * 2
        available = len(track) - offset
        chunk = pcm[:available]
        track[offset : offset + len(chunk)] = chunk
        if progress:
            progress(i + 1, len(cues), f"{i + 1}/{len(cues)}")

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with wave.open(out_path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(target_rate)
        wf.writeframes(bytes(track))
    return out_path


def cleanup_parts(parts: list[str]) -> None:
    for path in parts:
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            pass


def find_ffmpeg() -> str | None:
    path = shutil.which("ffmpeg")
    if path:
        return path
    for candidate in ("ffmpeg.exe",):
        found = shutil.which(candidate)
        if found:
            return found
    return None


def mux(video_path: str, audio_path: str, out_path: str) -> str:
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        raise TTSError("ffmpeg bulunamadı; videoya ses gömülemiyor.")
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        video_path,
        "-i",
        audio_path,
        "-map",
        "0:v",
        "-map",
        "1:a",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-shortest",
        out_path,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise TTSError(f"ffmpeg hatası: {(proc.stderr or '')[-400:]}")
    return out_path
