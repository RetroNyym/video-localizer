"""Ekran görüntüleri üretir: screenshots/01-main.png, 02-voices.png, 03-english.png"""

import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding="utf-8")

from PIL import ImageGrab  # noqa: E402

SHOTS = os.path.join(ROOT, "screenshots")


def demo_dir() -> str:
    d = os.path.join(tempfile.gettempdir(), "videoloc_shots")
    os.makedirs(d, exist_ok=True)
    for name, size in (("video1.mp4", 8 << 20), ("video2.mkv", 5 << 20)):
        path = os.path.join(d, name)
        if not os.path.exists(path) or os.path.getsize(path) != size:
            with open(path, "wb") as fh:
                fh.truncate(size)
    src = os.path.join(d, "ornek.srt")
    tr = os.path.join(d, "ornek.tr.srt")
    if not os.path.exists(src):
        with open(src, "w", encoding="utf-8") as fh:
            fh.write(
                "1\n00:00:00,200 --> 00:00:02,500\nHello and welcome to the demo.\n\n"
                "2\n00:00:03,000 --> 00:00:05,400\nToday we localize this video.\n\n"
                "3\n00:00:05,800 --> 00:00:08,600\nEverything runs on your machine.\n"
            )
    if not os.path.exists(tr):
        with open(tr, "w", encoding="utf-8") as fh:
            fh.write(
                "1\n00:00:00,200 --> 00:00:02,500\nMerhaba ve demoya hoş geldiniz.\n\n"
                "2\n00:00:03,000 --> 00:00:05,400\nBugün bu videoyu yerelleştiriyoruz.\n\n"
                "3\n00:00:05,800 --> 00:00:08,600\nHer şey kendi makinenizde çalışır.\n"
            )
    wav = os.path.join(d, "ornek.tr.wav")
    if not os.path.exists(wav):
        from videoloc import srt, tts

        cues = srt.read_file(tr)
        parts = tts.synthesize_cues(cues, d, prefix="ornek.tr")
        tts.build_track(cues, parts, wav, padding_ms=100)
    return d


def _workarea_bottom() -> int:
    import ctypes

    class RECT(ctypes.Structure):
        _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long),
                    ("r", ctypes.c_long), ("b", ctypes.c_long)]

    rc = RECT()
    ctypes.windll.user32.SystemParametersInfoW(48, 0, ctypes.byref(rc), 0)
    return rc.b


def grab(win, path: str) -> None:
    import ctypes

    class RECT(ctypes.Structure):
        _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long),
                    ("r", ctypes.c_long), ("b", ctypes.c_long)]

    win.update()
    win.lift()
    try:
        win.attributes("-topmost", True)
        win.focus_force()
    except Exception:
        pass
    time.sleep(0.6)
    win.update()
    hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
    rect = RECT()
    ctypes.windll.dwmapi.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(rect), ctypes.sizeof(rect))
    bbox = (rect.l, rect.t, rect.r, min(rect.b, _workarea_bottom()))
    ImageGrab.grab(bbox=bbox).save(path)
    try:
        win.attributes("-topmost", False)
    except Exception:
        pass
    print("kayıt:", path, bbox)


def main() -> None:
    import tkinter as tk

    from videoloc import i18n
    from videoloc.gui import App, config_path

    cfg_file = config_path()
    cfg_backup = open(cfg_file, "rb").read() if os.path.exists(cfg_file) else None
    d = demo_dir()
    os.makedirs(SHOTS, exist_ok=True)

    root = tk.Tk()
    app = App(root)

    import ctypes

    class RECT(ctypes.Structure):
        _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long),
                    ("r", ctypes.c_long), ("b", ctypes.c_long)]

    rc = RECT()
    ctypes.windll.user32.SystemParametersInfoW(48, 0, ctypes.byref(rc), 0)
    work_h = rc.b - rc.t
    root.geometry(f"1410x{min(1030, work_h - 8)}+0+0")
    root.update()
    frame_bottom = root.winfo_rooty() + root.winfo_height()
    over = frame_bottom - (work_h - 4)
    if over > 0:
        root.geometry(f"1410x{root.winfo_height() - over}")
        root.update()
    root.update()
    app._add_paths(
        [os.path.join(d, "ornek.srt"), os.path.join(d, "video1.mp4"), os.path.join(d, "video2.mkv")]
    )
    rows = list(app.tree.get_children())
    app.tree.set(rows[0], "lang", "Türkçe (tr)")
    app.tree.set(rows[0], "status", "✓ 3/3 cue hazır")
    for iid in rows[1:]:
        app.tree.set(iid, "lang", "İngilizce (en)")
        app.tree.set(iid, "status", "Bekliyor")
    app.tree.selection_set(rows[0])
    app._show_preview(os.path.join(d, "ornek.tr.srt"))
    app.set_stage(2)
    app.log("[stt] faster-whisper tiny · 0:08 · 3 cue", "ok")
    app.log("[çeviri] en → tr · Google Gtx · önbellek 0", "ok")
    app.log("[seslendirme] piper / tr_TR-dfki-medium · 3/3", "ok")
    app.stats.update(projects=24, minutes=186.0, ready=3, disk_gb=4.8)
    root.update()
    time.sleep(1.2)
    app._update_metrics()
    app.var_status.set(i18n.t("done_batch", app.lang) if "done_batch" in i18n.S[app.lang] else "Hazır")
    grab(root, os.path.join(SHOTS, "01-main.png"))

    dlg = app._open_voices()
    dlg.search_var.set("kokoro")
    dlg._load_tree()
    dlg.update()
    rows = list(dlg.tree.get_children())
    target_row = next((i for i in rows if str(i) == "kokoro:af_heart"), rows[0] if rows else None)
    if target_row is not None:
        dlg.tree.selection_set(target_row)
        dlg.tree.see(target_row)
    dlg._show_detail()
    dlg.geometry("+300+160")
    grab(dlg, os.path.join(SHOTS, "02-voices.png"))
    dlg.destroy()

    app.lang = "en"
    app.apply_language()
    app.var_status.set("Ready")
    grab(root, os.path.join(SHOTS, "03-english.png"))

    root.destroy()
    if cfg_backup is None:
        if os.path.exists(cfg_file):
            os.remove(cfg_file)
    else:
        with open(cfg_file, "wb") as fh:
            fh.write(cfg_backup)
    print("bitti")


if __name__ == "__main__":
    main()
