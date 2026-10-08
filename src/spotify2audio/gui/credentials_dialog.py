"""Diálogo para guardar el Client ID / Secret de Spotify (imprescindible en el .exe, que no tiene .env)."""
from __future__ import annotations

import re
import tkinter as tk
import webbrowser
from tkinter import messagebox
from typing import Callable

import customtkinter as ctk

from ..config.credentials import save_credentials
from ..services.spotify_client import DEFAULT_REDIRECT_URI
from .aero import BG, HEADING, TEXT, TEXT_DIM, AeroButton, AeroGroup, make_entry, ui_font

DASHBOARD_URL = "https://developer.spotify.com/dashboard"
_ID_RE = re.compile(r"[0-9a-fA-F]{32}")


class CredentialsDialog(ctk.CTkToplevel):
    def __init__(self, master, on_saved: Callable[[], None] | None = None, reason: str | None = None,
                 saver: Callable[[str, str], str] = save_credentials) -> None:
        super().__init__(master)
        self.title("Credenciales de Spotify")
        self.configure(fg_color=BG)
        self.resizable(False, False)
        self.transient(master)
        self._on_saved, self._saver = on_saved, saver
        self.grid_columnconfigure(0, weight=1)

        g = AeroGroup(self, "Conecta tu cuenta de Spotify")
        g.grid(row=0, column=0, sticky="nsew", padx=12, pady=(12, 6))
        b = g.body
        intro = reason + "\n\n" if reason else ""
        ctk.CTkLabel(b, text=intro + "Spotify exige que cada app tenga sus propias claves (gratis, pero la cuenta debe ser Premium):",
                     text_color=TEXT, font=ui_font(13), wraplength=470, justify="left", anchor="w"
                     ).grid(row=0, column=0, sticky="w")
        steps = ("1.  Entra en el Dashboard de Spotify for Developers y crea una app.\n"
                 "2.  En «Redirect URIs» añade exactamente la dirección de abajo.\n"
                 "3.  En «User Management» añade el correo de tu cuenta de Spotify.\n"
                 "4.  Copia aquí el Client ID y el Client Secret de la app.")
        ctk.CTkLabel(b, text=steps, text_color=TEXT_DIM, font=ui_font(12), wraplength=470, justify="left", anchor="w"
                     ).grid(row=1, column=0, sticky="w", pady=(8, 6))
        row = ctk.CTkFrame(b, fg_color="transparent")
        row.grid(row=2, column=0, sticky="ew")
        row.grid_columnconfigure(0, weight=1)
        self.uri_entry = make_entry(row)
        self.uri_entry.insert(0, DEFAULT_REDIRECT_URI)
        self.uri_entry.configure(state="readonly")
        self.uri_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        AeroButton(row, "Copiar", self._copy_uri, width=70).grid(row=0, column=1)

        ctk.CTkLabel(b, text="Client ID", text_color=HEADING, font=ui_font(13), anchor="w").grid(row=3, column=0, sticky="w", pady=(12, 2))
        self.id_entry = make_entry(b)
        self.id_entry.grid(row=4, column=0, sticky="ew")
        ctk.CTkLabel(b, text="Client Secret", text_color=HEADING, font=ui_font(13), anchor="w").grid(row=5, column=0, sticky="w", pady=(8, 2))
        self.secret_entry = make_entry(b, show="•")
        self.secret_entry.grid(row=6, column=0, sticky="ew")

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.grid(row=1, column=0, sticky="e", padx=12, pady=(4, 12))
        AeroButton(btns, "Abrir el Dashboard", lambda: webbrowser.open(DASHBOARD_URL), width=140, height=30).grid(row=0, column=0, padx=(0, 8))
        self.save_btn = AeroButton(btns, "Guardar", self._save, width=90, height=30, primary=True)
        self.save_btn.grid(row=0, column=1, padx=(0, 8))
        AeroButton(btns, "Cancelar", self.destroy, width=90, height=30).grid(row=0, column=2)

        self.bind("<Escape>", lambda _e: self.destroy())
        self.id_entry.bind("<Return>", lambda _e: self.secret_entry.focus_set())
        self.secret_entry.bind("<Return>", lambda _e: self._save())
        self.update_idletasks()
        w, h = 520, self.winfo_reqheight()
        x = master.winfo_rootx() + max((master.winfo_width() - w) // 2, 0)
        y = master.winfo_rooty() + max((master.winfo_height() - h) // 3, 0)
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.after(200, self._grab)

    def _grab(self) -> None:
        try:
            self.grab_set()
            self.id_entry.focus_set()
        except tk.TclError:
            pass

    def _copy_uri(self) -> None:
        self.clipboard_clear()
        self.clipboard_append(DEFAULT_REDIRECT_URI)

    def _save(self) -> None:
        cid, secret = self.id_entry.get().strip(), self.secret_entry.get().strip()
        if not cid or not secret:
            messagebox.showwarning("Credenciales de Spotify", "Rellena el Client ID y el Client Secret.", parent=self)
            return
        if not (_ID_RE.fullmatch(cid) and _ID_RE.fullmatch(secret)) and not messagebox.askyesno(
                "Credenciales de Spotify", "Las claves de Spotify suelen tener 32 caracteres (letras y números).\n"
                "Las que has escrito no lo parecen. ¿Guardarlas igualmente?", parent=self):
            return
        try:
            where = self._saver(cid, secret)
        except OSError as exc:
            messagebox.showerror("Credenciales de Spotify", f"No se pudieron guardar:\n{exc}", parent=self)
            return
        messagebox.showinfo("Credenciales de Spotify", f"Guardadas en {where}.", parent=self)
        self.destroy()
        if self._on_saved:
            self._on_saved()
