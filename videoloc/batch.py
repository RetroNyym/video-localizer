from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

from . import translate as translate_mod
from . import tts as tts_mod
from .langs import AUTO_CODE
from .srt import Cue, read_file, write_file

LogFn = Callable[[str], None]
ProgressFn = Callable[[float, str], None]

AUDIO_EXTS = {
    ".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv", ".wmv", ".m4v",
    ".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac",
}
SUB_EXTS = {".srt", ".vtt"}


class BatchError(RuntimeError):
    pass


class CancelledError(RuntimeError):
    pass


@dataclass
class Job:
    input_path: str
    output_dir: str
    target_lang: str = "tr"
    source_lang: str = AUTO_CODE
    translate: bool = True
    transcribe: bool = True
    tts: bool = False
    tts_engine: str | None = None
    embed: bool = False
    model: str = "small"
    device: str = "auto"
    voice: str | None = None
    rate: int | None = None
    force_transcribe: bool = False
    keep_parts: bool = False


@dataclass
class JobResult:
    job: Job
    ok: bool
    message: str
    srt_path: str | None = None
    track_path: str | None = None
    video_path: str | None = None
    cues: int = 0
    elapsed: float = 0.0


@dataclass
class Context:
    log: LogFn = print
    progress: ProgressFn = lambda *_: None
    cancel: threading.Event = field(default_factory=threading.Event)
    backend: translate_mod.Backend | None = None
    model: object | None = None
    model_size: str | None = None
    cache: dict[str, str] | None = None
    cache_path: str | None = None
    stt_lock: threading.RLock = field(default_factory=threading.RLock)
    log_lock: threading.Lock = field(default_factory=threading.Lock)

    def check_cancel(self) -> None:
        if self.cancel.is_set():
            raise CancelledError("İşlem iptal edildi.")

    def get_backend(self, src: str = AUTO_CODE, tgt: str = AUTO_CODE) -> translate_mod.Backend:
        if self.backend is None:
            self.backend = translate_mod.get_backend("auto", src, tgt)
        return self.backend

    def get_model(self, size: str):
        from .transcribe import load_model

        with self.stt_lock:
            if self.model is None or self.model_size != size:
                self.model = load_model(size, device="auto")
                self.model_size = size
            return self.model

    def load_cache(self) -> dict[str, str]:
        if self.cache is None:
            self.cache = {}
            if self.cache_path and os.path.exists(self.cache_path):
                try:
                    with open(self.cache_path, encoding="utf-8") as fh:
                        data = json.load(fh)
                    if isinstance(data, dict):
                        self.cache = {str(k): str(v) for k, v in data.items()}
                except Exception:
                    self.cache = {}
        return self.cache

    def save_cache(self) -> None:
        if not self.cache_path or self.cache is None:
            return
        try:
            os.makedirs(os.path.dirname(self.cache_path), exist_ok=True)
            tmp = f"{self.cache_path}.tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self.cache, fh, ensure_ascii=False)
            os.replace(tmp, self.cache_path)
        except OSError:
            pass


def default_cache_path() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "VideoLocalizer", "translate_cache.json")


def _stage(ctx: Context, value: float, text: str) -> None:
    ctx.check_cancel()
    ctx.progress(value, text)


def _load_cues(job: Job, ctx: Context) -> tuple[list[Cue], str]:
    ext = os.path.splitext(job.input_path)[1].lower()
    if ext in SUB_EXTS:
        return read_file(job.input_path), "altyazı dosyası okundu"
    sidecar = os.path.splitext(job.input_path)[0] + ".srt"
    if os.path.exists(sidecar) and not job.force_transcribe:
        return read_file(sidecar), f"yan altyazı bulundu: {os.path.basename(sidecar)}"
    if not job.transcribe:
        raise BatchError(
            f"{os.path.basename(job.input_path)} için altyazı bulunamadı; "
            "metne çevirme seçeneğini etkinleştirin."
        )
    from .transcribe import transcribe

    ctx.log(f"[stt] {os.path.basename(job.input_path)} -> model: {job.model}")

    def stt_progress(percent: float, text: str) -> None:
        _stage(ctx, 0.05 + percent * 0.45, f"ses metne çevriliyor: {text}")

    with ctx.stt_lock:
        cues = transcribe(
            job.input_path,
            model_size=job.model,
            language=None if job.source_lang == AUTO_CODE else job.source_lang,
            device=job.device,
            model=ctx.get_model(job.model),
            progress=stt_progress,
        )
    return cues, f"transkripsiyon tamam ({len(cues)} altyazı)"


def _output_stem(job: Job) -> str:
    return os.path.splitext(os.path.basename(job.input_path))[0]


def run_job(job: Job, ctx: Context) -> JobResult:
    started = time.time()
    out_dir = job.output_dir or os.path.dirname(os.path.abspath(job.input_path))
    os.makedirs(out_dir, exist_ok=True)
    stem = _output_stem(job)
    ext = os.path.splitext(job.input_path)[1].lower()
    result = JobResult(job=job, ok=False, message="")
    try:
        _stage(ctx, 0.02, f"başlıyor: {os.path.basename(job.input_path)}")
        cues, note = _load_cues(job, ctx)
        ctx.log(f"[i/o] {note}")
        result.cues = len(cues)
        if not cues:
            raise BatchError("Altyazı bulunamadı.")
        ctx.check_cancel()

        translated = False
        if job.translate and job.target_lang and job.target_lang != AUTO_CODE:
            _stage(ctx, 0.55, "altyazılar çevriliyor")
            backend = ctx.get_backend(job.source_lang, job.target_lang)

            def tr_progress(done: int, total: int, label: str) -> None:
                _stage(ctx, 0.55 + 0.35 * (done / max(1, total)), f"çevriliyor ({label}): {done}/{total}")

            cues = translate_mod.translate_cues(
                cues,
                job.source_lang,
                job.target_lang,
                backend=backend,
                progress=tr_progress,
                cache=ctx.load_cache(),
            )
            ctx.save_cache()
            translated = True
            ctx.log(f"[tr] {len(cues)} altyazı çevrildi ({job.source_lang} -> {job.target_lang})")
        elif job.translate and job.target_lang == AUTO_CODE:
            ctx.log("[tr] hedef dil seçilmedi, çeviri atlandı")

        suffix = f".{job.target_lang}" if translated else ""
        srt_path = os.path.join(out_dir, f"{stem}{suffix}.srt")
        write_file(srt_path, cues)
        result.srt_path = srt_path
        ctx.log(f"[i/o] yazıldı: {srt_path}")
        ctx.check_cancel()

        if job.tts:
            _stage(ctx, 0.9, "seslendirme üretiliyor")
            parts_dir = tempfile.mkdtemp(prefix="videoloc_")
            try:
                def tts_progress(done: int, total: int, label: str) -> None:
                    _stage(ctx, 0.9 + 0.06 * (done / max(1, total)), f"seslendirme: {label}")

                parts = tts_mod.synthesize_cues(
                    cues,
                    parts_dir,
                    voice=job.voice,
                    rate=job.rate,
                    progress=tts_progress,
                    engine=job.tts_engine,
                    log=ctx.log,
                )
                track_path = os.path.join(out_dir, f"{stem}{suffix}.wav")
                tts_mod.build_track(cues, parts, track_path, progress=tts_progress)
                result.track_path = track_path
                ctx.log(f"[tts] seslendirme: {track_path}")
                if job.embed and ext not in SUB_EXTS:
                    if tts_mod.find_ffmpeg():
                        video_out = os.path.join(out_dir, f"{stem}{suffix}_yerellestirilmis.mp4")
                        tts_mod.mux(job.input_path, track_path, video_out)
                        result.video_path = video_out
                        ctx.log(f"[mux] video: {video_out}")
                    else:
                        ctx.log("[mux] ffmpeg bulunamadı, video gömme atlandı")
                if not job.keep_parts:
                    tts_mod.cleanup_parts(parts)
            finally:
                shutil.rmtree(parts_dir, ignore_errors=True)

        _stage(ctx, 1.0, "tamamlandı")
        result.ok = True
        result.message = f"tamam ({len(cues)} altyazı)"
    except CancelledError:
        result.message = "iptal edildi"
        ctx.log("[!] iptal edildi")
    except translate_mod.TranslationError as exc:
        result.message = str(exc)
        ctx.log(f"[hata] {exc}")
    except BatchError as exc:
        result.message = str(exc)
        ctx.log(f"[hata] {exc}")
    except Exception as exc:
        result.message = f"{type(exc).__name__}: {exc}"
        ctx.log(f"[hata] {result.message}")
    result.elapsed = time.time() - started
    return result


def run_jobs(
    jobs: list[Job],
    ctx: Context,
    workers: int = 1,
    on_result: Callable[[JobResult], None] | None = None,
) -> list[JobResult]:
    results: list[JobResult] = []
    if workers <= 1 or len(jobs) <= 1:
        for i, job in enumerate(jobs):
            ctx.check_cancel()
            ctx.progress(i / max(1, len(jobs)), f"dosya {i + 1}/{len(jobs)}")
            res = run_job(job, ctx)
            results.append(res)
            if on_result:
                on_result(res)
            if ctx.cancel.is_set():
                break
        return results

    lock = threading.Lock()

    def worker(job: Job) -> JobResult:
        def log(msg: str) -> None:
            with ctx.log_lock:
                ctx.log(msg)

        local_ctx = Context(
            log=log,
            progress=lambda v, t: None,
            cancel=ctx.cancel,
            cache=ctx.cache,
            cache_path=ctx.cache_path,
            stt_lock=ctx.stt_lock,
            log_lock=ctx.log_lock,
        )
        local_ctx.backend = ctx.backend
        local_ctx.model = ctx.model
        local_ctx.model_size = ctx.model_size
        res = run_job(job, local_ctx)
        with lock:
            ctx.model = local_ctx.model
            ctx.model_size = local_ctx.model_size
            if ctx.cache is None:
                ctx.cache = local_ctx.cache
        return res

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(worker, job): job for job in jobs}
        for i, future in enumerate(as_completed(futures)):
            res = future.result()
            results.append(res)
            if on_result:
                on_result(res)
            ctx.progress((i + 1) / max(1, len(jobs)), f"dosya {i + 1}/{len(jobs)}")
    return results


def expand_inputs(paths: list[str]) -> list[str]:
    out: list[str] = []
    for path in paths:
        if os.path.isdir(path):
            for name in sorted(os.listdir(path)):
                full = os.path.join(path, name)
                if os.path.isfile(full) and os.path.splitext(name)[1].lower() in (AUDIO_EXTS | SUB_EXTS):
                    out.append(full)
        elif os.path.exists(path):
            out.append(path)
    return out
