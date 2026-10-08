"""Ventana principal (CustomTkinter) con estética Windows Vista / 7 (Aero)."""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk

from ..config.paths import cache_dir
from ..config.settings import Settings
from ..core.events import JobStarted, TrackFinished, TrackProgress, TrackStarted
from ..models.options import OutputFormat
from ..models.playlist import Playlist
from ..models.results import TrackStatus
from . import aero
from .aero import (ACTIVE_BLUE, BG, ERR_RED, OK_GREEN, PANEL_BORDER, STATUS_BG, TEXT, TEXT_DIM, AeroButton,
                   AeroGroup, AeroProgress, AeroToggle, make_entry, make_menu, ui_font)
from .controller import EVENT, JOB_DONE, JOB_ERROR, LOAD_ERROR, LOAD_PROGRESS, LOADED, Controller
from .form_state import BITRATE_LABELS, NORMALIZE_LABELS, WORKER_CHOICES, FormState
from .progress_model import ACTIVE, QUEUED, ProgressTracker, row_for_progress, row_for_result

log = logging.getLogger(__name__)
APP_TITLE = "Spotify2Audio"
ROW_COLORS = {"queued": "#6B7280", "active": ACTIVE_BLUE, "ok": OK_GREEN, "failed": ERR_RED,
              "skipped": "#6B7280", "cancelled": "#B26A00"}
FORMAT_OPTIONS = [(OutputFormat.MP3.value, "MP3  ·  iPod y reproductores MP3"),
                  (OutputFormat.M4A.value, "M4A (AAC)  ·  iPod, iTunes"),
                  (OutputFormat.WAV.value, "WAV  ·  CD de audio sin compresión")]


class App(ctk.CTk):
    def __init__(self, controller: Controller | None = None) -> None:
        super().__init__()
        ctk.set_appearance_mode("light")
        self.title(APP_TITLE)
        self.geometry("1040x800")
        self.minsize(960, 720)
        self.configure(fg_color=BG)
        self._set_icon()

        self.controller = controller or Controller()
        self.settings = Settings.load()
        self.form = FormState.from_settings(self.settings)
        self.playlist: Playlist | None = None
        self.tracker: ProgressTracker | None = None
        self.running = False
        self._phase = 0.0
        self._form_widgets: list = []

        aero.style_treeview(self, getattr(self, "_get_window_scaling", lambda: 1.0)())
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._build_header()
        self._build_body()
        self._build_actions()
        self._build_statusbar()
        self._update_format_dependent()
        self._sync_buttons()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(50, self._poll)

    # =============================================================== construcción
    def _set_icon(self) -> None:
        if sys.platform != "win32":
            return
        ico = cache_dir() / "app.ico"
        if (ico.exists() or aero.make_app_icon(ico)):
            self.after(300, lambda: self._safe_icon(ico))    # CTk pisa el icono durante ~200 ms

    def _safe_icon(self, ico: Path) -> None:
        try:
            self.iconbitmap(str(ico))
        except tk.TclError:
            pass

    def _build_header(self) -> None:
        self.header = ctk.CTkLabel(self, text="", height=84, fg_color="transparent")
        self.header.grid(row=0, column=0, sticky="ew")
        self._header_w = 0
        self.header.bind("<Configure>", self._on_header_resize)

    def _on_header_resize(self, event) -> None:
        scale = getattr(self.header, "_get_widget_scaling", lambda: 1.0)()
        w = max(int(event.width / scale), 400)
        if w != self._header_w:
            self._header_w = w
            img = aero.make_header_image(w, 84, APP_TITLE, "Convierte tus playlists de Spotify en música para iPod, MP3 y CD")
            self.header.configure(image=ctk.CTkImage(img, size=(w, 84)))

    def _build_body(self) -> None:
        body = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        body.grid(row=1, column=0, sticky="nsew", padx=12, pady=(10, 4))
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)
        left = ctk.CTkFrame(body, fg_color="transparent", width=380)
        left.grid(row=0, column=0, sticky="ns", padx=(0, 10))
        right = ctk.CTkFrame(body, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew")
        self._build_left(left)
        self._build_right(right)

    # ---- columna izquierda: configuración ------------------------------------------------
    def _build_left(self, left: ctk.CTkFrame) -> None:
        left.grid_columnconfigure(0, weight=1)

        g = AeroGroup(left, "Playlist de Spotify")
        g.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        row = ctk.CTkFrame(g.body, fg_color="transparent")
        row.grid(row=0, column=0, sticky="ew")
        row.grid_columnconfigure(0, weight=1)
        self.url_entry = make_entry(row, placeholder_text="Pega aquí el enlace de tu playlist")
        self.url_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        if self.form.url:
            self.url_entry.insert(0, self.form.url)
        self.url_entry.bind("<Return>", lambda _e: self._on_load())
        self.load_btn = AeroButton(row, "Cargar", self._on_load, width=84, primary=True)
        self.load_btn.grid(row=0, column=1)
        self.info_label = ctk.CTkLabel(g.body, text="Solo se pueden leer playlists tuyas o colaborativas.",
                                       text_color=TEXT_DIM, font=ui_font(12), anchor="w", justify="left", wraplength=330)
        self.info_label.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        self._form_widgets += [self.url_entry, self.load_btn]

        g = AeroGroup(left, "Formato de salida")
        g.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        self.fmt_var = tk.StringVar(value=self.form.output_format)
        for i, (value, label) in enumerate(FORMAT_OPTIONS):
            t = AeroToggle(g.body, label, "radio", self.fmt_var, value, command=self._update_format_dependent)
            t.grid(row=i, column=0, sticky="w", pady=1)
            self._form_widgets.append(t)
        q = ctk.CTkFrame(g.body, fg_color="transparent")
        q.grid(row=3, column=0, sticky="w", pady=(8, 0))
        ctk.CTkLabel(q, text="Calidad:", text_color=TEXT, font=ui_font(13)).grid(row=0, column=0, padx=(0, 8))
        self.bitrate_var = tk.StringVar(value=self.form.bitrate if self.form.bitrate in BITRATE_LABELS else BITRATE_LABELS[0])
        self.bitrate_menu = make_menu(q, BITRATE_LABELS, self.bitrate_var, width=130)
        self.bitrate_menu.grid(row=0, column=1)
        self.quality_hint = ctk.CTkLabel(g.body, text="", text_color=TEXT_DIM, font=ui_font(12), anchor="w",
                                         justify="left", wraplength=330)
        self.quality_hint.grid(row=4, column=0, sticky="ew", pady=(6, 0))
        self._form_widgets.append(self.bitrate_menu)

        g = AeroGroup(left, "Audio y archivos")
        g.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        self.norm_var = tk.StringVar(value=NORMALIZE_LABELS.get(self.form.normalize, NORMALIZE_LABELS["loudnorm"]))
        self.norm_menu = make_menu(g.body, list(NORMALIZE_LABELS.values()), self.norm_var, width=330)
        self.norm_menu.grid(row=0, column=0, sticky="w")
        self.folders_var = tk.BooleanVar(value=self.form.create_folders)
        self.skip_var = tk.BooleanVar(value=self.form.skip_existing)
        c1 = AeroToggle(g.body, "Crear carpetas  Artista / Álbum", "check", self.folders_var)
        c2 = AeroToggle(g.body, "Omitir canciones ya descargadas", "check", self.skip_var)
        c1.grid(row=1, column=0, sticky="w", pady=(8, 1))
        c2.grid(row=2, column=0, sticky="w", pady=1)
        w = ctk.CTkFrame(g.body, fg_color="transparent")
        w.grid(row=3, column=0, sticky="w", pady=(6, 0))
        ctk.CTkLabel(w, text="Descargas simultáneas:", text_color=TEXT, font=ui_font(13)).grid(row=0, column=0, padx=(0, 8))
        self.workers_var = tk.StringVar(value=self.form.workers if self.form.workers in WORKER_CHOICES else "1")
        self.workers_menu = make_menu(w, WORKER_CHOICES, self.workers_var, width=70)
        self.workers_menu.grid(row=0, column=1)
        self._form_widgets += [self.norm_menu, c1, c2, self.workers_menu]

        g = AeroGroup(left, "Carpeta de destino")
        g.grid(row=3, column=0, sticky="ew")
        row = ctk.CTkFrame(g.body, fg_color="transparent")
        row.grid(row=0, column=0, sticky="ew")
        row.grid_columnconfigure(0, weight=1)
        self.dir_entry = make_entry(row)
        self.dir_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.dir_entry.insert(0, self.form.output_dir)
        self.browse_btn = AeroButton(row, "Examinar…", self._on_browse, width=92)
        self.browse_btn.grid(row=0, column=1)
        self._form_widgets += [self.dir_entry, self.browse_btn]

    # ---- columna derecha: cola y registro --------------------------------------------------
    def _build_right(self, right: ctk.CTkFrame) -> None:
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(0, weight=3)
        right.grid_rowconfigure(1, weight=1)

        g = AeroGroup(right, "Cola de canciones")
        g.grid(row=0, column=0, sticky="nsew", pady=(0, 8))
        g.body.grid_rowconfigure(0, weight=1)
        g.body.grid_columnconfigure(0, weight=1)
        self.tree = ttk.Treeview(g.body, columns=("n", "song", "state"), show="headings", style="Aero.Treeview",
                                 selectmode="browse")
        for col, text, width, stretch in (("n", "#", 44, False), ("song", "Canción", 330, True), ("state", "Estado", 230, False)):
            self.tree.heading(col, text=text, anchor="w")
            self.tree.column(col, width=width, minwidth=40, stretch=stretch, anchor="w")
        for tag, color in ROW_COLORS.items():
            self.tree.tag_configure(tag, foreground=color)
        sb = ctk.CTkScrollbar(g.body, command=self.tree.yview, fg_color="transparent", button_color="#C3CAD6",
                              button_hover_color="#9FB0C8", width=14)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns", padx=(4, 0))
        self._empty_hint()

        g = AeroGroup(right, "Registro")
        g.grid(row=1, column=0, sticky="nsew")
        g.body.grid_rowconfigure(0, weight=1)
        self.log = ctk.CTkTextbox(g.body, height=96, fg_color="#FFFFFF", text_color=TEXT, border_color="#C9D0DC",
                                  border_width=1, corner_radius=2, font=ctk.CTkFont(family="Consolas", size=12),
                                  state="disabled", wrap="word")
        self.log.grid(row=0, column=0, sticky="nsew")
        self.log.tag_config("err", foreground=ERR_RED)
        self.log.tag_config("ok", foreground=OK_GREEN)
        self.log.tag_config("dim", foreground=TEXT_DIM)

    def _empty_hint(self) -> None:
        self.tree.insert("", "end", iid="hint", values=("", "Carga una playlist para ver aquí sus canciones.", ""), tags=("queued",))

    # ---- barra de acciones y de estado ------------------------------------------------------
    def _build_actions(self) -> None:
        bar = ctk.CTkFrame(self, fg_color=BG, corner_radius=0, border_width=0)
        bar.grid(row=2, column=0, sticky="ew", padx=12, pady=(2, 6))
        bar.grid_columnconfigure(0, weight=1)
        left = ctk.CTkFrame(bar, fg_color="transparent")
        left.grid(row=0, column=0, sticky="ew", padx=(0, 14))
        left.grid_columnconfigure(0, weight=1)
        self.now_label = ctk.CTkLabel(left, text="Listo. Carga una playlist para empezar.", text_color=TEXT,
                                      font=ui_font(13), anchor="w")
        self.now_label.grid(row=0, column=0, sticky="ew")
        self.count_label = ctk.CTkLabel(left, text="", text_color=TEXT_DIM, font=ui_font(12), anchor="e")
        self.count_label.grid(row=0, column=1, sticky="e")
        self.progress = AeroProgress(left, height=22)
        self.progress.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        btns = ctk.CTkFrame(bar, fg_color="transparent")
        btns.grid(row=0, column=1)
        self.start_btn = AeroButton(btns, "Iniciar conversión", self._on_start, width=150, height=32, primary=True)
        self.cancel_btn = AeroButton(btns, "Cancelar", self._on_cancel, width=90, height=32)
        self.open_btn = AeroButton(btns, "Abrir carpeta", self._on_open_folder, width=110, height=32)
        for i, b in enumerate((self.start_btn, self.cancel_btn, self.open_btn)):
            b.grid(row=0, column=i, padx=(0 if i == 0 else 8, 0))

    def _build_statusbar(self) -> None:
        bar = ctk.CTkFrame(self, fg_color=STATUS_BG, corner_radius=0, height=26)
        bar.grid(row=3, column=0, sticky="ew")
        bar.grid_columnconfigure(0, weight=1)
        ctk.CTkFrame(bar, height=1, fg_color="#C5CDDA", corner_radius=0).grid(row=0, column=0, columnspan=2, sticky="ew")
        self.status_label = ctk.CTkLabel(bar, text="Listo", text_color="#33415C", font=ui_font(12), anchor="w")
        self.status_label.grid(row=1, column=0, sticky="w", padx=12, pady=2)
        ctk.CTkLabel(bar, text="El audio de YouTube es ~128–160 kbps: la conversión no mejora la calidad original",
                     text_color=TEXT_DIM, font=ui_font(11), anchor="e").grid(row=1, column=1, sticky="e", padx=12)

    # =============================================================== lógica de interfaz
    def _read_form(self) -> FormState:
        norm = next((k for k, v in NORMALIZE_LABELS.items() if v == self.norm_var.get()), "loudnorm")
        return FormState(url=self.url_entry.get().strip(), output_dir=self.dir_entry.get().strip(),
                         output_format=self.fmt_var.get(), bitrate=self.bitrate_var.get(), normalize=norm,
                         create_folders=self.folders_var.get(), skip_existing=self.skip_var.get(),
                         workers=self.workers_var.get())

    def _update_format_dependent(self) -> None:
        wav = self.fmt_var.get() == OutputFormat.WAV.value
        self.bitrate_menu.configure(state="disabled" if wav else "normal")
        self.quality_hint.configure(text=(
            "Se guarda a 16 bits / 44,1 kHz estéreo, el formato que exigen los CD de audio." if wav else
            "Una tasa más alta no mejora el audio de origen; solo afecta al tamaño del archivo."))

    def _set_form_enabled(self, enabled: bool) -> None:
        for w in self._form_widgets:
            if hasattr(w, "set_enabled"):
                w.set_enabled(enabled)
            else:
                w.configure(state="normal" if enabled else "disabled")
        if enabled:
            self._update_format_dependent()
        else:
            self.bitrate_menu.configure(state="disabled")

    def _sync_buttons(self) -> None:
        loading = self.controller.busy and not self.running
        self.start_btn.set_enabled(bool(self.playlist and len(self.playlist)) and not self.running and not loading)
        self.cancel_btn.set_enabled(self.running)
        self.open_btn.set_enabled(bool(self.dir_entry.get().strip()))

    def _set_status(self, text: str) -> None:
        self.status_label.configure(text=text)

    def _log(self, text: str, tag: str | None = None) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", f"{datetime.now():%H:%M:%S}  {text}\n", tag) if tag else \
            self.log.insert("end", f"{datetime.now():%H:%M:%S}  {text}\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    # ---- acciones de usuario -------------------------------------------------------------------
    def _on_browse(self) -> None:
        chosen = filedialog.askdirectory(initialdir=self.dir_entry.get() or str(Path.home()), title="Carpeta de destino")
        if chosen:
            self.dir_entry.delete(0, "end")
            self.dir_entry.insert(0, str(Path(chosen)))
            self._sync_buttons()

    def _on_open_folder(self) -> None:
        folder = Path(self.dir_entry.get().strip())
        folder.mkdir(parents=True, exist_ok=True)
        try:
            if sys.platform == "win32":
                os.startfile(folder)                                     # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(folder)])
            else:
                subprocess.Popen(["xdg-open", str(folder)])
        except OSError as exc:
            messagebox.showerror(APP_TITLE, f"No se pudo abrir la carpeta:\n{exc}")

    def _on_load(self) -> None:
        url = self.url_entry.get().strip()
        if not url:
            self.info_label.configure(text="Pega primero el enlace de una playlist.", text_color=ERR_RED)
            return
        if self.running or not self.controller.load_playlist(url):
            return
        self.playlist = None
        self.load_btn.set_enabled(False)
        self.info_label.configure(text="Conectando con Spotify… (la primera vez se abrirá el navegador)", text_color=TEXT_DIM)
        self._set_status("Leyendo la playlist…")
        self._sync_buttons()

    def _on_start(self) -> None:
        if not self.playlist:
            return
        form = self._read_form()
        problems = form.validate()
        if problems:
            messagebox.showwarning(APP_TITLE, "\n".join(problems))
            return
        options = form.to_job_options()
        form.to_settings().save()
        if not self.controller.start(self.playlist, options):
            return
        self.running = True
        self.tracker = ProgressTracker(len(self.playlist))
        for i in range(len(self.playlist)):
            self._set_row(i, QUEUED)
        self._set_form_enabled(False)
        self.progress.set(0.0, shine=True)
        self.now_label.configure(text="Iniciando…")
        self.count_label.configure(text=self.tracker.label)
        self._set_status("Convirtiendo…")
        self._log(f"Iniciando «{self.playlist.name}» ({len(self.playlist)} canciones, {options.output_format.value.upper()})", "dim")
        self._sync_buttons()

    def _on_cancel(self) -> None:
        self.controller.cancel()
        self.cancel_btn.set_enabled(False)
        self.now_label.configure(text="Cancelando… terminando la operación en curso")
        self._set_status("Cancelando…")

    def _on_close(self) -> None:
        if self.running and not messagebox.askyesno(APP_TITLE, "Hay una conversión en curso. ¿Cancelar y salir?"):
            return
        try:
            self._read_form().to_settings().save()
        except OSError:
            pass
        self.controller.shutdown()
        self.destroy()

    # ---- cola de eventos ---------------------------------------------------------------------------
    def _poll(self) -> None:
        for kind, payload in self.controller.drain():
            handler = {LOAD_PROGRESS: self._h_load_progress, LOADED: self._h_loaded, LOAD_ERROR: self._h_load_error,
                       EVENT: self._h_event, JOB_DONE: self._h_job_done, JOB_ERROR: self._h_job_error}[kind]
            handler(payload)
        if self.running and self.tracker:
            self._phase += 0.03
            self.progress.set(self.tracker.fraction, shine=True, phase=self._phase)
            self.count_label.configure(text=f"{self.tracker.label}   ·   {self.tracker.fraction:.0%}")
        self.after(60, self._poll)

    def _h_load_progress(self, payload) -> None:
        done, total = payload
        self.info_label.configure(text=f"Leyendo canciones… {done}/{total}", text_color=TEXT_DIM)

    def _h_loaded(self, playlist: Playlist) -> None:
        self.playlist = playlist
        self.tree.delete(*self.tree.get_children())
        for i, t in enumerate(playlist.tracks):
            self.tree.insert("", "end", iid=str(i), values=(i + 1, f"{t.artist_display} — {t.title}", QUEUED.text), tags=("queued",))
        extra = f" ({len(playlist.skipped)} omitidas: locales o podcasts)" if playlist.skipped else ""
        self.info_label.configure(text=f"«{playlist.name}» de {playlist.owner}\n{len(playlist)} canciones{extra}", text_color=OK_GREEN)
        self.load_btn.set_enabled(True)
        self.progress.set(0.0)
        self.now_label.configure(text="Playlist cargada. Revisa las opciones y pulsa «Iniciar conversión».")
        self.count_label.configure(text="")
        self._set_status(f"{len(playlist)} canciones listas")
        self._log(f"Playlist cargada: «{playlist.name}», {len(playlist)} canciones", "dim")
        self._sync_buttons()

    def _h_load_error(self, message: str) -> None:
        self.info_label.configure(text=message, text_color=ERR_RED)
        self.load_btn.set_enabled(True)
        self._set_status("Error al cargar la playlist")
        self._log(f"ERROR: {message}", "err")
        self._sync_buttons()

    def _set_row(self, index: int, state) -> None:
        iid = str(index)
        if self.tree.exists(iid):
            self.tree.set(iid, "state", state.text)
            self.tree.item(iid, tags=(state.tag,))

    def _h_event(self, ev) -> None:
        if isinstance(ev, TrackStarted):
            self._set_row(ev.index, ACTIVE)
            self.now_label.configure(text=f"{ev.track}")
            if self.tree.exists(str(ev.index)):
                self.tree.see(str(ev.index))
        elif isinstance(ev, TrackProgress):
            if self.tracker:
                self.tracker.on_progress(ev)
            self._set_row(ev.index, row_for_progress(ev))
            self.now_label.configure(text=f"{ev.stage.value}: {ev.track}")
        elif isinstance(ev, TrackFinished):
            if self.tracker:
                self.tracker.on_finished(ev)
            self._set_row(ev.index, row_for_result(ev.result))
            r = ev.result
            if r.status is TrackStatus.FAILED:
                self._log(f"ERROR  {r.track}: {r.error}", "err")
            elif r.status is TrackStatus.OK:
                self._log(f"OK     {r.track}", "ok")
            elif r.status is TrackStatus.SKIPPED:
                self._log(f"Omitida  {r.track}", "dim")
        elif isinstance(ev, JobStarted):
            self._set_status(f"Convirtiendo «{ev.playlist_name}»…")

    def _finish_job(self) -> None:
        self.running = False
        self._set_form_enabled(True)
        self.progress.set(self.tracker.fraction if self.tracker else 0.0, shine=False)
        self._sync_buttons()

    def _h_job_done(self, summary) -> None:
        self._finish_job()
        if self.tracker and not summary.cancelled:
            self.progress.set(1.0 if not summary.failed else self.tracker.fraction)
        self.now_label.configure(text="Cancelado." if summary.cancelled else "Proceso terminado.")
        self.count_label.configure(text="")
        self._set_status(str(summary))
        self._log(f"Resumen: {summary}", "dim")
        if summary.cancelled:
            return
        text = f"{summary}."
        if summary.failed:
            text += "\n\nLas canciones fallidas están en failed_tracks.txt dentro de la carpeta de destino.\nPulsa «Iniciar conversión» de nuevo para reintentarlas."
            messagebox.showwarning(APP_TITLE, text)
        else:
            messagebox.showinfo(APP_TITLE, "¡Listo!\n\n" + text)

    def _h_job_error(self, message: str) -> None:
        self._finish_job()
        self.now_label.configure(text="No se pudo iniciar la conversión.")
        self._set_status("Error")
        self._log(f"ERROR: {message}", "err")
        messagebox.showerror(APP_TITLE, message)


def run_gui() -> None:
    if sys.platform == "win32":
        try:                                       # el icono propio en la barra de tareas
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Spotify2Audio.App")
        except Exception:  # noqa: BLE001
            pass
    from ..utils.logging_setup import setup_logging
    setup_logging()
    App().mainloop()
