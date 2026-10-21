from __future__ import annotations

import argparse
import sys

from .batch import Context, Job, default_cache_path, expand_inputs, run_jobs
from .langs import AUTO_CODE, CODE_TO_NAME, LANGUAGES
from .transcribe import MODEL_SIZES


def _lang_code(value: str) -> str:
    value = value.strip()
    if value.lower() in ("auto", "otomatik"):
        return AUTO_CODE
    if value in LANGUAGES.values() or value in CODE_TO_NAME:
        return value
    for name, code in LANGUAGES.items():
        if name.lower() == value.lower():
            return code
    raise SystemExit(f"Bilinmeyen dil: {value} (örnek: tr, en, 'Almanca')")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="video-localizer",
        description="Video Localizer - video/altyazı yerelleştirme aracı (GUI için argümansız çalıştırın)",
    )
    parser.add_argument("inputs", nargs="*", help="video, ses veya srt dosyaları / klasörleri")
    parser.add_argument("--target", default="tr", help="hedef dil kodu (varsayılan: tr)")
    parser.add_argument("--source", default="auto", help="kaynak dil kodu veya auto")
    parser.add_argument("--out", default="", help="çıktı klasörü (boş = dosyanın yanında)")
    parser.add_argument("--model", default="small", choices=MODEL_SIZES, help="whisper model boyutu")
    parser.add_argument("--workers", type=int, default=1, help="eşzamanlı iş sayısı")
    parser.add_argument("--no-translate", action="store_true", help="çeviriyi atla")
    parser.add_argument("--no-transcribe", action="store_true", help="STT'yi atla (yan srt kullanılır)")
    parser.add_argument("--tts", action="store_true", help="seslendirme üret")
    parser.add_argument(
        "--tts-engine",
        default=None,
        choices=["piper", "sapi", "kokoro"],
        help="seslendirme motoru (varsayılan: piper, yoksa sapi)",
    )
    parser.add_argument("--list-voices", action="store_true", help="ses kütüphanesini listele ve çık")
    parser.add_argument("--embed", action="store_true", help="seslendirme videoya göm (ffmpeg gerekir)")
    parser.add_argument("--voice", default=None, help="TTS ses kimliği")
    parser.add_argument("--rate", type=int, default=None, help="TTS konuşma hızı (wpm)")
    parser.add_argument("--ignore-sidecar", action="store_true", help="yanındaki .srt dosyasını yok say")
    return parser


def _print_voices() -> int:
    from . import tts as tts_mod
    from . import voices as voices_mod

    print(f"Varsayılan motor: {tts_mod.default_engine()}")
    installed = voices_mod.installed_piper_voices()
    print(f"\nPiper: {len(voices_mod.piper_catalog())} ses katalogda, {len(installed)} kurulu")
    for key in installed:
        mark = "  * (TR, CC BY-NC-SA 4.0 — ticari değil)" if key == voices_mod.TR_VOICE_KEY else ""
        print(f"  - {key}{mark}")
    try:
        sapi = voices_mod.sapi_catalog()
        print(f"\nWindows SAPI: {len(sapi)} sistem sesi")
        for info in sapi[:6]:
            print(f"  - {info.name}")
    except Exception as exc:
        print(f"\nWindows SAPI: kullanılamıyor ({exc})")
    lib_ok, ready = voices_mod.kokoro_installed()
    info = voices_mod.KOKORO_INFO
    print(
        f"\nKokoro: {'kurulu' if lib_ok else 'pip install kokoro-onnx gerekli'} | "
        f"modeller {'hazır' if ready else 'indirilmedi'} | lisans {info['license']} | "
        f"{'Türkçe desteklenmiyor' if not info['turkish_supported'] else ''}"
    )
    print("  diller: " + ", ".join(info["languages"]))
    print(f"  kaynak: {info['source']}")
    cv = voices_mod.COMMONVOICE_INFO
    print(
        f"\nCommon Voice (Türkçe): {cv['target_sentence_count']} hedef cümle | {cv['page']}\n"
        f"  {cv['note']}"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.list_voices:
        return _print_voices()
    if not args.inputs:
        print("Girdi dosyası verilmedi.", file=sys.stderr)
        return 2
    files = expand_inputs(args.inputs)
    if not files:
        print("İşlenecek dosya bulunamadı.", file=sys.stderr)
        return 2

    target = _lang_code(args.target) if not args.no_translate else AUTO_CODE
    source = _lang_code(args.source)

    jobs = [
        Job(
            input_path=path,
            output_dir=args.out,
            target_lang=target,
            source_lang=source,
            translate=not args.no_translate,
            transcribe=not args.no_transcribe,
            tts=args.tts,
            tts_engine=args.tts_engine,
            embed=args.embed,
            model=args.model,
            voice=args.voice,
            rate=args.rate,
            force_transcribe=args.ignore_sidecar,
        )
        for path in files
    ]

    ctx = Context(
        log=lambda msg: print(msg, flush=True),
        progress=lambda value, text: print(f"[{value * 100:5.1f}%] {text}", flush=True),
        cache_path=default_cache_path(),
    )
    results = run_jobs(jobs, ctx, workers=max(1, args.workers))
    ok = sum(1 for r in results if r.ok)
    for res in results:
        mark = "OK " if res.ok else "HATA"
        print(f"{mark} {res.job.input_path} -> {res.message}")
    print(f"Toplam: {ok}/{len(results)} başarılı")
    return 0 if ok == len(results) else 1
