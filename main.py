"""
PDF Dark Mode Converter
-----------------------
Standalone desktop app. No Node, no Rust, no Electron.
Requires: pip install pymupdf

Run:  python converter.py
Build: pyinstaller --onefile --windowed --name "PDF-Dark-Converter" converter.py
"""

import fitz  # PyMuPDF
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
import platform
import ctypes
import sys

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

# ── HiDPI / display-scaling awareness (Windows only) ───────────────────────────
# Must be called before any Tk window is created.
if sys.platform == "win32":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()   # fallback for older Windows
        except Exception:
            pass


# ── Theme definitions ──────────────────────────────────────────────────────────
# Each value is the (R, G, B) background color.
# The pixel algorithm maps brightness → this bg color (dark) to white (bright).
THEMES = {
    "Classic Inversion": (0,   0,   0),
    "Claude Warm":       (42,  37,  34),
    "ChatGPT Cool":      (52,  53,  65),
    "Sepia Dark":        (40,  35,  25),
    "Midnight Blue":     (25,  30,  45),
    "Forest Green":      (25,  35,  30),
}




# ── PDF processing ─────────────────────────────────────────────────────────────

def convert_pdf(
    input_path: Path,
    output_path: Path,
    theme_name: str,
    dpi: int,
    preserve_text: bool,
    jpeg_quality: int,
    searchable: bool,
    progress_cb,
    done_cb,
    error_cb,
) -> None:
    """
    Convert a PDF to dark mode using blend mode annotation overlay.

    Adds two annotation rectangles per page:
      1. White fill + Difference blend  → mathematically inverts all colors
      2. Theme fill + Screen blend      → tints result to the selected theme

    Result: native vector quality, full text search, ~same file size as input,
    ~3ms per page (vs minutes for rasterization).
    TOC/bookmarks are preserved automatically (document modified in-place).
    """
    import time
    import traceback
    import tempfile
    import shutil
    from collections import deque

    try:
        if Path(input_path).resolve() == Path(output_path).resolve():
            raise ValueError("Output path must be different from input path.")

        doc      = fitz.open(str(input_path))
        total    = doc.page_count
        bg_color = THEMES.get(theme_name, (52, 53, 65))
        R, G, B  = bg_color
        r, g, b  = R / 255.0, G / 255.0, B / 255.0

        page_times = deque(maxlen=10)

        for i, page in enumerate(doc):
            t0 = time.perf_counter()

            # PDF annotation flags: Print(4) | ReadOnly(64) | Locked(128) = 196
            # Print  → annotation renders in viewers/print (keeps the dark mode effect)
            # ReadOnly + Locked → suppresses editing UI, tooltips, and annotation
            #                     panel entries in Sumatra and other strict viewers
            _ANNOT_FLAGS = 4 | 64 | 128  # 196

            # Layer 1: Difference(white) — inverts all colors
            # white bg (255) → black (0), black text (0) → white (255)
            a1 = page.add_rect_annot(page.rect)
            a1.set_colors(stroke=None, fill=(1.0, 1.0, 1.0))
            a1.set_opacity(1.0)
            a1.set_blendmode("Difference")
            a1.set_flags(_ANNOT_FLAGS)
            a1.update()

            # Layer 2: Screen(theme) — tints inverted result to theme background
            # black background → theme color, white text → stays near white
            a2 = page.add_rect_annot(page.rect)
            a2.set_colors(stroke=None, fill=(r, g, b))
            a2.set_opacity(1.0)
            a2.set_blendmode("Screen")
            a2.set_flags(_ANNOT_FLAGS)
            a2.update()

            page_times.append(time.perf_counter() - t0)
            avg       = sum(page_times) / len(page_times)
            remaining = avg * (total - i - 1)
            progress_cb(i + 1, total, remaining)

        # TOC is preserved automatically — not rebuilding the document
        toc = doc.get_toc()

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp_path = tmp.name

        doc.save(
            tmp_path,
            garbage=4,
            deflate=True,
            deflate_images=True,
            deflate_fonts=True,
            clean=True,
            linear=False,
        )
        doc.close()
        shutil.move(tmp_path, str(output_path))

        done_cb(len(toc), total)

    except Exception:
        error_cb(traceback.format_exc())
    finally:
        if "doc" in locals():
            try:
                doc.close()
            except Exception:
                pass


# ── GUI ────────────────────────────────────────────────────────────────────────

C = {
    "bg":         "#0d0f14",
    "panel":      "#0a0c10",
    "surface":    "#13151c",
    "border":     "#2e3140",   # brighter (was #1e2028)
    "border2":    "#3a3e52",   # brighter (was #2a2d3a)
    "accent":     "#1e4ed8",
    "accent_dim": "#162ea0",
    "text":       "#e8eaf0",
    "text2":      "#c4c8d8",   # brighter (was #a0a8c0)
    "muted":      "#8a90a8",   # MUCH brighter (was #4a4e5c)
    "muted2":     "#6b7185",   # brighter (was #3d4155)
    "divider":    "#252730",   # slightly visible (was #1a1c24)
}

# Modern font stack — Segoe UI ships with Windows 10/11 and renders crisply
if platform.system() == "Darwin":
    _ui_font   = "SF Pro Display"
    _mono_font = "SF Mono"
elif platform.system() == "Windows":
    _ui_font   = "Segoe UI"
    _mono_font = "Consolas"
else:
    _ui_font   = "DejaVu Sans"
    _mono_font = "DejaVu Sans Mono"

FONT_MONO  = (_mono_font, 9)          # used only for file path entries
FONT_LABEL = (_ui_font,   9)
FONT_TITLE = (_ui_font,   17, "bold")
FONT_BTN   = (_ui_font,   10, "bold")
FONT_SMALL = (_ui_font,   8)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self._title_base = "PDF-DarkMod"
        self.title(self._title_base)
        self.geometry("1060x620")
        self.minsize(920, 560)
        self.configure(bg=C["bg"])
        self.resizable(True, True)

        self._current_width = 0
        self.bind("<Configure>", self._on_app_configure)

        # Match Tkinter's internal scaling to the actual display DPI
        try:
            dpi = self.winfo_fpixels("1i")  # pixels per inch
            self.tk.call("tk", "scaling", dpi / 72.0)
        except Exception:
            pass
        
        # Windows 11 Taskbar Icon + Dark Titlebar Support
        if sys.platform == "win32":
            try:
                # 1. Force Windows to use our icon for the taskbar (avoids default python icon)
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("pdfdarkmod.converter.v2")
                
                # 2. Set dark titlebar
                self.update_idletasks() # Ensure window is created
                hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
                value = ctypes.c_int(2) # 2 = Dark mode
                # DWMWA_USE_IMMERSIVE_DARK_MODE = 20
                ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(value), ctypes.sizeof(value))
            except Exception:
                pass

        try:
            import os
            # Resolve absolute path for icon to ensure it loads
            icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "favicon.ico")
            self.iconbitmap(icon_path)
        except Exception:
            pass

        self._input_path: Path | None = None
        self._converting = False
        
        self._input_var = tk.StringVar()
        self._output_var = tk.StringVar()
        self._theme_var = tk.StringVar(value="ChatGPT Cool")
        self._preserve_var = tk.BooleanVar(value=False)
        self._progress_var = tk.IntVar(value=0)

        self._preview_page_index = 0   # 0-based page index currently shown in preview
        self._preview_total_pages = 0  # set when a PDF is loaded

        self._zoom_mode = "fit"
        self._zoom_custom_factor = 1.0
        self._resize_timer = None

        # Triggers for preview
        self._input_var.trace_add("write", lambda *_: (
            setattr(self, '_preview_page_index', 0),
            self._page_entry_var.set("1") if hasattr(self, '_page_entry_var') else None,
            self._render_preview(self._theme_var.get(), page_index=0)
        ))
        self._theme_var.trace_add("write", lambda *_: self._render_preview(self._theme_var.get()))

        self._build_ui()

    def _make_field(self, parent, label_text: str, textvariable, btn_text: str, btn_cmd) -> tk.Frame:
        frame = tk.Frame(parent, bg=C["bg"])
        
        tk.Label(frame, text=label_text, font=FONT_LABEL,
                 bg=C["bg"], fg=C["muted"]).pack(anchor="w", pady=(0, 5))
        
        row = tk.Frame(frame, bg=C["bg"])
        row.pack(fill=tk.X)
        
        entry = tk.Entry(row, textvariable=textvariable,
                         font=FONT_MONO, bg=C["surface"], fg=C["text2"],
                         insertbackground=C["text2"], relief="flat",
                         highlightthickness=1, highlightbackground=C["border"],
                         highlightcolor=C["accent"])
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=6)
        
        btn = tk.Button(row, text=btn_text, command=btn_cmd,
                        font=FONT_LABEL, bg=C["surface"], fg=C["text2"],
                        activebackground=C["border2"], activeforeground=C["text"],
                        relief="flat", padx=10, cursor="hand2",
                        highlightthickness=1, highlightbackground=C["border"])
        btn.pack(side=tk.LEFT, padx=(6, 0), ipady=6)
        
        return frame

    def _make_dropdown(self, parent, variable: tk.StringVar, options: list, width: int = 18):
        """Custom dark-themed dropdown replacing tk.OptionMenu."""
        container = tk.Frame(parent, bg=C["surface"],
                             highlightthickness=1, highlightbackground=C["border"])

        btn = tk.Button(
            container,
            textvariable=variable,
            font=FONT_LABEL,
            bg=C["surface"], fg=C["text2"],
            activebackground=C["border2"], activeforeground=C["text"],
            relief="flat", anchor="w", padx=10, pady=7,
            cursor="hand2", bd=0,
            width=width,
        )
        btn.pack(side=tk.LEFT, fill=tk.X, expand=True)

        arrow = tk.Label(
            container, text="▾",
            font=(FONT_LABEL[0], 10),
            bg=C["surface"], fg=C["muted"],
            padx=6, pady=7, cursor="hand2",
        )
        arrow.pack(side=tk.RIGHT)

        menu = tk.Menu(
            self, tearoff=0,
            bg=C["surface"], fg=C["text2"],
            activebackground=C["accent"], activeforeground="#ffffff",
            font=FONT_LABEL,
            relief="flat", bd=1,
            activeborderwidth=0,
        )

        def _set(val):
            variable.set(val)

        for opt in options:
            menu.add_command(label=opt, command=lambda v=opt: _set(v))

        def _open_menu(event=None):
            x = container.winfo_rootx()
            y = container.winfo_rooty() + container.winfo_height()
            menu.tk_popup(x, y)

        btn.configure(command=_open_menu)
        arrow.bind("<Button-1>", _open_menu)
        container.bind("<Button-1>", _open_menu)

        return container

    def _build_ui(self):
        left_pane  = tk.Frame(self, bg=C["bg"], width=340)
        right_pane = tk.Frame(self, bg=C["panel"])
        left_pane.pack(side=tk.LEFT, fill=tk.Y, padx=0, pady=0)
        left_pane.pack_propagate(False)
        right_pane.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        SIDE_PAD = 24

        # --- LEFT PANEL ---
        title_frame = tk.Frame(left_pane, bg=C["bg"])
        title_frame.pack(fill=tk.X, pady=(22, 0))

        tk.Label(title_frame, text="PDF-DarkMod", font=FONT_TITLE,
                 bg=C["bg"], fg=C["text"]).pack(anchor="center")

        tk.Label(left_pane, text="Offline Converter",
                 font=FONT_SMALL, bg=C["bg"], fg=C["muted"]
                 ).pack(anchor="center", pady=(2, 20))

        # File inputs
        self._make_field(left_pane, "INPUT PDF", self._input_var, "Browse", self._browse_input).pack(
            fill=tk.X, padx=SIDE_PAD, pady=(0, 14))
        self._make_field(left_pane, "OUTPUT PDF", self._output_var, "Change", self._browse_output).pack(
            fill=tk.X, padx=SIDE_PAD, pady=(0, 14))

        # Thin divider
        tk.Frame(left_pane, bg=C["divider"], height=1).pack(
            fill=tk.X, padx=SIDE_PAD, pady=(6, 16))

        # Theme
        theme_block = tk.Frame(left_pane, bg=C["bg"])
        theme_block.pack(fill=tk.X, padx=SIDE_PAD, pady=(0, 14))
        tk.Label(theme_block, text="THEME", font=FONT_LABEL,
                 bg=C["bg"], fg=C["muted"]).pack(anchor="w", pady=(0, 5))

        self._make_dropdown(theme_block, self._theme_var, list(THEMES.keys()), width=16).pack(fill=tk.X)


        # Spacer pushes button to bottom
        tk.Frame(left_pane, bg=C["bg"]).pack(fill=tk.BOTH, expand=True)

        # Convert button
        self._convert_btn = tk.Button(
            left_pane,
            text="Convert to Dark Mode",
            command=self._start_conversion,
            font=FONT_BTN,
            bg=C["accent"], fg="#c8d8ff",
            activebackground=C["accent_dim"], activeforeground="#c8d8ff",
            relief="flat", cursor="hand2",
            pady=10
        )
        self._convert_btn.pack(fill=tk.X, padx=SIDE_PAD, pady=(0, 10))

        # Progress area
        prog_frame = tk.Frame(left_pane, bg=C["bg"])
        prog_frame.pack(fill=tk.X, padx=SIDE_PAD, pady=(0, 18))

        style = ttk.Style()
        try:
            style.theme_use("default")
        except Exception:
            pass
            
        style.configure("Thin.Horizontal.TProgressbar",
                        troughcolor=C["divider"],
                        background=C["accent"],
                        thickness=2,
                        borderwidth=0)

        self._progress = ttk.Progressbar(prog_frame, style="Thin.Horizontal.TProgressbar",
                                          variable=self._progress_var, maximum=100)
        self._progress.pack(fill=tk.X, pady=(0, 5))

        self._status_label = tk.Label(prog_frame, text="Select a PDF to begin.",
                                       font=FONT_SMALL, bg=C["bg"], fg=C["muted"],
                                       anchor="w")
        self._status_label.pack(fill=tk.X)


        # --- RIGHT PANEL ---
        header = tk.Frame(right_pane, bg=C["panel"], height=36)
        header.pack(fill=tk.X)
        header.pack_propagate(False)

        tk.Label(header, text="PREVIEW", font=FONT_LABEL,
                 bg=C["panel"], fg=C["muted"]).pack(side=tk.LEFT, padx=18, pady=0)

        self._preview_page_badge = tk.Label(header, text="PAGE 1",
            font=FONT_LABEL, bg=C["border2"], fg=C["text2"],
            padx=7, pady=2, relief="flat")
        self._preview_page_badge.pack(side=tk.LEFT, padx=(4, 0))

        # Navigation buttons — right-aligned in header
        nav_frame = tk.Frame(header, bg=C["panel"])
        nav_frame.pack(side=tk.RIGHT, padx=12)

        btn_zoom_out = tk.Button(
            nav_frame, text="−", command=self._zoom_out,
            font=FONT_LABEL, bg=C["surface"], fg=C["text2"],
            activebackground=C["border2"], activeforeground=C["text"],
            relief="flat", padx=6, pady=2, cursor="hand2",
            highlightthickness=1, highlightbackground=C["border"]
        )
        btn_zoom_out.pack(side=tk.LEFT, padx=(0, 4))

        btn_zoom_fit = tk.Button(
            nav_frame, text="Fit", command=self._zoom_fit,
            font=FONT_LABEL, bg=C["surface"], fg=C["text2"],
            activebackground=C["border2"], activeforeground=C["text"],
            relief="flat", padx=8, pady=2, cursor="hand2",
            highlightthickness=1, highlightbackground=C["border"]
        )
        btn_zoom_fit.pack(side=tk.LEFT, padx=(0, 4))

        btn_zoom_in = tk.Button(
            nav_frame, text="+", command=self._zoom_in,
            font=FONT_LABEL, bg=C["surface"], fg=C["text2"],
            activebackground=C["border2"], activeforeground=C["text"],
            relief="flat", padx=6, pady=2, cursor="hand2",
            highlightthickness=1, highlightbackground=C["border"]
        )
        btn_zoom_in.pack(side=tk.LEFT, padx=(0, 12))

        btn_prev = tk.Button(
            nav_frame, text="◀", command=self._preview_prev,
            font=FONT_LABEL, bg=C["surface"], fg=C["text2"],
            activebackground=C["border2"], activeforeground=C["text"],
            relief="flat", padx=8, pady=2, cursor="hand2",
            highlightthickness=1, highlightbackground=C["border"]
        )
        btn_prev.pack(side=tk.LEFT, padx=(0, 4))

        self._page_entry_var = tk.StringVar(value="1")
        page_entry = tk.Entry(
            nav_frame, textvariable=self._page_entry_var,
            font=FONT_LABEL, bg=C["surface"], fg=C["text2"],
            insertbackground=C["text2"], relief="flat",
            highlightthickness=1, highlightbackground=C["border"],
            width=4, justify="center"
        )
        page_entry.pack(side=tk.LEFT)
        page_entry.bind("<Return>", self._preview_goto)

        btn_next = tk.Button(
            nav_frame, text="▶", command=self._preview_next,
            font=FONT_LABEL, bg=C["surface"], fg=C["text2"],
            activebackground=C["border2"], activeforeground=C["text"],
            relief="flat", padx=8, pady=2, cursor="hand2",
            highlightthickness=1, highlightbackground=C["border"]
        )
        btn_next.pack(side=tk.LEFT, padx=(4, 0))

        tk.Frame(right_pane, bg=C["divider"], height=1).pack(fill=tk.X)

        preview_area = tk.Frame(right_pane, bg=C["panel"])
        preview_area.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        self._preview_canvas = tk.Canvas(preview_area, bg=C["surface"], highlightthickness=0)
        self._v_scroll = ttk.Scrollbar(preview_area, orient="vertical", command=self._preview_canvas.yview)
        self._h_scroll = ttk.Scrollbar(preview_area, orient="horizontal", command=self._preview_canvas.xview)
        self._preview_canvas.configure(yscrollcommand=self._v_scroll.set, xscrollcommand=self._h_scroll.set)
        
        self._v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self._h_scroll.pack(side=tk.BOTTOM, fill=tk.X)
        self._preview_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        self._canvas_img_id = self._preview_canvas.create_image(0, 0, anchor="nw")
        self._canvas_text_id = self._preview_canvas.create_text(
            0, 0, text="Load a PDF to preview", 
            font=FONT_MONO, fill=C["muted"], anchor="center"
        )
        self._preview_canvas.bind("<Configure>", self._on_canvas_configure)

        footer = tk.Frame(right_pane, bg=C["panel"], height=32)
        footer.pack(fill=tk.X, side=tk.BOTTOM)
        footer.pack_propagate(False)

        tk.Frame(right_pane, bg=C["divider"], height=1).pack(fill=tk.X, side=tk.BOTTOM)

        tk.Label(footer, text="SWITCH PREVIEW",
                 font=FONT_LABEL, bg=C["panel"], fg=C["muted"]).pack(side=tk.LEFT, padx=(14, 8))

        THEME_DOTS = {
            "Classic Inversion": "#000000",
            "Claude Warm":       "#2a2522",
            "ChatGPT Cool":      "#343541",
            "Sepia Dark":        "#282319",
            "Midnight Blue":     "#191e2d",
            "Forest Green":      "#19231e",
        }
        for theme_name, dot_color in THEME_DOTS.items():
            dot = tk.Label(footer, bg=dot_color, width=2, relief="flat", cursor="hand2",
                           highlightthickness=1, highlightbackground=C["border"])
            dot.pack(side=tk.LEFT, padx=3, pady=6)
            dot.bind("<Button-1>", lambda e, t=theme_name: self._on_theme_dot(t))
            dot.bind("<Enter>",    lambda e, d=dot: d.configure(highlightbackground=C["text2"]))
            dot.bind("<Leave>",    lambda e, d=dot: d.configure(highlightbackground=C["border"]))


    def _on_canvas_configure(self, event):
        self._preview_canvas.coords(self._canvas_text_id, event.width / 2, event.height / 2)
        if self._zoom_mode == "fit" and self._input_var.get():
            if self._resize_timer is not None:
                self.after_cancel(self._resize_timer)
            self._resize_timer = self.after(300, lambda: self._render_preview(self._theme_var.get()))

    def _on_app_configure(self, event):
        if event.widget == self:
            w = event.width
            if w != self._current_width:
                self._current_width = w
                if sys.platform == "win32":
                    title_len = len(self._title_base)
                    # Estimate the offset needed to center the text relative to the screen width,
                    # accounting for the window buttons (~140px) and icon (~40px).
                    pixels_needed = ((w - 180) / 2) - ((title_len * 7) / 2)
                    # Use Em Space (\u2003) which Windows titlebar does not strip.
                    # An Em Space is typically ~12 pixels wide in the standard title font.
                    spaces = max(0, int(pixels_needed / 12))
                    self.title("\u2003" * spaces + self._title_base)

    def _zoom_in(self):
        self._zoom_mode = "custom"
        self._zoom_custom_factor *= 1.25
        self._render_preview(self._theme_var.get())

    def _zoom_out(self):
        self._zoom_mode = "custom"
        self._zoom_custom_factor /= 1.25
        self._render_preview(self._theme_var.get())

    def _zoom_fit(self):
        self._zoom_mode = "fit"
        self._zoom_custom_factor = 1.0
        self._render_preview(self._theme_var.get())

    def _on_theme_dot(self, theme_name: str) -> None:
        self._theme_var.set(theme_name)

    def _preview_prev(self):
        if not self._input_var.get() or self._preview_total_pages == 0:
            return
        idx = max(0, self._preview_page_index - 1)
        self._page_entry_var.set(str(idx + 1))
        self._render_preview(self._theme_var.get(), page_index=idx)

    def _preview_next(self):
        if not self._input_var.get() or self._preview_total_pages == 0:
            return
        idx = min(self._preview_total_pages - 1, self._preview_page_index + 1)
        self._page_entry_var.set(str(idx + 1))
        self._render_preview(self._theme_var.get(), page_index=idx)

    def _preview_goto(self, event=None):
        if not self._input_var.get() or self._preview_total_pages == 0:
            return
        try:
            n = int(self._page_entry_var.get()) - 1
            n = max(0, min(n, self._preview_total_pages - 1))
            self._page_entry_var.set(str(n + 1))
            self._render_preview(self._theme_var.get(), page_index=n)
        except ValueError:
            pass


    # ── Helpers ────────────────────────────────────────────────────────────────

    def _fmt_eta(self, s: float) -> str:
        if s < 5:
            return ""
        m, s = divmod(int(s), 60)
        return f"~{m}m {s}s remaining" if m else f"~{s}s remaining"


    # ── File pickers ───────────────────────────────────────────────────────────

    def _browse_input(self):
        path = filedialog.askopenfilename(
            title="Select PDF", filetypes=[("PDF files", "*.pdf")])
        if not path:
            return
        self._input_path = Path(path)
        try:
            _doc = fitz.open(str(self._input_path))
            self._preview_total_pages = _doc.page_count
            _doc.close()
        except Exception:
            self._preview_total_pages = 1
        self._preview_page_index = 0
        self._input_var.set(str(self._input_path))
        self._output_var.set(str(
            self._input_path.parent / f"{self._input_path.stem}-dark.pdf"))
        self._convert_btn.configure(state="normal")
        self._status_label.configure(text=f"Ready: {self._input_path.name}")

    def _browse_output(self):
        path = filedialog.asksaveasfilename(
            title="Save output as",
            defaultextension=".pdf",
            filetypes=[("PDF files", "*.pdf")],
            initialfile=self._output_var.get())
        if path:
            self._output_var.set(path)

            
    # ── Preview Rendering ──────────────────────────────────────────────────────

    def _render_preview(self, theme: str, page_index: int = None) -> None:
        """Render page 1 of the loaded PDF at 72 DPI for preview. Non-blocking.
        Uses only PyMuPDF + tkinter.PhotoImage — no Pillow required.
        Applies the same luminance-based pixel algorithm as process_page.
        """
        if page_index is None:
            page_index = self._preview_page_index
        else:
            self._preview_page_index = page_index
        if not self._input_var.get():
            return

        input_path = Path(self._input_var.get())
        if not input_path.exists():
            return

        def _do_render():
            import base64
            try:
                bg = THEMES.get(theme, (42, 37, 34))
                BG_R, BG_G, BG_B = bg

                doc = fitz.open(str(input_path))
                page = doc[page_index]
                
                page_rect = page.rect
                page_w = page_rect.width
                page_h = page_rect.height
                
                zoom = 1.0
                if self._zoom_mode == "fit":
                    canvas_w = self._preview_canvas.winfo_width()
                    canvas_h = self._preview_canvas.winfo_height()
                    if canvas_w > 1 and canvas_h > 1:
                        margin = 20
                        zoom = min((canvas_w - margin) / page_w, (canvas_h - margin) / page_h)
                else:
                    zoom = self._zoom_custom_factor

                mat = fitz.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=mat, alpha=False, colorspace=fitz.csRGB)
                doc.close()

                if HAS_NUMPY:
                    import numpy as np
                    # NumPy vectorized transform — same luminance formula as process_page
                    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3).copy()

                    r = arr[:, :, 0].astype(np.float32)
                    g = arr[:, :, 1].astype(np.float32)
                    b = arr[:, :, 2].astype(np.float32)

                    brightness = 0.299 * r + 0.587 * g + 0.114 * b
                    factor = 1.0 - (brightness / 255.0)

                    arr[:, :, 0] = np.clip(BG_R + (255 - BG_R) * factor, 0, 255).astype(np.uint8)
                    arr[:, :, 1] = np.clip(BG_G + (255 - BG_G) * factor, 0, 255).astype(np.uint8)
                    arr[:, :, 2] = np.clip(BG_B + (255 - BG_B) * factor, 0, 255).astype(np.uint8)

                    pix = fitz.Pixmap(fitz.csRGB, pix.width, pix.height, arr.tobytes(), False)
                else:
                    # Pure-Python bytearray fallback
                    samples = bytearray(pix.samples)
                    for i in range(0, len(samples), 3):
                        r, g, b = samples[i], samples[i+1], samples[i+2]
                        brightness = 0.299 * r + 0.587 * g + 0.114 * b
                        factor = 1.0 - (brightness / 255.0)
                        samples[i] = int(min(255, max(0, BG_R + (255 - BG_R) * factor)))
                        samples[i+1] = int(min(255, max(0, BG_G + (255 - BG_G) * factor)))
                        samples[i+2] = int(min(255, max(0, BG_B + (255 - BG_B) * factor)))

                    pix = fitz.Pixmap(fitz.csRGB, pix.width, pix.height, bytes(samples), False)

                # Encode as PNG → base64 → tk.PhotoImage (no Pillow needed)
                b64 = base64.b64encode(pix.tobytes("png"))
                photo = tk.PhotoImage(data=b64)

                self.after(0, lambda p=photo: self._update_preview_image(p))
                self.after(0, lambda i=page_index, t=self._preview_total_pages:
                    self._preview_page_badge.configure(
                        text=f"PAGE {i + 1} / {t}"
                    )
                )
            except Exception as e:
                msg = str(e)
                self.after(0, lambda m=msg: self._show_preview_error(m))

        threading.Thread(target=_do_render, daemon=True).start()

    def _update_preview_image(self, photo) -> None:
        self._preview_photo = photo  # keep reference to prevent GC
        self._preview_canvas.itemconfig(self._canvas_img_id, image=photo)
        self._preview_canvas.itemconfig(self._canvas_text_id, state="hidden")
        
        cw = self._preview_canvas.winfo_width()
        ch = self._preview_canvas.winfo_height()
        iw = photo.width()
        ih = photo.height()
        
        x = max(0, (cw - iw) // 2)
        y = max(0, (ch - ih) // 2)
        
        self._preview_canvas.coords(self._canvas_img_id, x, y)
        self._preview_canvas.configure(scrollregion=(0, 0, max(cw, iw), max(ch, ih)))

    def _show_preview_error(self, msg: str) -> None:
        self._preview_canvas.itemconfig(self._canvas_text_id, text=f"Preview error:\n{msg}", state="normal")
        self._preview_canvas.itemconfig(self._canvas_img_id, image="")


    # ── Conversion ─────────────────────────────────────────────────────────────

    def _start_conversion(self):
        if self._converting or not self._input_path:
            return
        output_path = Path(self._output_var.get() or str(
            self._input_path.parent / f"{self._input_path.stem}-dark.pdf"))
        if not output_path.suffix:
            output_path = output_path.with_suffix(".pdf")

        self._converting = True
        self._convert_btn.configure(state="disabled", text="Converting…")
        self._progress_var.set(0)
        self._status_label.configure(text="Starting…")

        threading.Thread(
            target=convert_pdf,
            args=(self._input_path, output_path, self._theme_var.get(),
                  0,       # dpi — unused, kept for signature compat
                  False,   # preserve_text — unused
                  0,       # jpeg_quality — unused
                  False,   # searchable — unused
                  self._on_progress, self._on_done, self._on_error),
            daemon=True,
        ).start()

    # ── Thread-safe callbacks ──────────────────────────────────────────────────

    def _on_progress(self, current: int, total: int, eta: float):
        pct = int((current / total) * 100)
        eta_str = self._fmt_eta(eta) if eta > 0 else "Applying text layer..."
        
        def _update():
            self._progress_var.set(pct)
            self._status_label.configure(text=f"Page {current} of {total}   {eta_str}")
            
        self.after(0, _update)

    def _on_done(self, bookmark_count: int, page_count: int):
        def _finish():
            self._converting = False
            self._progress_var.set(100)
            self._convert_btn.configure(state="normal", text="Convert to Dark Mode")
            self._status_label.configure(text=f"Done: {page_count} pages, {bookmark_count} bookmarks preserved.")
            messagebox.showinfo("Done",
                f"Saved to:\n{self._output_var.get()}\n\n"
                f"{page_count} pages converted · "
                f"{bookmark_count} bookmark{'s' if bookmark_count != 1 else ''} preserved\n"
                f"Text is searchable · Native vector quality")
        self.after(0, _finish)

    def _on_error(self, message: str):
        def _show():
            self._converting = False
            self._convert_btn.configure(state="normal", text="Convert to Dark Mode")
            self._status_label.configure(text="Failed — see error dialog.")
            messagebox.showerror("Conversion failed", message)
        self.after(0, _show)


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = App()
    app.mainloop()