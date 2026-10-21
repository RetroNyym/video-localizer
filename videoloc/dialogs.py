from __future__ import annotations

import os
import queue
import threading
import webbrowser
from tkinter import (
    END,
    BooleanVar,
    E,
    StringVar,
    Text,
    Toplevel,
    W,
    messagebox,
    ttk,
)

from . import i18n
from . import tts as tts_mod
from . import voices as voices_mod
from .langs import CODE_TO_NAME


class _Async:
    def __init__(self) -> None:
        self.events: queue.Queue = queue.Queue()

    def put(self, kind: str, payload=None) -> None:
        self.events.put((kind, payload))

    def drain(self) -> list[tuple[str, object]]:
        out: list[tuple[str, object]] = []
        while True:
            try:
                out.append(self.events.get_nowait())
            except queue.Empty:
                return out


class VoicesDialog(Toplevel):
    def __init__(self, app) -> None:
        super().__init__(app.root)
        self.app = app
        self.lang = app.lang
        self.title(i18n.t("voices_dialog", self.lang))
        self.geometry("920x600")
        self.minsize(820, 520)
        self.configure(bg="#0b0c0f")
        self.transient(app.root)
        self._async = _Async()
        self._rows: dict[str, object] = {}
        self._build()
        self._load_tree()
        self._poll()
        self.after(50, self._load_sapi_async)

    def _build(self) -> None:
        pad = {"padx": 12, "pady": 8}
        top = ttk.Frame(self)
        top.pack(fill="x", **pad)

        self.search_var = StringVar()
        entry = ttk.Entry(top, textvariable=self.search_var, width=32)
        entry.pack(side="left")
        entry.bind("<KeyRelease>", lambda _e: self._load_tree())

        self.installed_only = BooleanVar(value=False)
        ttk.Checkbutton(
            top, text=i18n.t("installed_only", self.lang), variable=self.installed_only,
            command=self._load_tree,
        ).pack(side="left", padx=10)

        ttk.Button(top, text=i18n.t("cv_refresh", self.lang), command=self._refresh_catalog).pack(
            side="right"
        )

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True, **pad)

        cols = ("engine", "language", "license", "status")
        self.tree = ttk.Treeview(body, columns=cols, show="tree headings", height=14)
        self.tree.heading("#0", text=i18n.t("col_file", self.lang))
        self.tree.heading("engine", text=i18n.t("engine", self.lang))
        self.tree.heading("language", text=i18n.t("col_lang", self.lang))
        self.tree.heading("license", text=i18n.t("license", self.lang))
        self.tree.heading("status", text=i18n.t("status_col", self.lang))
        self.tree.column("#0", width=330, anchor=W)
        self.tree.column("engine", width=80, anchor=W)
        self.tree.column("language", width=80, anchor=W)
        self.tree.column("license", width=150, anchor=W)
        self.tree.column("status", width=130, anchor=W)
        vsb = ttk.Scrollbar(body, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="left", fill="y")
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._show_detail())

        right = ttk.Frame(body, width=330)
        right.pack(side="right", fill="y", padx=(10, 0))
        right.pack_propagate(False)

        ttk.Label(right, text=i18n.t("preview", self.lang), style="CardHead.TLabel").pack(anchor=W)
        self.detail = Text(right, height=16, wrap="word", state="disabled")
        self.detail.pack(fill="both", expand=True, pady=(6, 8))
        self.detail.tag_configure("h", foreground="#c5f36a")

        actions = ttk.Frame(right)
        actions.pack(fill="x")
        self.btn_use = ttk.Button(actions, text=i18n.t("use_voice", self.lang), command=self._use)
        self.btn_use.pack(side="left", fill="x", expand=True)
        self.btn_dl = ttk.Button(actions, text=i18n.t("download_voice", self.lang), command=self._download)
        self.btn_dl.pack(side="left", fill="x", expand=True, padx=(6, 0))
        self.btn_src = ttk.Button(actions, text=i18n.t("open_source", self.lang), command=self._open_source)
        self.btn_src.pack(fill="x", pady=(6, 0))

        self.footer = ttk.Label(
            self,
            text=i18n.t("voice_note", self.lang),
            style="Muted.TLabel",
            wraplength=860,
        )
        self.footer.pack(fill="x", padx=12, pady=(0, 10))

    def _catalog_rows(self) -> list[tuple[str, voices_mod.VoiceInfo]]:
        rows: list[tuple[str, voices_mod.VoiceInfo]] = []
        for info in voices_mod.piper_catalog():
            rows.append((f"piper:{info.id}", info))
        for info in self.app.sapi_voices:
            rows.append((f"sapi:{info.id}", info))
        lib_ok, ready = voices_mod.kokoro_installed()
        rows.append(
            (
                "kokoro:kokoro",
                voices_mod.VoiceInfo(
                    engine="kokoro",
                    id="kokoro",
                    name="Kokoro 82M (hexgrad)",
                    language="en-US, en-GB, ja, es, fr, hi, it, pt-BR, zh",
                    license=voices_mod.KOKORO_INFO["license"],
                    license_note=voices_mod.KOKORO_INFO["license_note"],
                    source_url=voices_mod.KOKORO_INFO["source"],
                    installed=bool(lib_ok and ready),
                ),
            )
        )
        cv = voices_mod.refresh_commonvoice() if False else dict(voices_mod.COMMONVOICE_INFO)
        rows.append(
            (
                "data:commonvoice-tr",
                voices_mod.VoiceInfo(
                    engine="data",
                    id="commonvoice-tr",
                    name=cv["name"],
                    language=cv["locale"],
                    license="Veri kümesi (site koşulları)",
                    license_note=cv["note"],
                    source_url=cv["page"],
                    installed=True,
                ),
            )
        )
        return rows

    def _load_tree(self) -> None:
        self.tree.delete(*self.tree.get_children())
        self._rows = {}
        query = self.search_var.get()
        installed_only = self.installed_only.get()
        for iid, info in self._catalog_rows():
            if installed_only and not info.installed and info.engine != "data":
                continue
            if query:
                blob = f"{info.name} {info.language} {info.id}".lower()
                if query.lower() not in blob:
                    continue
            status = i18n.t("installed", self.lang) if info.installed else i18n.t("not_installed", self.lang)
            self.tree.insert(
                "", END, iid=iid, text=info.name,
                values=(info.engine, info.language, info.license, status),
            )
            self._rows[iid] = info

    def _selected(self):
        sel = self.tree.selection()
        if not sel:
            return None, None
        iid = sel[0]
        return iid, self._rows.get(iid)

    def _set_detail(self, lines: list[tuple[str, str]]) -> None:
        self.detail.configure(state="normal")
        self.detail.delete("1.0", END)
        for head, value in lines:
            self.detail.insert(END, head + "\n", "h")
            self.detail.insert(END, value + "\n\n")
        self.detail.configure(state="disabled")

    def _show_detail(self) -> None:
        iid, info = self._selected()
        if not info:
            return
        lines = [
            (i18n.t("engine", self.lang), info.engine),
            (i18n.t("col_lang", self.lang), f"{info.language} {info.language_native}".strip()),
            (i18n.t("license", self.lang), info.license),
            ("", info.license_note),
            (i18n.t("size", self.lang), f"{info.size_mb} MB" if info.size_mb else "—"),
            (i18n.t("source", self.lang), info.source_url),
        ]
        if info.engine == "kokoro":
            lines.append((i18n.t("kokoro_langs", self.lang), ", ".join(voices_mod.KOKORO_INFO["languages"])))
            lines.append(("", i18n.t("kokoro_tr", self.lang)))
        if info.engine == "data":
            cv = voices_mod.COMMONVOICE_INFO
            lines.append(("Hedef cümle", str(cv["target_sentence_count"])))
            lines.append(("", cv["note"]))
        self._set_detail(lines)

    def _use(self) -> None:
        iid, info = self._selected()
        if not info or info.engine == "data":
            return
        if not info.installed and info.engine == "piper":
            self._download()
            return
        if info.engine == "kokoro":
            lib_ok, ready = voices_mod.kokoro_installed()
            if not lib_ok:
                messagebox.showinfo(
                    i18n.t("voices_dialog", self.lang),
                    "pip install kokoro-onnx\n" + voices_mod.KOKORO_INFO["license_note"],
                    parent=self,
                )
                return
            if not ready:
                self._download()
                return
        self.app.select_voice(info.engine, info.id)
        self.footer.configure(text=f"✓ {info.name}")

    def _download(self) -> None:
        iid, info = self._selected()
        if not info:
            return
        if info.engine == "piper":
            threading.Thread(
                target=self._download_piper_worker, args=(info.id,), daemon=True
            ).start()
        elif info.engine == "kokoro":
            threading.Thread(target=self._download_kokoro_worker, daemon=True).start()

    def _download_piper_worker(self, key: str) -> None:
        try:
            def prog(name: str, done: int, total: int) -> None:
                self._async.put(
                    "dl",
                    (key, round(done / (1 << 20)), max(1, round(total / (1 << 20)))),
                )

            voices_mod.download_piper_voice(key, progress=prog)
            self._async.put("done", key)
        except Exception as exc:
            self._async.put("err", str(exc))

    def _download_kokoro_worker(self) -> None:
        try:
            def prog(name: str, done: int, total: int) -> None:
                self._async.put(
                    "dl", (name, round(done / (1 << 20)), max(1, round(total / (1 << 20))))
                )

            voices_mod.download_kokoro_models(progress=prog)
            self._async.put("done", "kokoro")
        except Exception as exc:
            self._async.put("err", str(exc))

    def _load_sapi_async(self) -> None:
        def loader() -> None:
            try:
                items = voices_mod.sapi_catalog()
                self._async.put("sapi", items)
            except Exception as exc:
                self._async.put("err", str(exc))

        threading.Thread(target=loader, daemon=True).start()

    def _refresh_catalog(self) -> None:
        def worker() -> None:
            ok = voices_mod.refresh_piper_catalog()
            cv = voices_mod.refresh_commonvoice()
            self._async.put("catalog", (ok, cv))

        threading.Thread(target=worker, daemon=True).start()

    def _open_source(self) -> None:
        _iid, info = self._selected()
        if info and info.source_url:
            webbrowser.open(info.source_url)

    def _poll(self) -> None:
        if not self.winfo_exists():
            return
        for kind, payload in self._async.drain():
            if kind == "dl":
                key, done, total = payload
                self.footer.configure(
                    text=i18n.t("downloading", self.lang, name=key, done=done, total=total)
                )
            elif kind == "done":
                self.footer.configure(
                    text=i18n.t("downloaded", self.lang, name=str(payload))
                )
                self._load_tree()
                self.app.refresh_voice_choices()
            elif kind == "err":
                self.footer.configure(text=f"! {payload}")
            elif kind == "sapi":
                self.app.sapi_voices = payload
                self._load_tree()
            elif kind == "catalog":
                ok, cv = payload
                self._load_tree()
                self.footer.configure(
                    text=i18n.t("cv_refreshed", self.lang, date=cv.get("refreshed", "?"))
                )
                _ = ok
        self.after(200, self._poll)


class PrefsDialog(Toplevel):
    def __init__(self, app) -> None:
        super().__init__(app.root)
        self.app = app
        self.lang = app.lang
        self.title(i18n.t("prefs_dialog", self.lang))
        self.geometry("520x470")
        self.minsize(480, 430)
        self.configure(bg="#0b0c0f")
        self.transient(app.root)
        cfg = app.config
        self.var_lang = StringVar(value=i18n.LANGUAGES_UI.get(cfg.get("ui_lang", "tr"), "Türkçe"))
        self.var_model = StringVar(value=cfg.get("model", "small"))
        self.var_workers = StringVar(value=str(cfg.get("workers", 1)))
        self.var_embed = BooleanVar(value=bool(cfg.get("embed", False)))
        self.var_sidecar = BooleanVar(value=bool(cfg.get("ignore_sidecar", False)))
        self.var_outdir = StringVar(value=cfg.get("outdir", ""))
        self._build()

    def _build(self) -> None:
        pad = {"padx": 14, "pady": 8}
        body = ttk.Frame(self)
        body.pack(fill="both", expand=True, padx=6, pady=6)

        ttk.Label(body, text=i18n.t("prefs_ui_lang", self.lang)).grid(row=0, column=0, sticky=W, **pad)
        ttk.Combobox(
            body, textvariable=self.var_lang, state="readonly",
            values=list(i18n.LANGUAGES_UI.values()),
        ).grid(row=0, column=1, sticky=E, **pad)

        ttk.Label(body, text=i18n.t("prefs_model", self.lang)).grid(row=1, column=0, sticky=W, **pad)
        from .transcribe import MODEL_SIZES

        ttk.Combobox(
            body, textvariable=self.var_model, state="readonly", values=MODEL_SIZES
        ).grid(row=1, column=1, sticky=E, **pad)
        ttk.Label(body, text=i18n.t("prefs_model_s", self.lang), style="Muted.TLabel").grid(
            row=2, column=1, sticky=W, padx=14
        )

        ttk.Label(body, text=i18n.t("prefs_workers", self.lang)).grid(row=3, column=0, sticky=W, **pad)
        ttk.Combobox(
            body, textvariable=self.var_workers, state="readonly", values=["1", "2", "3", "4"]
        ).grid(row=3, column=1, sticky=E, **pad)

        ttk.Checkbutton(body, text=i18n.t("prefs_embed", self.lang), variable=self.var_embed).grid(
            row=4, column=0, columnspan=2, sticky=W, **pad
        )
        ttk.Checkbutton(body, text=i18n.t("prefs_sidecar", self.lang), variable=self.var_sidecar).grid(
            row=5, column=0, columnspan=2, sticky=W, **pad
        )

        ttk.Label(body, text=i18n.t("prefs_outdir", self.lang)).grid(row=6, column=0, sticky=W, **pad)
        row = ttk.Frame(body)
        row.grid(row=6, column=1, sticky=E, **pad)
        ttk.Entry(row, textvariable=self.var_outdir, width=30).pack(side="left")
        ttk.Button(
            row, text=i18n.t("prefs_browse", self.lang), width=3,
            command=self._pick,
        ).pack(side="left", padx=(4, 0))

        ttk.Button(body, text=i18n.t("prefs_save", self.lang), command=self._save).grid(
            row=7, column=1, sticky=E, padx=14, pady=18
        )
        body.columnconfigure(1, weight=1)

    def _pick(self) -> None:
        from tkinter import filedialog

        folder = filedialog.askdirectory(parent=self)
        if folder:
            self.var_outdir.set(folder)

    def _save(self) -> None:
        lang_name = self.var_lang.get()
        ui_lang = "en" if lang_name == "English" else "tr"
        try:
            workers = max(1, min(4, int(self.var_workers.get())))
        except ValueError:
            workers = 1
        self.app.apply_prefs(
            {
                "ui_lang": ui_lang,
                "model": self.var_model.get(),
                "workers": workers,
                "embed": self.var_embed.get(),
                "ignore_sidecar": self.var_sidecar.get(),
                "outdir": self.var_outdir.get().strip(),
            }
        )
        self.destroy()


def open_voices(app) -> VoicesDialog:
    return VoicesDialog(app)


def open_prefs(app) -> PrefsDialog:
    return PrefsDialog(app)


def engine_display_name(engine: str, lang: str) -> str:
    return {
        "piper": "Piper",
        "sapi": "Windows SAPI",
        "kokoro": "Kokoro",
    }.get(engine, engine)


def voice_license_summary(engine: str, voice_id: str, lang: str) -> str:
    if engine == "piper" and voice_id == voices_mod.TR_VOICE_KEY:
        return voices_mod.TR_LICENSE_NOTE
    if engine == "kokoro":
        return voices_mod.KOKORO_INFO["license_note"]
    if engine == "sapi":
        return "Windows SAPI sesleri işletim sistemiyle gelir."
    return voices_mod.GENERIC_LICENSE_NOTE


_ = (CODE_TO_NAME, tts_mod, os, W)
