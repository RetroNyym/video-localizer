from __future__ import annotations

import json
import os
import queue
import threading
import traceback
import winsound
from tkinter import (
    END,
    BooleanVar,
    Canvas,
    StringVar,
    Text,
    Tk,
    W,
    filedialog,
    messagebox,
    ttk,
)

from . import dialogs, i18n
from . import tts as tts_mod
from . import voices as voices_mod
from .batch import (
    SUB_EXTS,
    Context,
    Job,
    JobResult,
    default_cache_path,
    expand_inputs,
    run_jobs,
)
from .i18n import t
from .langs import AUTO_CODE, CODE_TO_NAME
from .srt import read_file

BG = "#0b0c0f"
SIDE = "#0e0f12"
PANEL = "#111318"
PANEL2 = "#15171d"
LINE = "#242730"
MUTED = "#858995"
TEXT = "#f4f5f7"
LIME = "#c5f36a"
LIME_D = "#a6d94d"
DARK_ON_LIME = "#15180f"
NAV = "#a2a5af"
RED = "#ff777e"

LANG_EN = {
    "tr": "Turkish", "en": "English", "ar": "Arabic", "de": "German", "fr": "French",
    "es": "Spanish", "it": "Italian", "pt": "Portuguese", "ru": "Russian", "fa": "Persian",
    "he": "Hebrew", "nl": "Dutch", "pl": "Polish", "uk": "Ukrainian", "cs": "Czech",
    "ro": "Romanian", "hu": "Hungarian", "bg": "Bulgarian", "el": "Greek", "sv": "Swedish",
    "no": "Norwegian", "da": "Danish", "fi": "Finnish", "sr": "Serbian", "hr": "Croatian",
    "id": "Indonesian", "vi": "Vietnamese", "th": "Thai", "ms": "Malay", "ja": "Japanese",
    "ko": "Korean", "zh-CN": "Chinese (Simplified)", "zh-TW": "Chinese (Traditional)",
    "hi": "Hindi", "bn": "Bengali", "fil": "Filipino", "sw": "Swahili",
}


def config_path() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "VideoLocalizer", "config.json")


def load_config() -> dict:
    try:
        with open(config_path(), encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def save_config(cfg: dict) -> None:
    try:
        path = config_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
    except OSError:
        pass


class Toggle(Canvas):
    def __init__(self, master, variable: BooleanVar, bg: str = PANEL, **kwargs) -> None:
        super().__init__(
            master, width=38, height=20, highlightthickness=0, bg=bg,
            cursor="hand2", **kwargs,
        )
        self.var = variable
        self.bg = bg
        self.bind("<Button-1>", lambda _e: self.var.set(not self.var.get()))
        self.var.trace_add("write", lambda *_: self.redraw())
        self.redraw()

    def redraw(self) -> None:
        self.delete("all")
        on = bool(self.var.get())
        color = LIME if on else "#2a2d35"
        self.create_rectangle(10, 1, 28, 19, fill=color, outline="")
        self.create_oval(1, 1, 19, 19, fill=color, outline="")
        self.create_oval(19, 1, 37, 19, fill=color, outline="")
        knob_x = 19 if on else 1
        self.create_oval(knob_x + 1, 3, knob_x + 17, 19, fill="#ffffff" if on else "#8a8f9a", outline="")


def build_styles(root: Tk) -> ttk.Style:
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:
        pass

    def f(name: str, **kw) -> None:
        style.configure(name, **kw)

    f("TFrame", background=BG)
    f("Side.TFrame", background=SIDE)
    f("Card.TFrame", background=PANEL)
    f("Panel2.TFrame", background=PANEL2)
    f("TLabel", background=BG, foreground=TEXT, font=("Segoe UI", 10))
    f("Side.TLabel", background=SIDE, foreground=TEXT, font=("Segoe UI", 10))
    f("Muted.TLabel", background=BG, foreground=MUTED, font=("Segoe UI", 9))
    f("MutedCard.TLabel", background=PANEL, foreground=MUTED, font=("Segoe UI", 9))
    f("Card.TLabel", background=PANEL, foreground=TEXT, font=("Segoe UI", 10))
    f("CardHead.TLabel", background=PANEL, foreground=TEXT, font=("Segoe UI", 11, "bold"))
    f("CardTag.TLabel", background=PANEL, foreground=MUTED, font=("Segoe UI", 8))
    f("Badge.TLabel", background=LIME, foreground=DARK_ON_LIME, font=("Segoe UI", 8, "bold"))
    f("Brand.TLabel", background=SIDE, foreground=TEXT, font=("Manrope", 16, "bold"))
    f("Logo.TLabel", background=LIME, foreground=DARK_ON_LIME, font=("Segoe UI", 14, "bold"))
    f("NavLabel.TLabel", background=SIDE, foreground="#696d78", font=("Segoe UI", 8, "bold"))
    f("Nav.TLabel", background=SIDE, foreground=NAV, font=("Segoe UI", 10))
    f("NavActive.TLabel", background="#1b1e23", foreground=TEXT, font=("Segoe UI", 10))
    f("LocalCard.TLabel", background="#171a1e", foreground=TEXT, font=("Segoe UI", 9, "bold"))
    f("LocalCardP.TLabel", background="#171a1e", foreground="#818591", font=("Segoe UI", 8))
    f("Avatar.TLabel", background="#6a5bd6", foreground="#ffffff", font=("Segoe UI", 9, "bold"))
    f("Crumb.TLabel", background=BG, foreground=MUTED, font=("Segoe UI", 9))
    f("Status.TLabel", background=BG, foreground=LIME_D, font=("Segoe UI", 9))
    f("Eyebrow.TLabel", background=BG, foreground=LIME, font=("Segoe UI", 8, "bold"))
    f("Title.TLabel", background=BG, foreground=TEXT, font=("Segoe UI", 22, "bold"))
    f("Sub.TLabel", background=BG, foreground=MUTED, font=("Segoe UI", 10))
    f("Metric.TLabel", background=PANEL, foreground=MUTED, font=("Segoe UI", 9))
    f("MetricNum.TLabel", background=PANEL, foreground=TEXT, font=("Segoe UI", 20, "bold"))
    f("MetricFoot.TLabel", background=PANEL, foreground=MUTED, font=("Segoe UI", 8))
    f("Green.TLabel", background=PANEL, foreground=LIME_D, font=("Segoe UI", 8, "bold"))
    f("Step.TLabel", background=PANEL, foreground=MUTED, font=("Segoe UI", 9))
    f("StepDone.TLabel", background=PANEL, foreground=LIME_D, font=("Segoe UI", 9))
    f("StepNow.TLabel", background=PANEL, foreground=TEXT, font=("Segoe UI", 9, "bold"))
    f("StepCircle.TLabel", background=PANEL2, foreground=MUTED, font=("Segoe UI", 9, "bold"),
      width=3, anchor="center")
    f("StepCircleDone.TLabel", background=LIME, foreground=DARK_ON_LIME,
      font=("Segoe UI", 9, "bold"), width=3, anchor="center")
    f("StepCircleNow.TLabel", background="#1b1e23", foreground=LIME,
      font=("Segoe UI", 9, "bold"), width=3, anchor="center")
    f("Play.TLabel", background=PANEL, foreground=TEXT, font=("Segoe UI", 13))
    f("TButton", background=PANEL2, foreground=TEXT, borderwidth=0, focusthickness=0,
      padding=(10, 6), font=("Segoe UI", 10))
    style.map("TButton", background=[("active", "#20232b"), ("pressed", "#272b34")])
    f("Primary.TButton", background=LIME, foreground=DARK_ON_LIME, borderwidth=0,
      focusthickness=0, padding=(12, 7), font=("Segoe UI", 10, "bold"))
    style.map("Primary.TButton", background=[("active", LIME_D), ("pressed", "#96c445")])
    f("Mini.TButton", background=PANEL2, foreground=MUTED, borderwidth=0, padding=(8, 4),
      font=("Segoe UI", 9))
    style.map("Mini.TButton", background=[("active", "#20232b")])
    f("TEntry", fieldbackground=PANEL2, foreground=TEXT, insertcolor=TEXT, borderwidth=0,
      padding=6, font=("Segoe UI", 10))
    style.map("TEntry", fieldbackground=[("readonly", PANEL2)])
    f("TCombobox", fieldbackground=PANEL2, foreground=TEXT, background=PANEL2,
      arrowcolor=MUTED, borderwidth=0, padding=5, font=("Segoe UI", 10))
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", PANEL2)],
        foreground=[("readonly", TEXT)],
        background=[("active", "#20232b"), ("readonly", PANEL2)],
        arrowcolor=[("active", TEXT)],
    )
    f("Treeview", background=PANEL, fieldbackground=PANEL, foreground=TEXT, borderwidth=0,
      rowheight=30, font=("Segoe UI", 10))
    style.map("Treeview", background=[("selected", LIME)], foreground=[("selected", DARK_ON_LIME)])
    f("Treeview.Heading", background=PANEL2, foreground=MUTED, borderwidth=0,
      font=("Segoe UI", 9, "bold"))
    style.map("Treeview.Heading", background=[("active", PANEL2)])
    f("TProgressbar", background=LIME, troughcolor=LINE, borderwidth=0, thickness=6)
    f("TCheckbutton", background=BG, foreground=TEXT, focusthing=0, font=("Segoe UI", 10))
    style.map("TCheckbutton", background=[("active", BG)], foreground=[("active", TEXT)])
    f("SideCheck.TCheckbutton", background=SIDE, foreground=TEXT, font=("Segoe UI", 10))
    f("TSeparator", background=LINE)
    f("TScrollbar", background=PANEL2, troughcolor=SIDE, borderwidth=0, arrowsize=12)
    return style


class App:
    def __init__(self, root: Tk) -> None:
        self.root = root
        self.config = load_config()
        self.lang = self.config.get("ui_lang", "tr")
        self.files: list[str] = []
        self.events: queue.Queue = queue.Queue()
        self.worker: threading.Thread | None = None
        self.ctx: Context | None = None
        self.total_jobs = 0
        self.finished_jobs = 0
        self.sapi_voices: list[voices_mod.VoiceInfo] = []
        self._texts: list[tuple[object, str, object]] = []
        self._stage = 0
        self._voice_map: dict[str, str] = {}
        self._piper_map: dict[str, str] = {}
        self._busy = False
        self._last_track: str | None = None

        stats = self.config.get("stats", {})
        self.stats = {
            "projects": int(stats.get("projects", 0)),
            "minutes": float(stats.get("minutes", 0.0)),
            "ready": 0,
            "disk_gb": float(stats.get("disk_gb", 0.0)),
        }

        self.var_translate = BooleanVar(value=bool(self.config.get("translate", True)))
        self.var_tts = BooleanVar(value=bool(self.config.get("tts", False)))
        self.var_status = StringVar(value=t("ready", self.lang))
        self.var_source = StringVar()
        self.var_target = StringVar()
        self.var_engine = StringVar(
            value=self.config.get("tts_engine") or tts_mod.default_engine()
        )
        self.var_voice = StringVar()
        self.var_ui_lang = StringVar(value=i18n.LANGUAGES_UI.get(self.lang, "Türkçe"))

        root.title(t("app_title", self.lang))
        root.geometry(self.config.get("geometry", "1180x800"))
        root.minsize(1020, 700)
        build_styles(root)

        self._build()
        self.apply_language(first=True)
        self._update_metrics()
        self._load_sapi_async()
        self._compute_disk_async()
        self.root.after(120, self._poll)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def W(self, widget, key: str, **fmt) -> object:
        widget.configure(text=t(key, self.lang, **fmt))
        self._texts.append((widget, key, fmt))
        return widget

    def apply_language(self, first: bool = False) -> None:
        lang = self.lang
        for widget, key, fmt in self._texts:
            kwargs = fmt() if callable(fmt) else fmt
            try:
                widget.configure(text=t(key, lang, **kwargs))
            except Exception:
                pass
        self.root.title(t("app_title", lang))
        self._refresh_lang_combos(first=first)
        for col, key in getattr(self, "_headings", []):
            self.tree.heading(col, text=t(key, lang))
        self._refresh_voice_choices()
        self._update_engine_desc()
        if not first:
            self._draw_local_panel()
            self._update_metrics()
            self.set_stage(self._stage)

    def _lg_name(self, code: str) -> str:
        if code == AUTO_CODE:
            return t("auto", self.lang)
        if self.lang == "en":
            return LANG_EN.get(code, code)
        return CODE_TO_NAME.get(code, code)

    def _lang_codes(self) -> list[str]:
        return [AUTO_CODE] + [c for c in CODE_TO_NAME]

    def _refresh_lang_combos(self, first: bool = False) -> None:
        codes = self._lang_codes()
        labels = [self._lg_name(c) for c in codes]
        self._src_codes = codes
        self._tgt_codes = codes[1:]
        if first:
            self._src_code = self.config.get("source", AUTO_CODE) or AUTO_CODE
            self._tgt_code = self.config.get("target", "tr") or "tr"
            if self._src_code not in codes:
                self._src_code = AUTO_CODE
            if self._tgt_code not in self._tgt_codes:
                self._tgt_code = "tr"
        self.var_source.set(self._lg_name(getattr(self, "_src_code", AUTO_CODE)))
        self.var_target.set(self._lg_name(getattr(self, "_tgt_code", "tr")))
        self.cb_source.configure(values=labels)
        self.cb_target.configure(values=labels[1:])
        self.cb_source.bind("<<ComboboxSelected>>", lambda _e: self._resolve_source())
        self.cb_target.bind("<<ComboboxSelected>>", lambda _e: self._resolve_target())

    def _code_for(self, var: StringVar, allow_auto: bool) -> str:
        label = var.get()
        table = self._src_codes if allow_auto else self._tgt_codes
        for code in table:
            if self._lg_name(code) == label:
                return code
        return AUTO_CODE if allow_auto else "tr"

    def _build(self) -> None:
        shell = ttk.Frame(self.root)
        shell.pack(fill="both", expand=True)

        side = ttk.Frame(shell, style="Side.TFrame", width=212)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        self._build_sidebar(side)

        main = ttk.Frame(shell)
        main.pack(side="left", fill="both", expand=True)
        self._build_main(main)

    def _build_sidebar(self, side: ttk.Frame) -> None:
        brand = ttk.Frame(side, style="Side.TFrame")
        brand.pack(fill="x", padx=14, pady=(16, 22))
        ttk.Label(brand, text="◒", style="Logo.TLabel", width=3, anchor="center").pack(
            side="left", padx=(0, 9)
        )
        self.W(ttk.Label(brand, text="", style="Brand.TLabel"), "brand").pack(side="left")

        def nav(text_key: str, icon: str, command=None, active: bool = False) -> None:
            row = ttk.Frame(side, style="Side.TFrame")
            row.pack(fill="x", padx=8, pady=1)
            lbl_style = "NavActive.TLabel" if active else "Nav.TLabel"
            ic = ttk.Label(row, text=icon, style=lbl_style, width=2)
            ic.pack(side="left", padx=(8, 6), pady=7)
            tx = ttk.Label(row, text="", style=lbl_style, cursor="hand2")
            tx.pack(side="left", pady=7)
            self.W(tx, text_key)
            if command:
                for w in (row, ic, tx):
                    w.bind("<Button-1>", lambda _e, c=command: c())

        self.W(ttk.Label(side, text="", style="NavLabel.TLabel"), "nav_workspace").pack(
            fill="x", padx=16, pady=(6, 2)
        )
        nav("nav_overview", "▦", lambda: self._hint("nav_hint_overview"), active=True)
        nav("nav_projects", "◷", lambda: self._hint("nav_hint_projects"))
        nav("nav_queue", "⇄", lambda: self._hint("nav_hint_queue"))

        self.W(ttk.Label(side, text="", style="NavLabel.TLabel"), "nav_library").pack(
            fill="x", padx=16, pady=(14, 2)
        )
        nav("nav_voices", "◉", self._open_voices)
        nav("nav_exports", "▤", self._open_exports)
        ttk.Frame(side, style="Side.TFrame").pack(fill="both", expand=True)
        nav("nav_prefs", "⚙", self._open_prefs)

        panel = Canvas(
            side, height=74, highlightthickness=1, highlightbackground=LINE,
            bg="#171a1e",
        )
        panel.pack(fill="x", padx=12, pady=(2, 8))
        self._local_panel = panel
        self._draw_local_panel()

        prof = ttk.Frame(side, style="Side.TFrame")
        prof.pack(fill="x", padx=12, pady=(2, 14))
        ttk.Label(prof, text="EK", style="Avatar.TLabel", width=3, anchor="center").pack(
            side="left", padx=(0, 8)
        )
        pcol = ttk.Frame(prof, style="Side.TFrame")
        pcol.pack(side="left")
        self.W(ttk.Label(pcol, text="", style="Side.TLabel"), "profile").pack(anchor="w")
        self.W(ttk.Label(pcol, text="", style="Muted.TLabel"), "profile_sub").pack(anchor="w")

    def _draw_local_panel(self) -> None:
        panel = getattr(self, "_local_panel", None)
        if panel is None:
            return
        panel.delete("all")
        panel.create_text(14, 20, anchor="w", text="● " + t("local_card", self.lang),
                          fill=LIME, font=("Segoe UI", 9, "bold"))
        panel.create_text(14, 44, anchor="w", text=t("local_card_p", self.lang),
                          fill="#818591", font=("Segoe UI", 8))

    def _build_main(self, main: ttk.Frame) -> None:
        top = ttk.Frame(main)
        top.pack(fill="x", padx=22, pady=(8, 0))
        crumb = ttk.Label(top, text="", style="Crumb.TLabel")
        crumb.pack(side="left")
        self.W(crumb, "crumb")
        sep = ttk.Label(top, text="  /  ", style="Crumb.TLabel")
        sep.pack(side="left")
        strong = ttk.Label(top, text="", style="Crumb.TLabel", font=("Segoe UI", 9, "bold"))
        strong.pack(side="left")
        self.W(strong, "crumb_overview")
        status = ttk.Label(top, text="", style="Status.TLabel")
        status.pack(side="right")
        self.W(status, "status")

        titlerow = ttk.Frame(main)
        titlerow.pack(fill="x", padx=22, pady=(6, 0))
        left = ttk.Frame(titlerow)
        left.pack(side="left")
        self.W(ttk.Label(left, text="", style="Eyebrow.TLabel"), "eyebrow").pack(anchor="w")
        self.W(ttk.Label(left, text="", style="Title.TLabel"), "title").pack(anchor="w")
        self.W(ttk.Label(left, text="", style="Sub.TLabel", wraplength=620), "subtitle").pack(anchor="w")
        btns = ttk.Frame(titlerow)
        btns.pack(side="right")
        self.btn_new = ttk.Button(btns, text="", command=self.clear_files)
        self.W(self.btn_new, "btn_new_project")
        self.btn_new.pack(side="right")
        self.btn_add = ttk.Button(
            btns, text="", style="Primary.TButton", command=self.add_files
        )
        self.W(self.btn_add, "btn_add_batch")
        self.btn_add.pack(side="right", padx=(0, 8))

        metrics = ttk.Frame(main)
        metrics.pack(fill="x", padx=22, pady=(8, 0))
        self.metric_vars: dict[str, StringVar] = {}
        self._metric_foot: dict[str, ttk.Label] = {}
        defs = [("m_projects", "projects"), ("m_minutes", "minutes"),
                ("m_ready", "ready"), ("m_disk", "disk")]
        for i, (key, ident) in enumerate(defs):
            card = ttk.Frame(metrics, style="Card.TFrame")
            card.pack(side="left", fill="both", expand=True, padx=(0 if i == 0 else 8, 0))
            head = ttk.Frame(card, style="Card.TFrame")
            head.pack(fill="x", padx=12, pady=(8, 0))
            self.W(ttk.Label(head, text="", style="Metric.TLabel"), key).pack(side="left")
            ttk.Label(head, text="↗", style="Metric.TLabel").pack(side="right")
            var = StringVar(value="0")
            self.metric_vars[ident] = var
            ttk.Label(card, text="", style="MetricNum.TLabel", textvariable=var).pack(
                anchor="w", padx=12, pady=(2, 0)
            )
            foot = ttk.Label(card, text="", style="MetricFoot.TLabel")
            foot.pack(anchor="w", padx=12, pady=(2, 6))
            self._metric_foot[ident] = foot

        content = ttk.Frame(main)
        content.pack(fill="both", expand=True, padx=22, pady=(6, 0))

        leftcol = ttk.Frame(content)
        leftcol.pack(side="left", fill="both", expand=True)
        rightcol = ttk.Frame(content, width=300)
        rightcol.pack(side="right", fill="y", padx=(12, 0))
        rightcol.pack_propagate(False)

        self._build_import_card(leftcol)
        self._build_recent_card(leftcol)
        self._build_preview_card(rightcol)
        self._build_voice_card(rightcol)
        self._build_bottom(main)

    def _card(self, parent, title_key: str, tag: str = "") -> ttk.Frame:
        card = ttk.Frame(parent, style="Card.TFrame")
        card.pack(fill="both", expand=True, pady=(0, 8))
        head = ttk.Frame(card, style="Card.TFrame")
        head.pack(fill="x", padx=14, pady=(8, 4))
        self.W(ttk.Label(head, text="", style="CardHead.TLabel"), title_key).pack(side="left")
        if tag:
            lbl = ttk.Label(head, text="", style="CardTag.TLabel")
            lbl.pack(side="right")
            self.W(lbl, tag)
        return card

    def _build_import_card(self, parent) -> None:
        card = self._card(parent, "card_start", "step_import")
        body = ttk.Frame(card, style="Card.TFrame")
        body.pack(fill="both", expand=True, padx=14, pady=(0, 8))

        drop = Canvas(body, height=50, highlightthickness=1, highlightbackground=LINE,
                      bg=PANEL2, cursor="hand2")
        drop.pack(fill="x")
        drop.create_text(120, 25, anchor="center", text="↑", fill=LIME,
                         font=("Segoe UI", 18, "bold"))
        drop_id = drop.create_text(150, 19, anchor="w", text="", fill=TEXT,
                                   font=("Segoe UI", 10, "bold"))
        drop_sub = drop.create_text(150, 34, anchor="w", text="", fill=MUTED,
                                    font=("Segoe UI", 9))
        self._drop_title = drop
        self._drop_items = (drop_id, drop_sub)
        drop.bind("<Button-1>", lambda _e: self.add_files())

        brow = ttk.Frame(body, style="Card.TFrame")
        brow.pack(fill="x", pady=(4, 0))
        b1 = ttk.Button(brow, text="", command=self.add_files)
        self.W(b1, "browse")
        b1.pack(side="left")
        b2 = ttk.Button(brow, text="", command=self.add_folder)
        self.W(b2, "folder")
        b2.pack(side="left", padx=(6, 0))
        hint = ttk.Label(brow, text="", style="MutedCard.TLabel")
        hint.pack(side="left", padx=10)
        self.W(hint, "browse_hint")

        wf = ttk.Frame(body, style="Card.TFrame")
        wf.pack(fill="x", pady=(10, 0))
        self._steps: list[tuple[ttk.Label, ttk.Label]] = []
        keys = ["wf_import", "wf_transcribe", "wf_translate", "wf_export"]
        for i, key in enumerate(keys):
            circle = ttk.Label(wf, text=str(i + 1), style="StepCircle.TLabel")
            circle.pack(side="left")
            name = ttk.Label(wf, text="", style="Step.TLabel")
            name.pack(side="left", padx=(5, 14 if i < 3 else 0))
            self.W(name, key)
            self._steps.append((circle, name))
        self.set_stage(0)

        fields = ttk.Frame(body, style="Card.TFrame")
        fields.pack(fill="x", pady=(10, 0))
        f1 = ttk.Frame(fields, style="Card.TFrame")
        f1.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.W(ttk.Label(f1, text="", style="MutedCard.TLabel"), "src_lang").pack(anchor="w")
        self.cb_source = ttk.Combobox(f1, textvariable=self.var_source, state="readonly")
        self.cb_source.pack(fill="x", pady=(3, 0))
        f2 = ttk.Frame(fields, style="Card.TFrame")
        f2.pack(side="left", fill="x", expand=True)
        self.W(ttk.Label(f2, text="", style="MutedCard.TLabel"), "tgt_lang").pack(anchor="w")
        self.cb_target = ttk.Combobox(f2, textvariable=self.var_target, state="readonly")
        self.cb_target.pack(fill="x", pady=(3, 0))

        self._toggle_line(body, "tog1", "tog1_s", self.var_translate)
        self._toggle_line(body, "tog2", "tog2_s", self.var_tts, fmt=self._engine_fmt)

        action = ttk.Frame(body, style="Card.TFrame")
        action.pack(fill="x", pady=(8, 0))
        self.btn_start = ttk.Button(
            action, text="", style="Primary.TButton", command=self.start
        )
        self.W(self.btn_start, "start_btn")
        self.btn_start.pack(side="right")
        self.btn_cancel = ttk.Button(action, text="", command=self.cancel)
        self.W(self.btn_cancel, "cancel")
        self.btn_cancel.pack(side="right", padx=(0, 8))
        self.btn_cancel.state(["disabled"])

    def _engine_fmt(self) -> dict:
        return {"engine": dialogs.engine_display_name(self.var_engine.get() or "piper", self.lang)}

    def _toggle_line(self, parent, key: str, sub_key: str, var: BooleanVar, fmt=None) -> None:
        row = ttk.Frame(parent, style="Card.TFrame")
        row.pack(fill="x", pady=(8, 0))
        col = ttk.Frame(row, style="Card.TFrame")
        col.pack(side="left")
        ttk.Label(col, text="", style="Card.TLabel").pack(anchor="w")
        self._texts.append((col.winfo_children()[-1], key, {}))
        sub = ttk.Label(col, text="", style="MutedCard.TLabel")
        sub.pack(anchor="w")
        self._texts.append((sub, sub_key, fmt if fmt else {}))
        Toggle(row, var, bg=PANEL).pack(side="right")

    def _build_recent_card(self, parent) -> None:
        card = self._card(parent, "recent")
        head = card.winfo_children()[0]
        view = ttk.Label(head, text="", style="CardTag.TLabel", foreground=LIME, cursor="hand2")
        view.pack(side="right")
        self.W(view, "view_all")
        view.bind("<Button-1>", lambda _e: self._open_exports())

        tree_frame = ttk.Frame(card, style="Card.TFrame")
        tree_frame.pack(fill="both", expand=True, padx=14)
        cols = ("lang", "status")
        self.tree = ttk.Treeview(tree_frame, columns=cols, show="tree headings", height=3)
        self._headings: list[tuple[str, str]] = [
            ("#0", "col_file"), ("lang", "col_lang"), ("status", "col_status"),
        ]
        for col, key in self._headings:
            self.tree.heading(col, text=t(key, self.lang))
        self.tree.column("#0", width=330, anchor=W)
        self.tree.column("lang", width=110, anchor=W)
        self.tree.column("status", width=150, anchor=W)
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._preview_selected())

        bar = ttk.Frame(card, style="Card.TFrame")
        bar.pack(fill="x", padx=14, pady=(4, 4))
        for key, cmd in (("add", self.add_files), ("remove", self.remove_selected),
                         ("clear", self.clear_files)):
            b = ttk.Button(bar, text="", style="Mini.TButton", command=cmd)
            self.W(b, key)
            b.pack(side="left", padx=(0, 6))

    def _build_preview_card(self, parent) -> None:
        card = ttk.Frame(parent, style="Card.TFrame")
        card.pack(fill="both", expand=True, pady=(0, 12))
        head = ttk.Frame(card, style="Card.TFrame")
        head.pack(fill="x", padx=12, pady=(10, 6))
        self.W(ttk.Label(head, text="", style="CardHead.TLabel"), "preview").pack(side="left")
        self.preview_meta = ttk.Label(head, text="", style="CardTag.TLabel")
        self.preview_meta.pack(side="right")

        self.preview_text = Text(
            card, height=6, wrap="word", state="disabled", bg=PANEL, fg=TEXT,
            relief="flat", highlightthickness=0, font=("Segoe UI", 9), borderwidth=0,
        )
        self.preview_text.pack(fill="both", expand=True, padx=12)
        self.preview_text.tag_configure("ts", foreground=LIME)
        self.preview_text.tag_configure("tx", foreground=TEXT)
        self.preview_text.tag_configure("hint", foreground=MUTED)

        prow = ttk.Frame(card, style="Card.TFrame")
        prow.pack(fill="x", padx=12, pady=(8, 12))
        self.play_btn = ttk.Label(prow, text="▶", style="Play.TLabel", cursor="hand2")
        self.play_btn.pack(side="left")
        self.play_btn.bind("<Button-1>", lambda _e: self._play_track())
        self.play_hint = ttk.Label(prow, text="", style="MutedCard.TLabel")
        self.play_hint.pack(side="left", padx=8)
        self._set_preview_empty()

    def _build_voice_card(self, parent) -> None:
        card = ttk.Frame(parent, style="Card.TFrame")
        card.pack(fill="x")
        head = ttk.Frame(card, style="Card.TFrame")
        head.pack(fill="x", padx=12, pady=(10, 4))
        self.W(ttk.Label(head, text="", style="CardHead.TLabel"), "voice_card").pack(side="left")
        badge = ttk.Label(head, text="", style="Badge.TLabel", padding=(6, 2))
        badge.pack(side="right")
        self.W(badge, "badge")

        rows = ttk.Frame(card, style="Card.TFrame")
        rows.pack(fill="x", padx=12)
        r1 = ttk.Frame(rows, style="Card.TFrame")
        r1.pack(fill="x", pady=(2, 0))
        ttk.Label(r1, text="Engine", style="MutedCard.TLabel").pack(side="left")
        self.cb_engine = ttk.Combobox(
            r1, textvariable=self.var_engine, state="readonly", width=18
        )
        self.cb_engine.pack(side="right")
        self.cb_engine.bind("<<ComboboxSelected>>", lambda _e: self._engine_changed())
        r2 = ttk.Frame(rows, style="Card.TFrame")
        r2.pack(fill="x", pady=(6, 0))
        ttk.Label(r2, text="Voice", style="MutedCard.TLabel").pack(side="left")
        self.cb_voice = ttk.Combobox(r2, textvariable=self.var_voice, state="readonly")
        self.cb_voice.pack(side="right", fill="x", expand=True, padx=(10, 0))
        self.cb_voice.bind("<<ComboboxSelected>>", lambda _e: self._voice_changed())

        self.engine_desc = ttk.Label(card, text="", style="MutedCard.TLabel", wraplength=236)
        self.engine_desc.pack(anchor="w", padx=12, pady=(8, 0))
        self.license_lbl = ttk.Label(card, text="", style="MutedCard.TLabel", wraplength=236,
                                     justify="left")
        self.license_lbl.pack(anchor="w", padx=12, pady=(4, 0))
        note = ttk.Label(card, text="", style="MutedCard.TLabel", wraplength=236, justify="left")
        note.pack(anchor="w", padx=12, pady=(6, 0))
        self.W(note, "voice_note")

        acts = ttk.Frame(card, style="Card.TFrame")
        acts.pack(fill="x", padx=12, pady=(10, 12))
        b1 = ttk.Button(acts, text="", command=self._open_voices)
        self.W(b1, "btn_voice_settings")
        b1.pack(side="left", fill="x", expand=True)
        b2 = ttk.Button(acts, text="", command=self._preview_voice)
        self.W(b2, "btn_listen")
        b2.pack(side="left", fill="x", expand=True, padx=(6, 0))

    def _build_bottom(self, main) -> None:
        bottom = ttk.Frame(main)
        bottom.pack(fill="x", padx=22, pady=(6, 6))
        self.progress = ttk.Progressbar(bottom, mode="determinate", maximum=100)
        self.progress.pack(fill="x")
        row = ttk.Frame(bottom)
        row.pack(fill="x", pady=(2, 0))
        ttk.Label(row, textvariable=self.var_status).pack(side="left")
        console_row = ttk.Frame(bottom)
        console_row.pack(fill="x", pady=(3, 0))
        head = ttk.Frame(console_row)
        head.pack(fill="x")
        self.W(ttk.Label(head, text="", style="Muted.TLabel"), "console").pack(side="left")
        self.log_text = Text(
            console_row, height=3, wrap="word", state="disabled", bg="#0d0f13", fg="#c9cdd6",
            relief="flat", highlightthickness=0, font=("Consolas", 9), borderwidth=0,
        )
        self.log_text.pack(fill="both", expand=False, pady=(2, 0))
        self.log_text.tag_configure("err", foreground=RED)
        self.log_text.tag_configure("ok", foreground=LIME_D)

    def set_stage(self, stage: int) -> None:
        self._stage = stage
        for i, (circle, name) in enumerate(self._steps, start=1):
            if stage > i:
                circle.configure(style="StepCircleDone.TLabel", text="✓")
                name.configure(style="StepDone.TLabel")
            elif stage == i:
                circle.configure(style="StepCircleNow.TLabel", text=str(i))
                name.configure(style="StepNow.TLabel")
            else:
                circle.configure(style="StepCircle.TLabel", text=str(i))
                name.configure(style="Step.TLabel")

    def _hint(self, key: str) -> None:
        self.var_status.set(t(key, self.lang))

    def _open_voices(self):
        return dialogs.open_voices(self)

    def _open_prefs(self):
        return dialogs.open_prefs(self)

    def _open_exports(self) -> None:
        folder = self.config.get("outdir") or (
            os.path.dirname(os.path.abspath(self.files[0])) if self.files else ""
        )
        if folder and os.path.isdir(folder):
            os.startfile(folder)
        else:
            self._hint("nav_hint_exports")

    def apply_prefs(self, new: dict) -> None:
        self.config.update(new)
        self.config["source"] = self._resolve_source()
        self.config["target"] = self._resolve_target()
        save_config(self.config)
        lang = new.get("ui_lang")
        if lang and lang != self.lang:
            self.lang = lang
            self.apply_language()

    def _resolve_source(self) -> str:
        self._src_code = self._code_for(self.var_source, True)
        return self._src_code

    def _resolve_target(self) -> str:
        self._tgt_code = self._code_for(self.var_target, False)
        return self._tgt_code

    def _load_sapi_async(self) -> None:
        def loader() -> None:
            try:
                self.sapi_voices = voices_mod.sapi_catalog()
                self.events.put(("refresh_voices", None, None))
            except Exception:
                self.sapi_voices = []

        threading.Thread(target=loader, daemon=True).start()

    def _compute_disk_async(self) -> None:
        def walker() -> None:
            total = 0
            roots = [os.path.join(os.environ.get("LOCALAPPDATA") or "~", "VideoLocalizer")]
            for name in ("huggingface", "hub"):
                roots.append(os.path.expanduser(f"~/.cache/huggingface/{name}"))
            roots.append(os.path.expanduser("~/.cache/huggingface"))
            for root in roots:
                if not os.path.isdir(root):
                    continue
                for dirpath, _dirnames, filenames in os.walk(root):
                    for fname in filenames:
                        try:
                            total += os.path.getsize(os.path.join(dirpath, fname))
                        except OSError:
                            pass
            gb = round(total / (1 << 30), 1)
            self.events.put(("disk", gb, None))

        threading.Thread(target=walker, daemon=True).start()

    def engine_choices(self) -> list[str]:
        return ["piper", "sapi", "kokoro"]

    def _refresh_voice_choices(self) -> None:
        if not hasattr(self, "cb_voice"):
            return
        engine = self.var_engine.get() or tts_mod.default_engine()
        mapping: dict[str, str] = {}
        labels: list[str] = []
        if engine == "piper":
            for info in voices_mod.piper_catalog():
                labels.append(info.id)
                mapping[info.id] = info.id
        elif engine == "sapi":
            items = self.sapi_voices or voices_mod.sapi_catalog()
            for info in items:
                labels.append(info.name.replace("Windows SAPI · ", ""))
                mapping[labels[-1]] = info.id
        else:
            for info in voices_mod.kokoro_catalog():
                label = f"{info.name.replace('Kokoro · ', '')} ({info.language})"
                labels.append(label)
                mapping[label] = info.id
        self._voice_map = mapping
        self.cb_voice.configure(values=labels)
        current = self.var_voice.get()
        if current not in labels:
            default = voices_mod.TR_VOICE_KEY if engine == "piper" and voices_mod.TR_VOICE_KEY in labels else (
                labels[0] if labels else ""
            )
            self.var_voice.set(default)
        self.cb_engine.configure(values=self.engine_choices())
        self._update_engine_desc()

    def _engine_changed(self) -> None:
        engine = self.var_engine.get()
        self.config["tts_engine"] = engine
        self.config.pop("voice", None)
        self.var_voice.set("")
        self._refresh_voice_choices()
        save_config(self.config)

    def _voice_changed(self) -> None:
        self.config["voice_id"] = self._voice_map.get(self.var_voice.get(), self.var_voice.get())
        save_config(self.config)
        self._update_engine_desc()

    def select_voice(self, engine: str, voice_id: str) -> None:
        self.var_engine.set(engine)
        self._refresh_voice_choices()
        label = voice_id
        for lab, vid in self._voice_map.items():
            if vid == voice_id:
                label = lab
                break
        if label not in self.cb_voice["values"]:
            self.cb_voice.configure(values=list(self.cb_voice["values"]) + [label])
        self.var_voice.set(label)
        self.config["tts_engine"] = engine
        self.config["voice_id"] = voice_id
        save_config(self.config)
        self._update_engine_desc()

    def _update_engine_desc(self) -> None:
        if not hasattr(self, "engine_desc"):
            return
        engine = self.var_engine.get() or tts_mod.default_engine()
        self.engine_desc.configure(
            text=t(f"voice_desc_{engine}", self.lang, n=len(voices_mod.KOKORO_VOICES))
        )
        voice_id = self._voice_map.get(self.var_voice.get(), self.var_voice.get())
        self.license_lbl.configure(text=dialogs.voice_license_summary(engine, voice_id, self.lang))
        if hasattr(self, "cb_voice"):
            self.cb_voice.configure()

    def current_voice_id(self) -> str | None:
        label = self.var_voice.get()
        return self._voice_map.get(label, label or None)

    def _preview_voice(self) -> None:
        if self._busy:
            return
        self._busy = True
        engine = self.var_engine.get() or tts_mod.default_engine()
        voice = self.current_voice_id()
        lang = self._resolve_target()

        def worker() -> None:
            try:
                out = os.path.join(
                    os.environ.get("LOCALAPPDATA") or ".", "VideoLocalizer", "preview.wav"
                )
                text = (
                    "Merhaba, bu yerel seslendirme önizlemesidir."
                    if lang == "tr"
                    else "Hello, this is a local voice preview."
                )
                if engine == "kokoro":
                    # Kokoro Türkçe konuşmuyor; önizleme her zaman İngilizce.
                    text = "Hello, this is a local voice preview."
                tts_mod.preview_sample(out, engine=engine, voice=voice, text=text,
                                       log=lambda m: self.events.put(("log", m, None)))
                winsound.PlaySound(out, winsound.SND_ASYNC)
                self.events.put(("log", f"[tts] {t('playing', self.lang)} {engine}/{voice}", None))
            except Exception as exc:
                self.events.put(("log", f"[hata] {exc}", "err"))
            finally:
                self._busy = False

        threading.Thread(target=worker, daemon=True).start()

    def _play_track(self) -> None:
        if self._last_track and os.path.exists(self._last_track):
            winsound.PlaySound(self._last_track, winsound.SND_ASYNC)
            self.play_hint.configure(text=t("playing", self.lang))
        else:
            self.play_hint.configure(text=t("play_no_track", self.lang))

    def _set_preview_empty(self) -> None:
        self.preview_text.configure(state="normal")
        self.preview_text.delete("1.0", END)
        self.preview_text.insert(END, t("preview_empty", self.lang), "hint")
        self.preview_text.configure(state="disabled")
        self.preview_meta.configure(text="")

    def _show_preview(self, srt_path: str) -> None:
        try:
            cues = read_file(srt_path)
        except Exception:
            self._set_preview_empty()
            return
        self.preview_text.configure(state="normal")
        self.preview_text.delete("1.0", END)
        for cue in cues[:40]:
            ts = f"{cue.start // 60000:02d}:{(cue.start // 1000) % 60:02d}.{(cue.start % 1000) // 100}"
            self.preview_text.insert(END, f"{ts}  ", "ts")
            self.preview_text.insert(END, cue.text.replace("\n", " ") + "\n", "tx")
        if not cues:
            self.preview_text.insert(END, t("preview_empty", self.lang), "hint")
        self.preview_text.configure(state="disabled")
        end = cues[-1].end if cues else 0
        self.preview_meta.configure(
            text=f"{len(cues)} cue · {end // 60000:02d}:{(end // 1000) % 60:02d}"
        )
        track = os.path.splitext(srt_path)[0] + ".wav"
        self._last_track = track if os.path.exists(track) else None

    def _preview_selected(self) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        path = sel[0]
        ext = os.path.splitext(path)[1].lower()
        target = self._resolve_target()
        outdir = self.config.get("outdir") or os.path.dirname(os.path.abspath(path))
        stem = os.path.splitext(path)[0]
        candidates = [
            os.path.join(outdir, f"{os.path.basename(stem)}.{target}.srt"),
            stem + ".srt",
        ]
        if ext in SUB_EXTS:
            candidates.append(path)
        for cand in candidates:
            if os.path.exists(cand):
                self._show_preview(cand)
                track = os.path.splitext(cand)[0] + ".wav"
                self._last_track = track if os.path.exists(track) else None
                return
        self._set_preview_empty()

    def add_files(self) -> None:
        paths = filedialog.askopenfilenames(
            title=t("file_dialog_title", self.lang),
            filetypes=[
                ("Video / ses", "*.mp4 *.mkv *.mov *.avi *.webm *.m4v *.mp3 *.wav *.m4a *.aac *.ogg *.flac"),
                ("Altyazı", "*.srt *.vtt"),
                ("Tüm dosyalar", "*.*"),
            ],
        )
        self._add_paths(list(paths))

    def add_folder(self) -> None:
        folder = filedialog.askdirectory(title=t("folder_dialog_title", self.lang))
        if folder:
            self._add_paths(expand_inputs([folder]))

    def _add_paths(self, paths: list[str]) -> None:
        added = False
        for path in paths:
            if path in self.files:
                continue
            added = True
            self.files.append(path)
            ext = os.path.splitext(path)[1].lower()
            _tur = "altyazı" if ext in SUB_EXTS else "video/ses"
            self.tree.insert("", END, iid=path, text=os.path.basename(path), values=("", "…"))
        if added:
            self.set_stage(1)
            self._refresh_drop_hint()
            self._preview_selected_first()

    def _refresh_drop_hint(self) -> None:
        if not self.files:
            return
        drop_id, drop_sub = self._drop_items
        drop = self._drop_title
        name = os.path.basename(self.files[-1])
        size_mb = round(os.path.getsize(self.files[-1]) / (1 << 20), 1) if os.path.exists(self.files[-1]) else 0
        drop.itemconfigure(drop_id, text=name)
        drop.itemconfigure(drop_sub, text=f"{size_mb} MB · {len(self.files)} dosya")

    def _preview_selected_first(self) -> None:
        if self.files:
            self.tree.selection_set(self.files[-1])
            self._preview_selected()

    def remove_selected(self) -> None:
        for item in self.tree.selection():
            if item in self.files:
                self.files.remove(item)
            self.tree.delete(item)
        self._refresh_drop_hint()

    def clear_files(self) -> None:
        self.files.clear()
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.set_stage(0)
        self._set_preview_empty()
        drop_id, drop_sub = self._drop_items
        self._drop_title.itemconfigure(drop_id, text="")
        self._drop_title.itemconfigure(drop_sub, text="")

    def start(self) -> None:
        if self._busy or (self.worker and self.worker.is_alive()):
            return
        if not self.files:
            messagebox.showwarning(t("app_title", self.lang), t("browse_hint", self.lang))
            return
        source = self._resolve_source()
        target = self._resolve_target()
        translate_on = self.var_translate.get()
        if translate_on:
            try:
                backend = Context().get_backend(source, target)
                if not backend.supports(source, target):
                    raise RuntimeError(
                        f"{backend.label}: {source} -> {target}"
                    )
            except Exception as exc:
                messagebox.showerror(t("app_title", self.lang), str(exc))
                return

        voice = self.current_voice_id()
        engine = self.var_engine.get() or tts_mod.default_engine()
        outdir = self.config.get("outdir", "").strip()
        jobs: list[Job] = []
        for path in self.files:
            ext = os.path.splitext(path)[1].lower()
            jobs.append(
                Job(
                    input_path=path,
                    output_dir=outdir or os.path.dirname(os.path.abspath(path)),
                    target_lang=target if translate_on else AUTO_CODE,
                    source_lang=source,
                    translate=translate_on,
                    transcribe=ext not in SUB_EXTS,
                    tts=self.var_tts.get(),
                    tts_engine=engine if self.var_tts.get() else None,
                    embed=bool(self.config.get("embed", False)),
                    model=self.config.get("model", "small"),
                    voice=voice,
                    rate=None,
                    force_transcribe=bool(self.config.get("ignore_sidecar", False)),
                )
            )
            lang_text = t("lang_label", self.lang, src=self._lg_name(source), tgt=self._lg_name(target))
            if self.tree.exists(path):
                self.tree.set(path, "lang", lang_text)
                self.tree.set(path, "status", "…")

        self.total_jobs = len(jobs)
        self.finished_jobs = 0
        self.progress["value"] = 0
        self.btn_start.state(["disabled"])
        self.btn_cancel.state(["!disabled"])
        self._busy = True
        self.var_status.set(t("running", self.lang))
        self.set_stage(2)
        self.log(t("started_log", self.lang, n=len(jobs), lang=target))

        ctx = Context(
            log=lambda msg: self.events.put(("log", msg, None)),
            progress=lambda value, text: self.events.put(("progress", value, text)),
            cache_path=default_cache_path(),
        )
        self.ctx = ctx
        workers = int(self.config.get("workers", 1) or 1)

        def runner() -> None:
            def on_result(res: JobResult) -> None:
                status = t("done", self.lang) if res.ok else res.message[:60]
                minutes = 0.0
                if res.srt_path and os.path.exists(res.srt_path):
                    try:
                        minutes = sum(c.duration_ms for c in read_file(res.srt_path)) / 60000.0
                    except Exception:
                        minutes = 0.0
                self.events.put(("file", res.job.input_path, status))
                self.events.put(("file_done", res, minutes))

            try:
                results = run_jobs(jobs, ctx, workers=max(1, workers), on_result=on_result)
                ok = sum(1 for r in results if r.ok)
                self.events.put(("done", t("done_log", self.lang, ok=ok, total=len(results)), None))
            except Exception as exc:
                traceback.print_exc()
                self.events.put(("done", f"Hata: {exc}", None))

        self.worker = threading.Thread(target=runner, daemon=True)
        self.worker.start()

    def cancel(self) -> None:
        if self.ctx:
            self.ctx.cancel.set()
            self.var_status.set(t("canceling", self.lang))
            self.log(t("cancel_log", self.lang))

    def log(self, message: str, tag: str | None = None) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert(END, message + "\n", tag or "")
        self.log_text.see(END)
        self.log_text.configure(state="disabled")

    def _save_stats(self) -> None:
        self.config["stats"] = {
            "projects": self.stats["projects"],
            "minutes": round(self.stats["minutes"], 1),
            "disk_gb": self.stats["disk_gb"],
        }
        save_config(self.config)

    def _update_metrics(self) -> None:
        self.metric_vars["projects"].set(str(self.stats["projects"]))
        minutes = self.stats["minutes"]
        self.metric_vars["minutes"].set(
            str(int(minutes)) if minutes < 1000 else f"{minutes / 1000:.1f}k"
        )
        self.metric_vars["ready"].set(str(self.stats["ready"]))
        self.metric_vars["disk"].set(str(self.stats["disk_gb"]))
        feet = self._metric_foot
        n_langs = len(CODE_TO_NAME)
        feet["projects"].configure(
            text=f"+1 {t('m_week', self.lang)}", foreground=LIME_D
        )
        feet["minutes"].configure(text=t("m_across", self.lang, n=n_langs))
        feet["ready"].configure(text=t("m_no_cloud", self.lang))
        feet["disk"].configure(text=t("m_model_cache", self.lang))

    def _poll(self) -> None:
        try:
            while True:
                kind, payload, extra = self.events.get_nowait()
                if kind == "log":
                    self.log(str(payload), extra)
                elif kind == "progress":
                    total = max(1, self.total_jobs)
                    overall = (self.finished_jobs + float(payload)) / total * 100
                    self.progress["value"] = max(0.0, min(100.0, overall))
                    if payload >= 0.55:
                        self.set_stage(3)
                    if extra:
                        self.var_status.set(str(extra))
                elif kind == "file":
                    if self.tree.exists(payload):
                        self.tree.set(payload, "status", str(extra))
                elif kind == "file_done":
                    self.finished_jobs += 1
                    res, minutes = payload, extra
                    self.stats["projects"] += 1
                    self.stats["minutes"] += float(minutes or 0.0)
                    if res.ok:
                        self.stats["ready"] += 1
                    self._update_metrics()
                    self._save_stats()
                    if res.job.input_path in self.files:
                        self.tree.selection_set(res.job.input_path)
                        self._preview_selected()
                elif kind == "done":
                    self.progress["value"] = 100
                    self.var_status.set(str(payload))
                    self.log(str(payload), "ok" if "Hata" not in str(payload) else "err")
                    self.btn_start.state(["!disabled"])
                    self.btn_cancel.state(["disabled"])
                    self._busy = False
                    self.set_stage(4)
                elif kind == "refresh_voices":
                    self._refresh_voice_choices()
                elif kind == "disk":
                    self.stats["disk_gb"] = float(payload)
                    self._update_metrics()
                    self._save_stats()
        except queue.Empty:
            pass
        self.root.after(120, self._poll)

    def _on_close(self) -> None:
        if self.ctx and self.worker and self.worker.is_alive():
            self.ctx.cancel.set()
        self.config["geometry"] = self.root.geometry().split("+")[0]
        self.config["source"] = self._resolve_source()
        self.config["target"] = self._resolve_target()
        self.config["translate"] = self.var_translate.get()
        self.config["tts"] = self.var_tts.get()
        self.config["tts_engine"] = self.var_engine.get() or tts_mod.default_engine()
        save_config(self.config)
        self.root.destroy()


def run_app() -> None:
    root = Tk()
    style = ttk.Style(root)
    if "clam" in style.theme_names():
        style.theme_use("clam")
    App(root)
    root.mainloop()
