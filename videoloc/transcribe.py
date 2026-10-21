from __future__ import annotations

import os
from collections.abc import Callable

from .srt import Cue, split_cue

Progress = Callable[[float, str], None]

MODEL_SIZES = ["tiny", "base", "small", "medium", "large-v3"]
DEFAULT_MAX_CHARS = 42
DEFAULT_MAX_LINES = 2


class TranscriptionError(RuntimeError):
    pass


def media_duration(path: str) -> float | None:
    try:
        import av

        with av.open(path) as container:
            if container.duration:
                return container.duration / 1_000_000.0
    except Exception:
        return None
    return None


def _patch_av_metadata_kwarg() -> None:
    try:
        import av
    except Exception:
        return
    if getattr(av, "_videoloc_patched", False):
        return
    original = av.open

    def open_compat(*args, **kwargs):
        try:
            return original(*args, **kwargs)
        except TypeError as exc:
            if "metadata_errors" in str(exc) and "metadata_errors" in kwargs:
                kwargs.pop("metadata_errors", None)
                return original(*args, **kwargs)
            raise

    av.open = open_compat
    av._videoloc_patched = True


def load_model(model_size: str = "small", device: str = "auto", compute_type: str | None = None):
    _patch_av_metadata_kwarg()
    try:
        from faster_whisper import WhisperModel
    except Exception as exc:
        raise TranscriptionError(
            "faster-whisper kurulu değil. Kurulum: pip install faster-whisper"
        ) from exc
    if model_size not in MODEL_SIZES:
        raise TranscriptionError(f"Bilinmeyen model boyutu: {model_size}")
    if compute_type is None:
        compute_type = "int8" if device in ("auto", "cpu") else "float16"
    try:
        return WhisperModel(model_size, device=device, compute_type=compute_type)
    except Exception as exc:
        raise TranscriptionError(f"Model yüklenemedi: {exc}") from exc


def transcribe(
    media_path: str,
    model_size: str = "small",
    language: str | None = None,
    device: str = "auto",
    model=None,
    progress: Progress | None = None,
    max_chars: int = DEFAULT_MAX_CHARS,
    max_lines: int = DEFAULT_MAX_LINES,
) -> list[Cue]:
    if not os.path.exists(media_path):
        raise TranscriptionError(f"Dosya bulunamadı: {media_path}")
    if model is None:
        model = load_model(model_size, device=device)
    duration = media_duration(media_path)
    if progress:
        progress(0.0, "ses çözülüyor")
    try:
        segments, info = model.transcribe(
            media_path,
            language=None if not language or language == "auto" else language,
            beam_size=5,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 400},
        )
    except Exception as exc:
        raise TranscriptionError(f"Transkripsiyon başlatılamadı: {exc}") from exc

    cues: list[Cue] = []
    last_percent = -1
    for segment in segments:
        text = " ".join(segment.text.split())
        if not text:
            continue
        start = int(max(0.0, segment.start) * 1000)
        end = int(max(start + 1, segment.end) * 1000)
        base = Cue(index=len(cues) + 1, start=start, end=end, text=text)
        for cue in split_cue(base, max_chars, max_lines):
            cue.index = len(cues) + 1
            cues.append(cue)
        if progress:
            if duration:
                percent = min(1.0, segment.end / duration)
                if int(percent * 100) != last_percent:
                    last_percent = int(percent * 100)
                    progress(percent, f"%{last_percent} - {text[:40]}")
            else:
                progress(min(0.99, len(cues) / 50.0), f"{len(cues)} bölüm - {text[:40]}")
    if progress:
        progress(1.0, f"tamamlandı ({len(cues)} altyazı)")
    if getattr(info, "language", None) and language in (None, "auto"):
        _ = info.language
    return cues


def transcribe_to_file(
    media_path: str,
    output_path: str,
    model_size: str = "small",
    language: str | None = None,
    device: str = "auto",
    progress: Progress | None = None,
) -> list[Cue]:
    from .srt import write_file

    cues = transcribe(
        media_path,
        model_size=model_size,
        language=language,
        device=device,
        progress=progress,
    )
    write_file(output_path, cues)
    return cues


def estimate_download_size(model_size: str) -> str:
    return {
        "tiny": "~75 MB",
        "base": "~145 MB",
        "small": "~484 MB",
        "medium": "~1.5 GB",
        "large-v3": "~3.1 GB",
    }.get(model_size, "bilinmiyor")
