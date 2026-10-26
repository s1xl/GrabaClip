"""
GrabaClip - Grabador de pantalla y clips instantaneos para Windows.
Version 0.4: teclas personalizables y temas de color.

Teclas (cambiables en la app): F9 guarda un clip, F10 empieza / detiene la grabacion.
"""
import os
import sys
import glob
import json
import queue
import shutil
import tempfile
import datetime
import itertools
import threading
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox

try:
    import keyboard  # teclas rapidas globales
except ImportError:
    keyboard = None

APP = "GrabaClip"
CARPETA_APP = os.path.dirname(os.path.abspath(__file__))
AUDIOCAP = os.path.join(CARPETA_APP, "audiocap.exe")
ARCHIVO_CONFIG = os.path.join(CARPETA_APP, "config.json")
CARPETA_SALIDA = os.path.join(os.path.expanduser("~"), "Videos", APP)
CARPETA_BUFER = os.path.join(tempfile.gettempdir(), APP + "_bufer")
CARPETA_LOGS = os.path.join(CARPETA_APP, "logs")
SEG = 2  # segundos que dura cada trocito del bufer
SIN_VENTANA = 0x08000000 if sys.platform == "win32" else 0
CONTADOR = itertools.count()

# Calidad: numero mas bajo = mejor imagen y archivos mas grandes
CALIDADES = {
    "Baja": 30,
    "Media": 26,
    "Alta": 22,
    "Muy alta": 19,
    "Maxima": 16,
}
FPS_OPCIONES = ["30", "60", "120", "144", "240"]
RESOLUCIONES = {"Original": 0, "1440p": 1440, "1080p": 1080, "720p": 720}


def args_encoder(encoder, calidad):
    q = CALIDADES.get(calidad, 22)
    if encoder == "h264_nvenc":
        preset = "p5" if q <= 19 else "p4"
        return ["-c:v", "h264_nvenc", "-preset", preset, "-rc", "vbr",
                "-cq", str(q), "-b:v", "0", "-spatial-aq", "1"]
    if encoder == "h264_amf":
        return ["-c:v", "h264_amf", "-quality", "quality" if q <= 19 else "balanced",
                "-rc", "cqp", "-qp_i", str(q - 1), "-qp_p", str(q + 1)]
    if encoder == "h264_qsv":
        return ["-c:v", "h264_qsv", "-global_quality", str(q), "-preset", "medium"]
    return ["-c:v", "libx264", "-preset", "veryfast", "-crf", str(q)]

NOMBRES = {
    "h264_nvenc": "GPU NVIDIA (NVENC)",
    "h264_amf": "GPU AMD (AMF)",
    "h264_qsv": "Intel QuickSync",
    "libx264": "Procesador (CPU, mas lento)",
}
CONFIG_INICIAL = {"duracion": 30, "fps": "60", "calidad": "Alta", "resolucion": "Original",
                  "mic": True, "apps": [], "ajuste_ms": 0,
                  "tecla_clip": "f9", "tecla_grab": "f10", "tema": "Oscuro"}

# ---------- temas ----------
# bg: fondo, panel: botones, campo: cajas de texto, tenue: texto secundario
TEMAS = {
    "Oscuro": dict(bg="#1e1f24", panel="#2c2e36", campo="#26282e", fg="#e8e8ec", tenue="#9a9ca6",
                   acento="#4c8dff", acento_fg="#ffffff", borde="#3a3d46", oscuro=True),
    "Medianoche": dict(bg="#0f172a", panel="#1e293b", campo="#172036", fg="#e2e8f0", tenue="#94a3b8",
                       acento="#38bdf8", acento_fg="#04121f", borde="#334155", oscuro=True),
    "Neon": dict(bg="#120b1f", panel="#22153b", campo="#1a1030", fg="#f3e8ff", tenue="#a78bca",
                 acento="#d946ef", acento_fg="#ffffff", borde="#3b2763", oscuro=True),
    "Bosque": dict(bg="#101a14", panel="#1c2b22", campo="#16231b", fg="#e3f1e7", tenue="#8fab98",
                   acento="#34d399", acento_fg="#062016", borde="#2c4235", oscuro=True),
    "Atardecer": dict(bg="#1f1410", panel="#30201a", campo="#281a14", fg="#fdebe1", tenue="#c19a86",
                      acento="#fb7a3c", acento_fg="#1f0d04", borde="#4a3227", oscuro=True),
    "Lima": dict(bg="#111111", panel="#1f1f1f", campo="#181818", fg="#eeeeee", tenue="#8c8c8c",
                 acento="#84cc16", acento_fg="#0b1400", borde="#333333", oscuro=True),
    "Rojo": dict(bg="#160d0f", panel="#27171a", campo="#1f1214", fg="#f5e6e8", tenue="#ad8a90",
                 acento="#ef4444", acento_fg="#ffffff", borde="#432a2e", oscuro=True),
    "Claro": dict(bg="#f5f6f8", panel="#ffffff", campo="#ffffff", fg="#1d1f24", tenue="#6b7080",
                  acento="#2563eb", acento_fg="#ffffff", borde="#d5d8df", oscuro=False),
    "Arena": dict(bg="#f6f1e7", panel="#fffaf0", campo="#fffdf8", fg="#3b3226", tenue="#8a7d6a",
                  acento="#b7791f", acento_fg="#ffffff", borde="#e2d6c2", oscuro=False),
    "Rosa": dict(bg="#fdf2f6", panel="#ffffff", campo="#ffffff", fg="#3a1d2b", tenue="#9b6b80",
                 acento="#e11d74", acento_fg="#ffffff", borde="#f1cfdd", oscuro=False),
    "Menta": dict(bg="#eff8f4", panel="#ffffff", campo="#ffffff", fg="#15302a", tenue="#5f8377",
                  acento="#0f9f77", acento_fg="#ffffff", borde="#cfe7dd", oscuro=False),
    "Alto contraste": dict(bg="#000000", panel="#000000", campo="#000000", fg="#ffffff",
                           tenue="#ffff00", acento="#ffff00", acento_fg="#000000", borde="#ffffff",
                           oscuro=True),
}


def mezclar(c1, c2, t):
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(a, b))


def colorear_barra_titulo(ventana, t):
    """Windows 10/11: barra de titulo oscura o clara (y del color del tema en Windows 11)."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ventana.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(ventana.winfo_id())
        dwm = ctypes.windll.dwmapi
        oscuro = ctypes.c_int(1 if t["oscuro"] else 0)
        dwm.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(oscuro), 4)
        for attr, color in ((35, t["bg"]), (36, t["fg"])):
            r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
            ref = ctypes.c_uint(r | (g << 8) | (b << 16))
            dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(ref), 4)
    except Exception:
        pass


def aplicar_estilo(root, t):
    st = ttk.Style(root)
    st.theme_use("clam")
    hover = mezclar(t["panel"], t["acento"], 0.25)
    fuente = ("Segoe UI", 10)
    st.configure(".", background=t["bg"], foreground=t["fg"], fieldbackground=t["campo"],
                 bordercolor=t["borde"], lightcolor=t["bg"], darkcolor=t["bg"],
                 troughcolor=t["bg"], focuscolor=t["acento"], selectbackground=t["acento"],
                 selectforeground=t["acento_fg"], insertcolor=t["fg"], arrowcolor=t["fg"],
                 font=fuente)
    st.configure("TFrame", background=t["bg"])
    st.configure("TLabel", background=t["bg"], foreground=t["fg"])
    st.configure("Tenue.TLabel", foreground=t["tenue"])
    st.configure("Titulo.TLabel", foreground=t["acento"], font=("Segoe UI", 18, "bold"))
    st.configure("TLabelframe", background=t["bg"], bordercolor=t["borde"])
    st.configure("TLabelframe.Label", background=t["bg"], foreground=t["acento"],
                 font=("Segoe UI", 10, "bold"))
    st.configure("TButton", background=t["panel"], foreground=t["fg"], padding=(10, 6),
                 bordercolor=t["borde"], lightcolor=t["panel"], darkcolor=t["panel"])
    st.map("TButton",
           background=[("disabled", t["bg"]), ("pressed", t["acento"]), ("active", hover)],
           foreground=[("disabled", t["tenue"]), ("pressed", t["acento_fg"])],
           lightcolor=[("active", hover)], darkcolor=[("active", hover)])
    acento_hover = mezclar(t["acento"], t["fg"], 0.15)
    st.configure("Acento.TButton", background=t["acento"], foreground=t["acento_fg"],
                 lightcolor=t["acento"], darkcolor=t["acento"], bordercolor=t["acento"],
                 font=("Segoe UI", 10, "bold"))
    st.map("Acento.TButton",
           background=[("disabled", t["panel"]), ("pressed", acento_hover), ("active", acento_hover)],
           foreground=[("disabled", t["tenue"])],
           lightcolor=[("active", acento_hover)], darkcolor=[("active", acento_hover)])
    st.configure("TCheckbutton", background=t["bg"], foreground=t["fg"],
                 indicatorbackground=t["campo"], indicatorforeground=t["acento_fg"])
    st.map("TCheckbutton", background=[("active", t["bg"])],
           indicatorbackground=[("selected", t["acento"])],
           foreground=[("disabled", t["tenue"])])
    for w in ("TCombobox", "TSpinbox"):
        st.configure(w, fieldbackground=t["campo"], background=t["panel"], foreground=t["fg"],
                     arrowcolor=t["fg"], bordercolor=t["borde"], lightcolor=t["campo"],
                     darkcolor=t["campo"], padding=3)
        st.map(w, fieldbackground=[("readonly", t["campo"]), ("disabled", t["bg"])],
               foreground=[("disabled", t["tenue"])],
               selectbackground=[("readonly", t["campo"])],
               selectforeground=[("readonly", t["fg"])],
               background=[("active", hover)])
    st.configure("Vertical.TScrollbar", background=t["panel"], troughcolor=t["bg"],
                 bordercolor=t["bg"], arrowcolor=t["fg"], lightcolor=t["panel"],
                 darkcolor=t["panel"])
    st.map("Vertical.TScrollbar", background=[("active", hover)])
    root.configure(bg=t["bg"])
    root.option_add("*TCombobox*Listbox.background", t["campo"])
    root.option_add("*TCombobox*Listbox.foreground", t["fg"])
    root.option_add("*TCombobox*Listbox.selectBackground", t["acento"])
    root.option_add("*TCombobox*Listbox.selectForeground", t["acento_fg"])


def tecla_bonita(combo):
    return "+".join(p.upper() if len(p) <= 3 else p.capitalize() for p in combo.split("+"))


def correr(args, **kw):
    return subprocess.run(args, capture_output=True, creationflags=SIN_VENTANA, **kw)


def detectar_encoder():
    """Prueba los codificadores por hardware y usa el primero que funcione."""
    for enc in ["h264_nvenc", "h264_amf", "h264_qsv"]:
        r = correr(["ffmpeg", "-hide_banner", "-loglevel", "error",
                    "-f", "lavfi", "-i", "color=black:s=640x360:r=30",
                    "-frames:v", "5", "-c:v", enc, "-f", "null", "-"])
        if r.returncode == 0:
            return enc
    return "libx264"


def cargar_config():
    cfg = dict(CONFIG_INICIAL)
    try:
        with open(ARCHIVO_CONFIG, encoding="utf-8") as f:
            cfg.update(json.load(f))
    except Exception:
        pass
    return cfg


def guardar_config(cfg):
    try:
        with open(ARCHIVO_CONFIG, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def apps_con_sonido():
    """Pide a audiocap.exe la lista de programas que tienen audio."""
    if not os.path.exists(AUDIOCAP):
        return []
    try:
        r = correr([AUDIOCAP, "list"], timeout=8)
    except Exception:
        return []
    apps = []
    for linea in r.stdout.decode("utf-8", "replace").splitlines():
        exe = linea.split("\t")[0].strip()
        if exe and exe.lower() not in [a.lower() for a in apps]:
            apps.append(exe)
    return apps


def nombre_bonito(exe):
    base = exe[:-4] if exe.lower().endswith(".exe") else exe
    return base[:1].upper() + base[1:]


def marca_tiempo():
    return datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def detener(proc, timeout=8):
    """Detiene ffmpeg con 'q' para que el archivo quede bien cerrado."""
    if proc is None or proc.poll() is not None:
        return
    try:
        proc.stdin.write(b"q")
        proc.stdin.flush()
        proc.wait(timeout=timeout)
    except Exception:
        proc.kill()


class Sesion:
    """Un ffmpeg (video + pistas de audio) junto con su ayudante de audio."""

    def __init__(self, fps, encoder, cfg, salida_args, nombre_log):
        self.audio = None
        self.pistas = []  # nombres de las pistas de audio, en orden
        self.aviso = ""
        os.makedirs(CARPETA_LOGS, exist_ok=True)

        especies = ["sys"]
        nombres_entrada = ["Sistema"]
        if cfg["mic"]:
            especies.append("mic")
            nombres_entrada.append("Microfono")
        for exe in cfg["apps"]:
            especies.append("app:" + exe)
            nombres_entrada.append(nombre_bonito(exe))

        prefijo = f"{APP}_{os.getpid()}_{next(CONTADOR)}"
        entradas = []
        if os.path.exists(AUDIOCAP):
            try:
                self.audio = subprocess.Popen(
                    [AUDIOCAP, "run", prefijo] + especies,
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                    stderr=open(os.path.join(CARPETA_LOGS, "audio_" + nombre_log), "w"),
                    creationflags=SIN_VENTANA)
                if self.audio.stdout.readline().strip() != b"READY":
                    raise RuntimeError("audiocap no respondio")
            except Exception:
                self.cerrar_audio()
                self.audio = None
        if self.audio is None:
            self.aviso = " (sin audio: fallo el ayudante de audio)"

        offset = f"{cfg['ajuste_ms'] / 1000:.3f}"
        if self.audio:
            for i in range(len(especies)):
                entradas += ["-itsoffset", offset,
                             "-f", "s16le", "-ar", "48000", "-ac", "2",
                             "-i", rf"\\.\pipe\{prefijo}_{i}"]

        alto = RESOLUCIONES.get(cfg["resolucion"], 0)
        escala = f"scale=-2:'min(ih,{alto})':flags=bicubic," if alto else ""
        filtro = (f"ddagrab=output_idx=0:framerate={fps}:draw_mouse=1,"
                  f"hwdownload,format=bgra,{escala}format=yuv420p[v]")
        mapas = ["-map", "[v]"]
        if self.audio:
            if cfg["mic"]:
                filtro += ";[0:a][1:a]amix=inputs=2:duration=longest:normalize=0[mezcla]"
                mapas += ["-map", "[mezcla]"]
            else:
                mapas += ["-map", "0:a"]
            self.pistas.append("Mezcla")
            for i in range(1, len(especies)):  # micro y apps (el "Sistema" ya esta en la mezcla)
                mapas += ["-map", f"{i}:a"]
                self.pistas.append(nombres_entrada[i])

        args = (entradas
                + ["-filter_complex", filtro] + mapas
                + args_encoder(encoder, cfg["calidad"])
                + ["-g", str(fps * SEG), "-force_key_frames", f"expr:gte(t,n_forced*{SEG})"])
        if self.pistas:
            args += ["-c:a", "aac", "-b:a", "160k"] + metadatos(self.pistas)
        args += salida_args

        self.log = open(os.path.join(CARPETA_LOGS, nombre_log), "w", encoding="utf-8")
        self.ffmpeg = subprocess.Popen(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"] + args,
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=self.log,
            creationflags=SIN_VENTANA)

    def viva(self):
        return self.ffmpeg.poll() is None

    def cerrar_audio(self):
        if self.audio and self.audio.poll() is None:
            try:
                self.audio.stdin.close()
                self.audio.wait(timeout=3)
            except Exception:
                self.audio.kill()

    def detener(self):
        detener(self.ffmpeg)
        self.cerrar_audio()


def metadatos(pistas):
    args = []
    for i, nombre in enumerate(pistas):
        args += [f"-metadata:s:a:{i}", f"title={nombre}",
                 f"-metadata:s:a:{i}", f"handler_name={nombre}"]
    return args


class App:
    def __init__(self, root):
        self.root = root
        self.cola = queue.Queue()
        self.cfg = cargar_config()
        self.bufer = None
        self.grab = None
        self.archivo_grab = None
        self.encoder = None

        self.capturando = None
        self.ventana_tema = None

        root.title(APP)
        root.resizable(False, False)
        aplicar_estilo(root, self.tema())
        marco = ttk.Frame(root, padding=18)
        marco.grid()
        marco.columnconfigure(0, weight=1, uniform="col")
        marco.columnconfigure(1, weight=1, uniform="col")

        cabecera = ttk.Frame(marco)
        cabecera.grid(row=0, columnspan=2, sticky="ew")
        ttk.Label(cabecera, text=APP, style="Titulo.TLabel").pack(side="left")
        ttk.Button(cabecera, text="\U0001F3A8  Tema", command=self.abrir_temas).pack(side="right")
        self.lbl_enc = ttk.Label(marco, text="Detectando tu tarjeta grafica...", style="Tenue.TLabel")
        self.lbl_enc.grid(row=1, columnspan=2, sticky="w", pady=(0, 10))

        izquierda = ttk.Frame(marco)
        izquierda.grid(row=2, column=0, sticky="nsew", padx=(0, 8))
        izquierda.columnconfigure(0, weight=1)

        # --- video ---
        video = ttk.LabelFrame(izquierda, text=" Video ", padding=10)
        video.grid(row=0, sticky="ew")
        video.columnconfigure(0, weight=1)

        ttk.Label(video, text="Duracion del clip (segundos):").grid(row=0, column=0, sticky="w")
        self.var_dur = tk.IntVar(value=self.cfg["duracion"])
        self.spin_dur = ttk.Spinbox(video, from_=10, to=300, increment=10,
                                    textvariable=self.var_dur, width=10)
        self.spin_dur.grid(row=0, column=1, sticky="e", pady=3)

        ttk.Label(video, text="Cuadros por segundo (FPS):").grid(row=1, column=0, sticky="w")
        self.var_fps = tk.StringVar(value=self.cfg["fps"])
        self.cmb_fps = ttk.Combobox(video, values=FPS_OPCIONES, textvariable=self.var_fps,
                                    width=10, state="readonly")
        self.cmb_fps.grid(row=1, column=1, sticky="e", pady=3)

        ttk.Label(video, text="Calidad:").grid(row=2, column=0, sticky="w")
        self.var_cal = tk.StringVar(value=self.cfg["calidad"])
        self.cmb_cal = ttk.Combobox(video, values=list(CALIDADES), textvariable=self.var_cal,
                                    width=10, state="readonly")
        self.cmb_cal.grid(row=2, column=1, sticky="e", pady=3)

        ttk.Label(video, text="Resolucion:").grid(row=3, column=0, sticky="w")
        self.var_res = tk.StringVar(value=self.cfg["resolucion"])
        self.cmb_res = ttk.Combobox(video, values=list(RESOLUCIONES), textvariable=self.var_res,
                                    width=10, state="readonly")
        self.cmb_res.grid(row=3, column=1, sticky="e", pady=3)

        ttk.Label(video, text="Mas FPS y calidad = videos mas fluidos, pero archivos mas grandes.\n"
                              "Si tu monitor es de 60 Hz, mas de 60 FPS no aporta nada.",
                  style="Tenue.TLabel").grid(row=4, columnspan=2, sticky="w", pady=(4, 0))
        for cmb in (self.cmb_fps, self.cmb_cal, self.cmb_res):
            cmb.bind("<<ComboboxSelected>>", lambda e: self.guardar())

        # --- teclas ---
        teclas = ttk.LabelFrame(izquierda, text=" Teclas rapidas ", padding=10)
        teclas.grid(row=1, sticky="ew", pady=(10, 0))
        teclas.columnconfigure(0, weight=1)
        ttk.Label(teclas, text="Guardar clip:").grid(row=0, column=0, sticky="w")
        self.btn_tecla_clip = ttk.Button(teclas, width=16,
                                         command=lambda: self.cambiar_tecla("tecla_clip"))
        self.btn_tecla_clip.grid(row=0, column=1, sticky="e", pady=3)
        ttk.Label(teclas, text="Grabar / detener:").grid(row=1, column=0, sticky="w")
        self.btn_tecla_grab = ttk.Button(teclas, width=16,
                                         command=lambda: self.cambiar_tecla("tecla_grab"))
        self.btn_tecla_grab.grid(row=1, column=1, sticky="e", pady=3)
        ttk.Label(teclas, text="Pulsa un boton y luego la tecla o combinacion nueva.",
                  style="Tenue.TLabel").grid(row=2, columnspan=2, sticky="w", pady=(4, 0))

        # --- audio ---
        audio = ttk.LabelFrame(marco, text=" Audio ", padding=10)
        audio.grid(row=2, column=1, sticky="nsew", padx=(8, 0))
        audio.columnconfigure(0, weight=1)
        self.var_mic = tk.BooleanVar(value=self.cfg["mic"])
        self.chk_mic = ttk.Checkbutton(audio, text="Grabar microfono (pista aparte)",
                                       variable=self.var_mic, command=self.guardar)
        self.chk_mic.grid(row=0, columnspan=2, sticky="w")
        ttk.Label(audio, text="Apps en su propia pista (clic para marcar):").grid(
            row=1, columnspan=2, sticky="w", pady=(8, 2))
        self.lista = tk.Listbox(audio, selectmode="multiple", height=7, activestyle="none",
                                exportselection=False, font=("Segoe UI", 10), relief="flat",
                                borderwidth=0, highlightthickness=1)
        self.lista.grid(row=2, column=0, sticky="ew")
        self.lista.bind("<<ListboxSelect>>", lambda e: self.guardar())
        barra = ttk.Scrollbar(audio, orient="vertical", command=self.lista.yview)
        barra.grid(row=2, column=1, sticky="ns")
        self.lista.config(yscrollcommand=barra.set)
        self.btn_actualizar = ttk.Button(audio, text="Actualizar lista de apps",
                                         command=self.actualizar_apps)
        self.btn_actualizar.grid(row=3, columnspan=2, sticky="ew", pady=(4, 0))
        ttk.Label(audio, text="La pista 1 siempre lleva todo mezclado.",
                  style="Tenue.TLabel").grid(row=4, columnspan=2, sticky="w", pady=(4, 0))
        fila = ttk.Frame(audio)
        fila.grid(row=5, columnspan=2, sticky="ew", pady=(6, 0))
        ttk.Label(fila, text="Ajuste de sincronia del audio (ms):").pack(side="left")
        self.var_ajuste = tk.IntVar(value=self.cfg["ajuste_ms"])
        self.spin_ajuste = ttk.Spinbox(fila, from_=-1000, to=1000, increment=20,
                                       textvariable=self.var_ajuste, width=6,
                                       command=self.guardar)
        self.spin_ajuste.pack(side="right")

        # --- botones ---
        self.btn_bufer = ttk.Button(marco, text="Activar clips", style="Acento.TButton",
                                    command=self.alternar_bufer)
        self.btn_bufer.grid(row=3, column=0, sticky="ew", pady=(14, 4), padx=(0, 8))
        self.btn_clip = ttk.Button(marco, command=self.guardar_clip, state="disabled")
        self.btn_clip.grid(row=3, column=1, sticky="ew", pady=(14, 4), padx=(8, 0))
        self.btn_grab = ttk.Button(marco, style="Acento.TButton", command=self.alternar_grabacion)
        self.btn_grab.grid(row=4, column=0, sticky="ew", pady=4, padx=(0, 8))
        ttk.Button(marco, text="Abrir carpeta de videos",
                   command=self.abrir_carpeta).grid(row=4, column=1, sticky="ew", pady=4, padx=(8, 0))

        self.lbl_estado = ttk.Label(marco, text="Listo.", style="Tenue.TLabel", wraplength=640)
        self.lbl_estado.grid(row=5, columnspan=2, sticky="w", pady=(10, 0))

        self.registrar_teclas()
        if not keyboard:
            self.estado("Teclas rapidas desactivadas (falta 'keyboard').")
        self.pintar_extras()
        self.actualizar_botones()

        self.apps_lista = []
        self.actualizar_apps()
        root.protocol("WM_DELETE_WINDOW", self.cerrar)
        root.after(100, self.preparar)
        root.after(100, self.revisar_cola)

    # ---------- tema ----------
    def tema(self):
        return TEMAS.get(self.cfg.get("tema"), TEMAS["Oscuro"])

    def pintar_extras(self):
        """Colores de lo que ttk no pinta solo: la lista, los desplegables y la barra de titulo."""
        t = self.tema()
        self.lista.config(bg=t["campo"], fg=t["fg"], selectbackground=t["acento"],
                          selectforeground=t["acento_fg"], highlightbackground=t["borde"],
                          highlightcolor=t["acento"], disabledforeground=t["tenue"])
        for cmb in (self.cmb_fps, self.cmb_cal, self.cmb_res):
            try:
                pop = cmb.tk.eval(f"ttk::combobox::PopdownWindow {cmb}")
                cmb.tk.call(f"{pop}.f.l", "configure", "-background", t["campo"],
                            "-foreground", t["fg"], "-selectbackground", t["acento"],
                            "-selectforeground", t["acento_fg"])
            except tk.TclError:
                pass
        colorear_barra_titulo(self.root, t)

    def elegir_tema(self, nombre):
        self.cfg["tema"] = nombre
        guardar_config(self.cfg)
        aplicar_estilo(self.root, self.tema())
        self.pintar_extras()
        if self.ventana_tema:
            self.ventana_tema.destroy()
            self.ventana_tema = None
            self.abrir_temas()

    def abrir_temas(self):
        if self.ventana_tema and self.ventana_tema.winfo_exists():
            self.ventana_tema.lift()
            return
        actual = self.tema()
        v = tk.Toplevel(self.root, bg=actual["bg"], padx=16, pady=16)
        v.title("Elegir tema")
        v.resizable(False, False)
        v.transient(self.root)
        self.ventana_tema = v
        v.protocol("WM_DELETE_WINDOW", lambda: (v.destroy(), setattr(self, "ventana_tema", None)))
        ttk.Label(v, text="Elige un tema", style="Titulo.TLabel").grid(row=0, columnspan=4,
                                                                       sticky="w", pady=(0, 10))
        for i, (nombre, t) in enumerate(TEMAS.items()):
            elegido = nombre == self.cfg.get("tema", "Oscuro")
            borde = actual["acento"] if elegido else actual["borde"]
            tarjeta = tk.Frame(v, bg=t["bg"], highlightthickness=3 if elegido else 1,
                               highlightbackground=borde, cursor="hand2", padx=10, pady=8)
            tarjeta.grid(row=1 + i // 4, column=i % 4, padx=5, pady=5, sticky="nsew")
            tk.Label(tarjeta, text=nombre, bg=t["bg"], fg=t["fg"], font=("Segoe UI", 10, "bold"),
                     width=13, anchor="w").pack(anchor="w")
            muestras = tk.Frame(tarjeta, bg=t["bg"])
            muestras.pack(anchor="w", pady=(6, 0))
            for color in (t["acento"], t["panel"], t["fg"], t["tenue"]):
                tk.Frame(muestras, bg=color, width=22, height=14, highlightthickness=1,
                         highlightbackground=t["borde"]).pack(side="left", padx=(0, 4))
            boton = tk.Label(tarjeta, text="Grabar", bg=t["acento"], fg=t["acento_fg"],
                             font=("Segoe UI", 9, "bold"), padx=8, pady=2)
            boton.pack(anchor="w", pady=(8, 0))
            for w in (tarjeta, muestras, boton, *tarjeta.winfo_children(), *muestras.winfo_children()):
                w.bind("<Button-1>", lambda e, n=nombre: self.elegir_tema(n))
        colorear_barra_titulo(v, actual)

    # ---------- teclas ----------
    def registrar_teclas(self):
        if not keyboard:
            for b in (self.btn_tecla_clip, self.btn_tecla_grab):
                b.config(text="(no disponible)", state="disabled")
            return
        try:
            keyboard.unhook_all_hotkeys()
        except Exception:
            pass
        for accion, clave in (("clip", "tecla_clip"), ("grab", "tecla_grab")):
            try:
                keyboard.add_hotkey(self.cfg[clave], lambda a=accion: self.cola.put(a))
            except Exception:
                self.cfg[clave] = CONFIG_INICIAL[clave]
                keyboard.add_hotkey(self.cfg[clave], lambda a=accion: self.cola.put(a))
        self.btn_tecla_clip.config(text=tecla_bonita(self.cfg["tecla_clip"]))
        self.btn_tecla_grab.config(text=tecla_bonita(self.cfg["tecla_grab"]))

    def cambiar_tecla(self, cual):
        if not keyboard or self.capturando:
            return
        self.capturando = cual
        try:
            keyboard.unhook_all_hotkeys()
        except Exception:
            pass
        boton = self.btn_tecla_clip if cual == "tecla_clip" else self.btn_tecla_grab
        boton.config(text="Presiona...")
        self.estado("Presiona la tecla o combinacion nueva (Esc para cancelar).")

        def leer():
            try:
                combo = keyboard.read_hotkey(suppress=False)
            except Exception:
                combo = "esc"
            self.cola.put(("tecla", cual, combo))
        threading.Thread(target=leer, daemon=True).start()

    def tecla_leida(self, cual, combo):
        self.capturando = None
        otra = "tecla_grab" if cual == "tecla_clip" else "tecla_clip"
        if combo in ("esc", "escape", ""):
            self.estado("Cambio de tecla cancelado.")
        elif combo == self.cfg[otra]:
            self.estado(f"{tecla_bonita(combo)} ya se usa para la otra accion. Elige otra.")
        else:
            self.cfg[cual] = combo
            guardar_config(self.cfg)
            self.estado(f"Nueva tecla guardada: {tecla_bonita(combo)}")
        self.registrar_teclas()
        self.actualizar_botones()

    # ---------- utilidades ----------
    def estado(self, texto):
        self.lbl_estado.config(text=texto)

    def preparar(self):
        if not shutil.which("ffmpeg"):
            messagebox.showerror(APP, "No encontre FFmpeg.\nEjecuta primero 'instalar.bat' "
                                      "y vuelve a abrir GrabaClip.")
            self.root.destroy()
            return
        self.encoder = detectar_encoder()
        self.lbl_enc.config(text="Codificando con: " + NOMBRES[self.encoder])
        os.makedirs(CARPETA_SALIDA, exist_ok=True)
        if not os.path.exists(AUDIOCAP):
            self.estado("Falta audiocap.exe en la carpeta: se grabara sin audio.")

    def actualizar_apps(self):
        marcadas = [a.lower() for a in self.cfg["apps"]]
        apps = apps_con_sonido()
        for a in self.cfg["apps"]:  # las guardadas aparecen aunque no esten abiertas
            if a.lower() not in [x.lower() for x in apps]:
                apps.append(a)
        apps.sort(key=str.lower)
        self.apps_lista = apps
        self.lista.delete(0, "end")
        for i, exe in enumerate(apps):
            self.lista.insert("end", "  " + nombre_bonito(exe))
            if exe.lower() in marcadas:
                self.lista.selection_set(i)
        if not apps:
            self.lista.insert("end", "  (abre Discord, Spotify o tu juego y pulsa Actualizar)")

    def guardar(self):
        try:
            self.cfg["duracion"] = int(self.var_dur.get())
            self.cfg["ajuste_ms"] = int(self.var_ajuste.get())
        except (tk.TclError, ValueError):
            pass
        self.cfg["fps"] = self.var_fps.get()
        self.cfg["calidad"] = self.var_cal.get()
        self.cfg["resolucion"] = self.var_res.get()
        self.cfg["mic"] = bool(self.var_mic.get())
        apps = getattr(self, "apps_lista", [])
        self.cfg["apps"] = [apps[i] for i in self.lista.curselection() if i < len(apps)]
        guardar_config(self.cfg)

    def revisar_cola(self):
        while not self.cola.empty():
            accion = self.cola.get()
            if isinstance(accion, tuple) and accion[0] == "tecla":
                self.tecla_leida(accion[1], accion[2])
            elif self.capturando:
                pass
            elif accion == "clip":
                self.guardar_clip()
            elif accion == "grab":
                self.alternar_grabacion()
        if self.bufer and not self.bufer.viva():
            self.bufer.cerrar_audio()
            self.bufer = None
            self.actualizar_botones()
            self.estado("El bufer de clips se detuvo por un error (ver logs).")
        if self.grab and not self.grab.viva():
            self.grab.cerrar_audio()
            self.grab = None
            self.actualizar_botones()
            self.estado("La grabacion se detuvo por un error (ver logs).")
        self.root.after(100, self.revisar_cola)

    def actualizar_botones(self):
        activo = self.bufer is not None
        self.btn_bufer.config(text="Desactivar clips" if activo else "Activar clips")
        tc = tecla_bonita(self.cfg["tecla_clip"])
        tg = tecla_bonita(self.cfg["tecla_grab"])
        self.btn_clip.config(state="normal" if activo else "disabled",
                             text=f"Guardar clip  ({tc})")
        self.btn_grab.config(text=f"Detener grabacion  ({tg})" if self.grab
                             else f"Empezar a grabar  ({tg})")
        ocupado = activo or self.grab is not None
        estado = "disabled" if ocupado else "normal"
        for w in (self.spin_dur, self.chk_mic, self.btn_actualizar, self.spin_ajuste):
            w.config(state=estado)
        self.lista.config(state=estado)
        for cmb in (self.cmb_fps, self.cmb_cal, self.cmb_res):
            cmb.config(state="disabled" if ocupado else "readonly")

    def abrir_carpeta(self):
        os.makedirs(CARPETA_SALIDA, exist_ok=True)
        os.startfile(CARPETA_SALIDA)

    # ---------- clips ----------
    def alternar_bufer(self):
        if self.bufer:
            self.bufer.detener()
            self.bufer = None
            self.estado("Clips desactivados.")
        else:
            self.guardar()
            shutil.rmtree(CARPETA_BUFER, ignore_errors=True)
            os.makedirs(CARPETA_BUFER, exist_ok=True)
            fps = int(self.var_fps.get())
            trozos = self.cfg["duracion"] // SEG + 3
            salida = os.path.join(CARPETA_BUFER, "seg%04d.ts")
            self.bufer = Sesion(fps, self.encoder, self.cfg,
                                ["-f", "segment", "-segment_time", str(SEG),
                                 "-segment_wrap", str(trozos), "-reset_timestamps", "1",
                                 "-segment_format", "mpegts", salida],
                                "bufer.log")
            self.estado(f"Clips activos: {tecla_bonita(self.cfg['tecla_clip'])} guarda los ultimos {self.cfg['duracion']} s. "
                        f"Pistas: {', '.join(self.bufer.pistas) or 'ninguna'}{self.bufer.aviso}")
        self.actualizar_botones()

    def guardar_clip(self):
        if not self.bufer:
            self.estado("Activa los clips primero.")
            return
        trozos = sorted(glob.glob(os.path.join(CARPETA_BUFER, "*.ts")), key=os.path.getmtime)
        trozos = trozos[:-1]  # el ultimo todavia se esta escribiendo
        necesarios = max(1, self.cfg["duracion"] // SEG)
        trozos = trozos[-necesarios:]
        if not trozos:
            self.estado("Aun no hay suficiente video, espera unos segundos.")
            return
        lista = os.path.join(CARPETA_BUFER, "lista.txt")
        with open(lista, "w", encoding="utf-8") as f:
            for t in trozos:
                f.write("file '" + t.replace("\\", "/").replace("'", "'\\''") + "'\n")
        destino = os.path.join(CARPETA_SALIDA, f"clip_{marca_tiempo()}.mp4")
        args = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-f", "concat", "-safe", "0", "-i", lista, "-map", "0", "-c", "copy"]
        if self.bufer.pistas:
            args += ["-bsf:a", "aac_adtstoasc"] + metadatos(self.bufer.pistas)
        args += ["-movflags", "+faststart", destino]
        r = correr(args)
        if r.returncode == 0:
            self.estado("Clip guardado: " + os.path.basename(destino))
        else:
            self.estado("No se pudo guardar el clip.")
            os.makedirs(CARPETA_LOGS, exist_ok=True)
            with open(os.path.join(CARPETA_LOGS, "clip.log"), "wb") as f:
                f.write(r.stderr)

    # ---------- grabacion normal ----------
    def alternar_grabacion(self):
        if self.grab:
            self.grab.detener()
            self.grab = None
            self.estado("Grabacion guardada: " + os.path.basename(self.archivo_grab))
        else:
            self.guardar()
            fps = int(self.var_fps.get())
            self.archivo_grab = os.path.join(CARPETA_SALIDA, f"grabacion_{marca_tiempo()}.mp4")
            self.grab = Sesion(fps, self.encoder, self.cfg,
                               ["-movflags", "+faststart", self.archivo_grab], "grabacion.log")
            self.estado(f"Grabando... ({tecla_bonita(self.cfg['tecla_grab'])} para detener). "
                        f"Pistas: {', '.join(self.grab.pistas) or 'ninguna'}{self.grab.aviso}")
        self.actualizar_botones()

    def cerrar(self):
        for s in (self.grab, self.bufer):
            if s:
                s.detener()
        self.guardar()
        if keyboard:
            keyboard.unhook_all()
        self.root.destroy()


if __name__ == "__main__":
    raiz = tk.Tk()
    App(raiz)
    raiz.mainloop()
