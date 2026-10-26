"""
Overlay de GrabaClip: un indicador pequeno de "clips activos / grabando" y un aviso
cuando se guarda un clip. Son ventanas siempre encima, que no reciben clics y que
no aparecen en las grabaciones.

Funciona sobre juegos en modo ventana o "pantalla completa sin bordes". En pantalla
completa exclusiva Windows no deja dibujar nada encima.
"""
import sys
import time
import queue

from idiomas import t_overlay as t
import threading

CLAVE = "#010203"   # color que se vuelve transparente
FUENTE = "Segoe UI Semibold"


def _hwnd(ventana):
    import ctypes
    ventana.update_idletasks()
    return ctypes.windll.user32.GetParent(ventana.winfo_id()) or ventana.winfo_id()


def _hacer_fantasma(ventana):
    """Sin clics, sin foco, fuera de Alt+Tab y fuera de las capturas de pantalla."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        u32 = ctypes.windll.user32
        h = _hwnd(ventana)
        GWL_EXSTYLE = -20
        estilo = u32.GetWindowLongW(h, GWL_EXSTYLE)
        # LAYERED | TRANSPARENT (clics pasan) | TOOLWINDOW (no en Alt+Tab) | NOACTIVATE | TOPMOST
        estilo |= 0x00080000 | 0x00000020 | 0x00000080 | 0x08000000 | 0x00000008
        u32.SetWindowLongW(h, GWL_EXSTYLE, estilo)
        u32.SetWindowDisplayAffinity(h, 0x11)  # WDA_EXCLUDEFROMCAPTURE (Windows 10 2004+)
    except Exception:
        pass


def _zona_pantalla():
    """Rectangulo (x, y, ancho, alto) de la pantalla donde esta la ventana activa."""
    try:
        import ctypes
        from ctypes import wintypes

        class MONITORINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                        ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]
        u32 = ctypes.windll.user32
        u32.MonitorFromWindow.restype = ctypes.c_void_p
        mon = u32.MonitorFromWindow(ctypes.c_void_p(u32.GetForegroundWindow()), 2)  # NEAREST
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)
        if u32.GetMonitorInfoW(ctypes.c_void_p(mon), ctypes.byref(info)):
            r = info.rcMonitor
            return r.left, r.top, r.right - r.left, r.bottom - r.top
    except Exception:
        pass
    return 0, 0, 1920, 1080


def _rect_redondo(lienzo, x1, y1, x2, y2, r, **kw):
    puntos = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
              x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return lienzo.create_polygon(puntos, smooth=True, **kw)


class Overlay:
    """Se maneja desde cualquier hilo: todo lo de Tk ocurre en su propio hilo."""

    def __init__(self, obtener_cfg, obtener_tema):
        self._cfg = obtener_cfg
        self._tema = obtener_tema
        self._cola = queue.Queue()
        self._estado = {"clips": False, "grabando": False, "inicio_grab": None, "esperando": False}
        self._listo = False
        if sys.platform == "win32":
            threading.Thread(target=self._hilo, daemon=True).start()

    # ---------- llamadas publicas ----------
    def actualizar(self, estado):
        self._cola.put(("estado", dict(estado)))

    def clip_guardado(self, titulo, detalle):
        self._cola.put(("aviso", (titulo, detalle)))

    def refrescar(self):
        self._cola.put(("refrescar", None))

    # ---------- hilo de Tk ----------
    def _hilo(self):
        try:
            import tkinter as tk
        except Exception:
            return
        try:
            self._tk = tk
            self.raiz = tk.Tk()
            self.raiz.withdraw()
            self.ind = self._ventana()
            self.ind_lienzo = tk.Canvas(self.ind, bg=CLAVE, highlightthickness=0, bd=0)
            self.ind_lienzo.pack(fill="both", expand=True)
            self.av = self._ventana()
            self.av_lienzo = tk.Canvas(self.av, bg=CLAVE, highlightthickness=0, bd=0)
            self.av_lienzo.pack(fill="both", expand=True)
            self._aviso_hasta = 0
            self._aviso_alfa = 0.0
            self._latido = 0
            self._listo = True
            self.raiz.after(100, self._tic)
            self.raiz.mainloop()
        except Exception:
            self._listo = False

    def _ventana(self):
        v = self._tk.Toplevel(self.raiz)
        v.overrideredirect(True)
        v.attributes("-topmost", True)
        v.attributes("-transparentcolor", CLAVE)
        v.attributes("-alpha", 0.0)
        v.configure(bg=CLAVE)
        v.geometry("10x10+-2000+-2000")
        v.deiconify()
        _hacer_fantasma(v)
        return v

    def _opcion(self, clave, defecto=True):
        cfg = self._cfg() or {}
        return bool(cfg.get("overlay", True)) and bool(cfg.get(clave, defecto))

    def _colocar(self, ventana, ancho, alto, desde_arriba):
        x0, y0, w, h = _zona_pantalla()
        margen = 22
        izquierda = (self._cfg() or {}).get("overlay_pos", "der") == "izq"
        x = x0 + margen if izquierda else x0 + w - ancho - margen
        ventana.geometry(f"{ancho}x{alto}+{x}+{y0 + desde_arriba}")

    def _tic(self):
        try:
            while True:
                tipo, dato = self._cola.get_nowait()
                if tipo == "estado":
                    self._estado = dato
                elif tipo == "aviso" and self._opcion("overlay_aviso"):
                    self._pintar_aviso(*dato)
                    self._aviso_hasta = time.time() + 3.2
        except queue.Empty:
            pass
        try:
            self._pintar_indicador()
            self._animar_aviso()
        except Exception:
            pass
        self.raiz.after(120, self._tic)

    # indicador "Clips" / "REC 00:01:23"
    def _pintar_indicador(self):
        e = self._estado
        visible = self._opcion("overlay_indicador") and (e.get("grabando") or e.get("clips"))
        if not visible:
            self.ind.attributes("-alpha", 0.0)
            return
        t = self._tema()
        c = self.ind_lienzo
        c.delete("all")
        self._latido = (self._latido + 1) % 16
        if e.get("grabando"):
            s = int(time.time() - (e.get("inicio_grab") or time.time() * 1000) / 1000)
            texto = "REC  %02d:%02d:%02d" % (s // 3600, s // 60 % 60, s % 60)
            punto = "#ef4444" if self._latido < 10 else "#7f1d1d"
        elif e.get("esperando"):
            texto, punto = t("Clips · esperando juego"), "#9ca3af"
        else:
            texto = t("Clips")
            punto = "#22c55e" if self._latido < 12 else "#15803d"
        ancho = 30 + 8 * len(texto) + 20
        alto = 30
        _rect_redondo(c, 1, 1, ancho - 1, alto - 1, 10, fill="#16161a", outline="#2e2e34")
        c.create_oval(13, 11, 21, 19, fill=punto, outline="")
        c.create_text(29, alto // 2, text=texto, anchor="w", fill="#f2f2f4", font=(FUENTE, 10))
        self._colocar(self.ind, ancho, alto, 22)
        self.ind.attributes("-alpha", 0.88)
        self.ind.attributes("-topmost", True)

    # aviso "Clip guardado"
    def _pintar_aviso(self, titulo, detalle):
        t = self._tema()
        c = self.av_lienzo
        c.delete("all")
        ancho = max(250, 70 + 8 * max(len(titulo), len(detalle)))
        alto = 62
        _rect_redondo(c, 1, 1, ancho - 1, alto - 1, 12, fill="#16161a", outline=t.get("acento", "#c8243f"))
        # circulo con check
        c.create_oval(14, 15, 46, 47, fill=t.get("acento", "#c8243f"), outline="")
        c.create_line(22, 31, 28, 37, 39, 25, fill="#ffffff", width=3, capstyle="round", joinstyle="round")
        c.create_text(58, 23, text=titulo, anchor="w", fill="#ffffff", font=(FUENTE, 11))
        c.create_text(58, 42, text=detalle, anchor="w", fill="#a1a1aa", font=("Segoe UI", 9))
        hay_indicador = self.ind.attributes("-alpha") > 0
        self._colocar(self.av, ancho, alto, 64 if hay_indicador else 22)
        self.av.attributes("-topmost", True)

    def _animar_aviso(self):
        objetivo = 0.95 if time.time() < self._aviso_hasta else 0.0
        if abs(self._aviso_alfa - objetivo) < 0.01:
            return
        paso = 0.25 if objetivo > self._aviso_alfa else -0.12
        self._aviso_alfa = max(0.0, min(0.95, self._aviso_alfa + paso))
        self.av.attributes("-alpha", self._aviso_alfa)
