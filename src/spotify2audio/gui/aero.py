"""Widgets con estética Windows Vista / 7 (Aero): cristal, brillos, degradados y barra verde.

Todo se dibuja con Pillow (a doble resolución) y se muestra mediante CTkImage, que se encarga
del escalado DPI. Así el aspecto es idéntico en cualquier monitor y no depende del tema de Windows 11.
"""
from __future__ import annotations

import math
import sys
import tkinter as tk
from functools import lru_cache
from tkinter import ttk

import customtkinter as ctk
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

SS = 2                      # factor de resolución de las imágenes (nitidez en pantallas HiDPI)

# ---- paleta -----------------------------------------------------------------------------------
BG = "#F0F0F0"              # fondo de ventana (gris de diálogo clásico)
PANEL = "#FFFFFF"
PANEL_BORDER = "#AEB8C8"
LINE = "#D5DCE8"
TEXT = "#1B1B1B"
TEXT_DIM = "#6B7280"
HEADING = "#003399"         # azul de los títulos de sección de Vista
ENTRY_BORDER = "#8C93A0"
STATUS_BG = "#E6EBF3"
OK_GREEN, ERR_RED, ACTIVE_BLUE = "#1E7A1E", "#B3261E", "#003399"

UI_FAMILY = "Segoe UI"


def ui_font(size: int = 13, weight: str = "normal") -> ctk.CTkFont:
    return ctk.CTkFont(family=UI_FAMILY, size=size, weight=weight)


# ---- utilidades de dibujo -----------------------------------------------------------------------
def _rgba(c) -> tuple[int, int, int, int]:
    return (*c[:3], c[3] if len(c) > 3 else 255)


def _lerp(a, b, t: float):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(4))


def _color_at(stops, t: float):
    stops = [(p, _rgba(c)) for p, c in stops]
    for (p0, c0), (p1, c1) in zip(stops, stops[1:]):
        if t <= p1:
            return c1 if p1 == p0 else _lerp(c0, c1, max(0.0, (t - p0) / (p1 - p0)))
    return stops[-1][1]


def vgradient(w: int, h: int, stops) -> Image.Image:
    col = Image.new("RGBA", (1, max(h, 1)))
    for y in range(max(h, 1)):
        col.putpixel((0, y), _color_at(stops, y / max(h - 1, 1)))
    return col.resize((max(w, 1), max(h, 1)), Image.NEAREST)


def _rr_mask(w: int, h: int, inset: int, radius: int) -> Image.Image:
    k = 4
    m = Image.new("L", (w * k, h * k), 0)
    ImageDraw.Draw(m).rounded_rectangle(
        [inset * k, inset * k, (w - inset) * k - 1, (h - inset) * k - 1], radius=max(radius, 0) * k, fill=255)
    return m.resize((w, h), Image.LANCZOS)


def _load_font(px: int, light: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    names = (["segoeuil.ttf", "SegoeUI-Light.ttf"] if light else []) + ["segoeui.ttf", "DejaVuSans.ttf"]
    for name in names:
        try:
            return ImageFont.truetype(name, px)
        except OSError:
            continue
    return ImageFont.load_default(px)


# ---- botones ---------------------------------------------------------------------------------
_BTN = {
    "normal":   dict(border=(112, 112, 112), top=((242, 242, 242), (235, 235, 235)), bot=((221, 221, 221), (207, 207, 207))),
    "primary":  dict(border=(60, 127, 177),  top=((240, 248, 253), (226, 241, 251)), bot=((196, 226, 246), (160, 205, 236))),
    "hover":    dict(border=(60, 127, 177),  top=((234, 246, 253), (217, 240, 252)), bot=((190, 230, 253), (167, 217, 245))),
    "pressed":  dict(border=(44, 98, 139),   top=((194, 228, 246), (173, 219, 243)), bot=((145, 205, 238), (104, 179, 219))),
    "disabled": dict(border=(173, 178, 181), top=((244, 244, 244), (244, 244, 244)), bot=((244, 244, 244), (244, 244, 244))),
}


@lru_cache(maxsize=256)
def make_button_image(w: int, h: int, state: str = "normal", primary: bool = False) -> Image.Image:
    W, H, r = w * SS, h * SS, 3 * SS
    p = _BTN["primary" if (primary and state == "normal") else state]
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    img.paste(Image.new("RGBA", (W, H), (*p["border"], 255)), (0, 0), _rr_mask(W, H, 0, r))
    stops = [(0, p["top"][0]), (0.499, p["top"][1]), (0.5, p["bot"][0]), (1, p["bot"][1])]
    inner = _rr_mask(W, H, SS, r - SS)
    img.paste(vgradient(W, H, stops), (0, 0), inner)
    if state != "disabled":                                   # filete blanco interior (brillo Aero)
        rim = ImageChops.subtract(inner, _rr_mask(W, H, 2 * SS, max(r - 2 * SS, 0)))
        img.paste(Image.new("RGBA", (W, H), (255, 255, 255, 150)), (0, 0), rim)
    return img


def _pointer_inside(widget: tk.Misc, event) -> bool:
    x, y = widget.winfo_rootx(), widget.winfo_rooty()
    return x <= event.x_root < x + widget.winfo_width() and y <= event.y_root < y + widget.winfo_height()


class AeroButton(ctk.CTkLabel):
    """Botón con degradado y brillo estilo Vista/7: normal, hover (azul cielo), pulsado y desactivado."""

    def __init__(self, master, text: str, command=None, width: int = 110, height: int = 28,
                 primary: bool = False, font: ctk.CTkFont | None = None) -> None:
        self._ae_imgs = {s: ctk.CTkImage(make_button_image(width, height, s, primary), size=(width, height))
                      for s in ("normal", "hover", "pressed", "disabled")}
        super().__init__(master, text=text, image=self._ae_imgs["normal"], compound="center", width=width,
                         height=height, fg_color="transparent", text_color=TEXT, corner_radius=0,
                         font=font or ui_font(13))
        self._ae_command, self._ae_enabled, self._ae_inside, self._ae_down = command, True, False, False
        for seq, fn in (("<Enter>", self._ae_motion), ("<Motion>", self._ae_motion), ("<Leave>", self._ae_motion),
                        ("<ButtonPress-1>", self._ae_press), ("<ButtonRelease-1>", self._ae_release)):
            self.bind(seq, fn)

    def set_enabled(self, enabled: bool) -> None:
        self._ae_enabled = enabled
        self._ae_down = self._ae_inside = False
        self._ae_refresh()

    def set_command(self, command) -> None:
        self._ae_command = command

    def _ae_refresh(self) -> None:
        if not self._ae_enabled:
            state, color = "disabled", "#8D8D8D"
        elif self._ae_down and self._ae_inside:
            state, color = "pressed", TEXT
        elif self._ae_inside:
            state, color = "hover", TEXT
        else:
            state, color = "normal", TEXT
        self.configure(image=self._ae_imgs[state], text_color=color)

    def _ae_motion(self, event) -> None:
        inside = self._ae_enabled and _pointer_inside(self, event)      # por coordenadas: sin parpadeos
        if inside != self._ae_inside:
            self._ae_inside = inside
            self._ae_refresh()

    def _ae_press(self, _event) -> None:
        if self._ae_enabled:
            self._ae_down = True
            self._ae_refresh()

    def _ae_release(self, event) -> None:
        fire = self._ae_enabled and self._ae_down and _pointer_inside(self, event)
        self._ae_down = False
        self._ae_refresh()
        if fire and self._ae_command:
            self._ae_command()


# ---- radios y casillas ----------------------------------------------------------------------------
_TOGGLE = {
    "normal":   ((141, 142, 143), (255, 255, 255), (222, 222, 222)),
    "hover":    ((60, 127, 177),  (236, 247, 254), (190, 226, 250)),
    "pressed":  ((44, 98, 139),   (200, 230, 248), (150, 205, 240)),
    "disabled": ((188, 188, 188), (245, 245, 245), (235, 235, 235)),
}


@lru_cache(maxsize=64)
def make_toggle_image(kind: str, checked: bool, state: str, d: int = 14, gap: int = 8, h: int = 18) -> Image.Image:
    K = 4
    W, H, D = (d + gap) * SS * K, h * SS * K, d * SS * K
    oy, one = (H - D) // 2, SS * K
    border, top, bot = _TOGGLE[state]

    def shape(inset: int) -> Image.Image:
        m = Image.new("L", (D, D), 0)
        box = [inset, inset, D - 1 - inset, D - 1 - inset]
        dr = ImageDraw.Draw(m)
        (dr.ellipse if kind == "radio" else lambda b, fill: dr.rounded_rectangle(b, radius=2 * one, fill=fill))(box, fill=255)
        return m

    tile = Image.new("RGBA", (D, D), (0, 0, 0, 0))
    tile.paste(Image.new("RGBA", (D, D), (*border, 255)), (0, 0), shape(0))
    tile.paste(vgradient(D, D, [(0, top), (1, bot)]), (0, 0), shape(one))
    if checked and state != "disabled":
        dr = ImageDraw.Draw(tile)
        navy = (25, 75, 140, 255)
        if kind == "radio":
            pad = int(D * 0.30)
            dr.ellipse([pad, pad, D - 1 - pad, D - 1 - pad], fill=navy, outline=(70, 125, 190, 255), width=one)
        else:
            pts = [(D * 0.22, D * 0.52), (D * 0.42, D * 0.74), (D * 0.80, D * 0.26)]
            dr.line(pts, fill=navy, width=int(2.4 * one), joint="curve")
    elif checked:
        dr = ImageDraw.Draw(tile)
        if kind == "radio":
            pad = int(D * 0.32)
            dr.ellipse([pad, pad, D - 1 - pad, D - 1 - pad], fill=(170, 170, 170, 255))
        else:
            dr.line([(D * 0.22, D * 0.52), (D * 0.42, D * 0.74), (D * 0.80, D * 0.26)], fill=(170, 170, 170, 255),
                    width=int(2.4 * one), joint="curve")
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    canvas.paste(tile, (0, oy))
    return canvas.resize(((d + gap) * SS, h * SS), Image.LANCZOS)


class AeroToggle(ctk.CTkLabel):
    """Radio o casilla estilo Vista. `variable` es un StringVar (radio, con `value`) o BooleanVar (casilla)."""

    def __init__(self, master, text: str, kind: str = "radio", variable: tk.Variable | None = None,
                 value: str | None = None, command=None) -> None:
        self.kind, self.variable, self.value, self._ae_command = kind, variable, value, command
        self._ae_enabled, self._ae_inside, self._ae_down = True, False, False
        super().__init__(master, text=text, image=self._ae_image("normal"), compound="left", anchor="w",
                         fg_color="transparent", text_color=TEXT, font=ui_font(13), corner_radius=0)
        for seq, fn in (("<Enter>", self._ae_motion), ("<Motion>", self._ae_motion), ("<Leave>", self._ae_motion),
                        ("<ButtonPress-1>", self._ae_press), ("<ButtonRelease-1>", self._ae_release)):
            self.bind(seq, fn)
        if variable is not None:
            variable.trace_add("write", lambda *_: self._ae_refresh())

    @property
    def checked(self) -> bool:
        if self.variable is None:
            return False
        return self.variable.get() == self.value if self.kind == "radio" else bool(self.variable.get())

    def _ae_image(self, state: str) -> ctk.CTkImage:
        return ctk.CTkImage(make_toggle_image(self.kind, self.checked, state), size=(22, 18))

    def set_enabled(self, enabled: bool) -> None:
        self._ae_enabled = enabled
        self._ae_inside = self._ae_down = False
        self._ae_refresh()

    def _ae_refresh(self) -> None:
        state = ("disabled" if not self._ae_enabled else "pressed" if self._ae_down and self._ae_inside
                 else "hover" if self._ae_inside else "normal")
        self.configure(image=self._ae_image(state), text_color=TEXT if self._ae_enabled else "#8D8D8D")

    def _ae_motion(self, event) -> None:
        inside = self._ae_enabled and _pointer_inside(self, event)
        if inside != self._ae_inside:
            self._ae_inside = inside
            self._ae_refresh()

    def _ae_press(self, _e) -> None:
        if self._ae_enabled:
            self._ae_down = True
            self._ae_refresh()

    def _ae_release(self, event) -> None:
        fire = self._ae_enabled and self._ae_down and _pointer_inside(self, event)
        self._ae_down = False
        if fire and self.variable is not None:
            if self.kind == "radio":
                self.variable.set(self.value)
            else:
                self.variable.set(not self.variable.get())
            if self._ae_command:
                self._ae_command()
        self._ae_refresh()


# ---- barra de progreso verde --------------------------------------------------------------------
def make_progress_image(w: int, h: int, fraction: float, phase: float = 0.0, shine: bool = False) -> Image.Image:
    W, H, r = w * SS, h * SS, 4 * SS
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    img.paste(Image.new("RGBA", (W, H), (150, 154, 160, 255)), (0, 0), _rr_mask(W, H, 0, r))
    track = vgradient(W, H, [(0, (205, 208, 212)), (0.2, (232, 234, 237)), (1, (248, 249, 250))])
    img.paste(track, (0, 0), _rr_mask(W, H, SS, r - SS))
    fw = int((W - 2 * SS) * max(0.0, min(1.0, fraction)))
    if fw > 3 * SS:
        fh = H - 2 * SS
        img.paste(Image.new("RGBA", (fw, fh), (38, 136, 18, 255)), (SS, SS), _rr_mask(fw, fh, 0, r - SS))
        iw, ih = fw - 2 * SS, fh - 2 * SS
        fill = vgradient(iw, ih, [(0, (196, 247, 178)), (0.48, (118, 224, 90)), (0.5, (44, 186, 18)), (1, (104, 220, 70))])
        if shine:                                                   # destello que recorre la barra
            bw = 90 * SS
            band = Image.new("RGBA", (bw, 1))
            for x in range(bw):
                band.putpixel((x, 0), (255, 255, 255, int(120 * math.sin(math.pi * x / bw))))
            band = band.resize((bw, ih), Image.NEAREST)
            layer = Image.new("RGBA", (iw + 2 * bw, ih), (0, 0, 0, 0))
            layer.paste(band, (int(phase * (iw + bw)), 0))
            fill = Image.alpha_composite(fill, layer.crop((bw, 0, bw + iw, ih)))
        img.paste(fill, (2 * SS, 2 * SS), _rr_mask(iw, ih, 0, max(r - 2 * SS, 0)))
        gloss = ImageChops.subtract(_rr_mask(iw, ih, 0, max(r - 2 * SS, 0)), _rr_mask(iw, ih, SS, max(r - 3 * SS, 0)))
        img.paste(Image.new("RGBA", (iw, ih), (255, 255, 255, 90)), (2 * SS, 2 * SS), gloss)
    return img


class AeroProgress(ctk.CTkLabel):
    """Barra de progreso verde con brillo, como la de Windows Vista/7."""

    def __init__(self, master, height: int = 22) -> None:
        super().__init__(master, text="", height=height, fg_color="transparent")
        self._ae_h, self._ae_w, self._ae_fraction, self._ae_phase, self._ae_shine = height, 0, 0.0, 0.0, False
        self.bind("<Configure>", self._ae_on_resize)

    def _ae_scaling(self) -> float:
        return getattr(self, "_get_widget_scaling", lambda: 1.0)()

    def _ae_on_resize(self, event) -> None:
        w = max(int(event.width / self._ae_scaling()), 40)
        if w != self._ae_w:
            self._ae_w = w
            self._ae_draw()

    def set(self, fraction: float, shine: bool = False, phase: float | None = None) -> None:
        if phase is not None:
            self._ae_phase = phase % 1.0
        self._ae_fraction, self._ae_shine = fraction, shine
        self._ae_draw()

    def _ae_draw(self) -> None:
        if self._ae_w:
            img = make_progress_image(self._ae_w, self._ae_h, self._ae_fraction, self._ae_phase, self._ae_shine)
            self.configure(image=ctk.CTkImage(img, size=(self._ae_w, self._ae_h)))


# ---- cabecera de cristal ----------------------------------------------------------------------
def make_cd_logo(px: int) -> Image.Image:
    S = px * 4
    c = S / 2
    disc = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(disc)
    for i in range(int(c), 0, -2):                                   # degradado radial plateado
        t = (i / c) ** 1.4
        d.ellipse([c - i, c - i, c + i, c + i], fill=(*_lerp((255, 255, 255, 255), (170, 184, 205, 255), t)[:3], 255))
    sheen = Image.new("RGBA", (S, S), (0, 0, 0, 0))                  # reflejos de arcoíris del CD
    sd = ImageDraw.Draw(sheen)
    for a0, a1, col in ((15, 55, (80, 200, 255, 130)), (55, 85, (255, 90, 200, 110)), (195, 235, (255, 230, 90, 120)),
                        (235, 265, (120, 255, 170, 110)), (100, 130, (255, 255, 255, 120))):
        sd.pieslice([0, 0, S - 1, S - 1], a0, a1, fill=col)
    sheen = sheen.filter(ImageFilter.GaussianBlur(S * 0.02))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, S - 1, S - 1], fill=255)
    disc = Image.alpha_composite(disc, Image.composite(sheen, Image.new("RGBA", (S, S), (0, 0, 0, 0)), mask))
    d = ImageDraw.Draw(disc)
    d.ellipse([0, 0, S - 1, S - 1], outline=(110, 128, 156, 255), width=max(S // 60, 2))
    r2 = S * 0.27                                                    # anillo interior
    d.ellipse([c - r2, c - r2, c + r2, c + r2], outline=(235, 240, 248, 255), width=max(S // 50, 2))
    hole = Image.new("L", (S, S), 0)
    hr = S * 0.095
    ImageDraw.Draw(hole).ellipse([c - hr, c - hr, c + hr, c + hr], fill=255)
    disc.paste(Image.new("RGBA", (S, S), (0, 0, 0, 0)), (0, 0), hole)
    d.ellipse([c - hr, c - hr, c + hr, c + hr], outline=(110, 128, 156, 255), width=max(S // 80, 1))
    return disc.resize((px, px), Image.LANCZOS)


def _glow_text(img: Image.Image, xy, text: str, font, fill, glow=(255, 255, 255)) -> None:
    layer = Image.new("L", img.size, 0)
    ImageDraw.Draw(layer).text(xy, text, font=font, fill=255)
    halo = layer.filter(ImageFilter.GaussianBlur(4 * SS)).point(lambda v: min(255, v * 3))
    img.paste(Image.new("RGBA", img.size, (*glow, 255)), (0, 0), halo)
    ImageDraw.Draw(img).text(xy, text, font=font, fill=fill)


@lru_cache(maxsize=8)
def make_header_image(w: int, h: int, title: str, subtitle: str) -> Image.Image:
    W, H = w * SS, h * SS
    img = vgradient(W, H, [(0, (219, 234, 250)), (0.5, (178, 207, 238)), (1, (146, 183, 226))])
    sheen = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(sheen).polygon([(0, 0), (int(W * 0.58), 0), (int(W * 0.30), H), (0, H)], fill=(255, 255, 255, 72))
    img = Image.alpha_composite(img, sheen)
    img = Image.alpha_composite(img, Image.new("RGBA", (W, H), (0, 0, 0, 0)))
    gloss = Image.new("RGBA", (W, H // 2), (255, 255, 255, 40))
    img.alpha_composite(gloss, (0, 0))
    d = ImageDraw.Draw(img)
    d.line([(0, H - 1), (W, H - 1)], fill=(104, 142, 194, 255), width=SS)
    d.line([(0, H - 1 - SS), (W, H - 1 - SS)], fill=(238, 245, 253, 255), width=SS)
    logo_px = int(H * 0.72)
    logo = make_cd_logo(logo_px)
    lx, ly = 18 * SS, (H - logo_px) // 2
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    shadow.paste((20, 40, 80, 120), (lx + 3 * SS, ly + 4 * SS), logo.split()[3])
    img = Image.alpha_composite(img, shadow.filter(ImageFilter.GaussianBlur(3 * SS)))
    img.alpha_composite(logo, (lx, ly))
    tx = lx + logo_px + 16 * SS
    f_title, f_sub = _load_font(30 * SS, light=True), _load_font(13 * SS)
    _glow_text(img, (tx, int(H * 0.17)), title, f_title, (16, 32, 64))
    _glow_text(img, (tx + 2 * SS, int(H * 0.60)), subtitle, f_sub, (38, 62, 104))
    return img


def make_app_icon(path) -> bool:
    try:
        make_cd_logo(256).save(path, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
        return True
    except OSError:
        return False


# ---- contenedores ------------------------------------------------------------------------------
class AeroGroup(ctk.CTkFrame):
    """Sección blanca con título azul y filete, como los paneles de Panel de control de Vista."""

    def __init__(self, master, title: str) -> None:
        super().__init__(master, fg_color=PANEL, border_color=PANEL_BORDER, border_width=1, corner_radius=3)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=12, pady=(8, 2))
        head.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(head, text=title, text_color=HEADING, font=ui_font(14)).grid(row=0, column=0)
        ctk.CTkFrame(head, height=1, fg_color=LINE, corner_radius=0).grid(row=0, column=1, sticky="ew", padx=(10, 0), pady=(4, 0))
        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.grid(row=1, column=0, sticky="nsew", padx=12, pady=(2, 10))
        self.body.grid_columnconfigure(0, weight=1)


def make_entry(master, **kw) -> ctk.CTkEntry:
    return ctk.CTkEntry(master, fg_color="#FFFFFF", border_color=ENTRY_BORDER, border_width=1, corner_radius=2,
                        text_color=TEXT, placeholder_text_color="#9AA0AA", height=28, font=ui_font(13), **kw)


def make_menu(master, values, variable, command=None, width: int = 150) -> ctk.CTkOptionMenu:
    return ctk.CTkOptionMenu(master, values=values, variable=variable, command=command, width=width, height=26,
                             corner_radius=2, fg_color="#FAFBFD", button_color="#D6DFEC", button_hover_color="#B9D3EF",
                             text_color=TEXT, dropdown_fg_color="#FFFFFF", dropdown_text_color=TEXT,
                             dropdown_hover_color="#CDE8FF", font=ui_font(13), dropdown_font=ui_font(13))


def style_treeview(root: tk.Misc, scaling: float = 1.0) -> None:
    style = ttk.Style(root)
    style.theme_use("vista" if "vista" in style.theme_names() else "clam")
    style.configure("Aero.Treeview", background="#FFFFFF", fieldbackground="#FFFFFF", foreground=TEXT,
                    rowheight=int(24 * scaling), borderwidth=0, font=(UI_FAMILY, 10))
    style.configure("Aero.Treeview.Heading", font=(UI_FAMILY, 10), padding=(6, 3))
    style.map("Aero.Treeview", background=[("selected", "#CDE8FF")], foreground=[("selected", TEXT)])
