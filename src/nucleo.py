"""
GrabaClip - motor de grabacion (sin interfaz).
Lo usan grabaclip.py (interfaz moderna) y grabaclip_clasico.py (respaldo).
"""
import os
import sys
import glob
import json
import shutil
import tempfile
import datetime
import itertools
import threading
import subprocess

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
# prioridad "por debajo de lo normal": el juego siempre va primero
BAJA_PRIORIDAD = (0x00004000 | SIN_VENTANA) if sys.platform == "win32" else 0
# se rellena al abrir: si la GPU puede capturar y comprimir sin pasar por el procesador
MODO_GPU = {"directo": False, "escala": False}
CONTADOR = itertools.count()

# Calidad: numero mas bajo = mejor imagen y archivos mas grandes
CALIDADES = {
    "Baja": 30,
    "Media": 26,
    "Alta": 22,
    "Muy alta": 19,
    "Máxima": 16,
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
                  "tecla_clip": "f9", "tecla_grab": "f10", "tema": "Carmesí", "ui_version": 6,
                  "iniciar_con_windows": False, "clips_al_abrir": False, "sonido_clip": True,
                  "por_juego": True, "encoder": "auto"}

# ---------- temas ----------
# bg: fondo, panel: botones, campo: cajas de texto, tenue: texto secundario
TEMAS = {
    "Carmesí": dict(bg="#151518", panel="#202024", campo="#1a1a1e", fg="#ececef", tenue="#8e8e97",
                    acento="#c8243f", acento_fg="#ffffff", borde="#2e2e34", oscuro=True),
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


def colorear_barra_titulo(ventana, t, hwnd=None):
    """Windows 10/11: barra de titulo oscura o clara (y del color del tema en Windows 11)."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        if hwnd is None:
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


def tecla_bonita(combo):
    return "+".join(p.upper() if len(p) <= 3 else p.capitalize() for p in combo.split("+"))


def correr(args, **kw):
    return subprocess.run(args, capture_output=True, creationflags=BAJA_PRIORIDAD, **kw)


def alto_monitor():
    """Alto real en pixeles del monitor principal (sin el escalado de Windows)."""
    try:
        import ctypes
        hdc = ctypes.windll.user32.GetDC(0)
        ancho = ctypes.windll.gdi32.GetDeviceCaps(hdc, 118)  # DESKTOPHORZRES
        alto = ctypes.windll.gdi32.GetDeviceCaps(hdc, 117)   # DESKTOPVERTRES
        ctypes.windll.user32.ReleaseDC(0, hdc)
        return ancho, alto
    except Exception:
        return 0, 0


def _sufijo_gpu(encoder):
    return ",hwmap=derive_device=qsv,format=qsv" if encoder == "h264_qsv" else ""


def probar_gpu(encoder):
    """Comprueba si la captura puede ir directo de la pantalla al codificador de la GPU."""
    MODO_GPU["directo"] = MODO_GPU["escala"] = False
    if encoder == "libx264":
        return MODO_GPU

    def prueba(filtro):
        try:
            r = correr(["ffmpeg", "-hide_banner", "-loglevel", "error",
                        "-filter_complex", filtro + "[v]", "-map", "[v]", "-frames:v", "8",
                        "-c:v", encoder, "-f", "null", "-"], timeout=15)
            return r.returncode == 0
        except Exception:
            return False

    base = "ddagrab=output_idx=0:framerate=30"
    MODO_GPU["directo"] = prueba(base + _sufijo_gpu(encoder))
    if MODO_GPU["directo"]:
        MODO_GPU["escala"] = prueba(base + ",scale_d3d11=width=1280:height=720" + _sufijo_gpu(encoder))
    return MODO_GPU


def filtro_video(encoder, fps, alto_deseado):
    base = f"ddagrab=output_idx=0:framerate={fps}:draw_mouse=1"
    ancho_m, alto_m = alto_monitor()
    reducir = bool(alto_deseado) and (not alto_m or alto_m > alto_deseado)
    if MODO_GPU["directo"] and (not reducir or (MODO_GPU["escala"] and alto_m)):
        if reducir:
            ancho = round(ancho_m * alto_deseado / alto_m / 2) * 2
            base += f",scale_d3d11=width={ancho}:height={alto_deseado}"
        return base + _sufijo_gpu(encoder)
    escala = f"scale=-2:'min(ih,{alto_deseado})':flags=bicubic," if alto_deseado else ""
    return base + f",hwdownload,format=bgra,{escala}format=yuv420p"


CANDIDATOS = ["h264_nvenc", "h264_amf", "h264_qsv"]


def _motivo(encoder, error):
    """Explica en palabras simples por que un codificador no funciona."""
    e = error.lower()
    if encoder == "h264_nvenc":
        if "driver" in e and ("version" in e or "minimum" in e or "update" in e):
            return "Tu driver de NVIDIA es muy antiguo. Actualizalo desde la app de NVIDIA o nvidia.com."
        if "nvcuda" in e or "cannot load" in e or "no capable devices" in e or "no nvenc capable" in e:
            return "No se encontro una tarjeta NVIDIA compatible."
    if encoder == "h264_amf":
        if "amfrt" in e or "failed to open" in e or "dll" in e:
            return "No se encontro una tarjeta AMD compatible (o falta su driver)."
    if encoder == "h264_qsv":
        if "mfx" in e or "session" in e or "unsupported" in e or "device" in e:
            return "Intel QuickSync no esta disponible (sin grafica Intel o desactivada)."
    primera = next((l.strip() for l in error.splitlines() if l.strip()), "")
    return (primera[:140] or "No funciono en esta PC.")


# Codigos de Windows cuando un programa ni siquiera puede arrancar
CODIGOS_ARRANQUE = {
    0xC0E90002: ("Windows bloqueo FFmpeg (Control inteligente de aplicaciones). Desactivalo en "
                 "Seguridad de Windows > Control de aplicaciones y navegador."),
    0xC0000135: "Faltan archivos de FFmpeg. Vuelve a descomprimir GrabaClip completo.",
    0xC000007B: "Los archivos de FFmpeg estan danados o bloqueados. Vuelve a descomprimir GrabaClip "
                "(desbloquea el zip antes).",
    0xC0000022: "Windows o el antivirus no dejan ejecutar FFmpeg (acceso denegado).",
    0xC0000005: "FFmpeg se cerro de golpe al arrancar.",
}


def _codigo(r):
    return r.returncode & 0xFFFFFFFF


def estado_ffmpeg():
    """(funciona, motivo): comprueba que FFmpeg pueda arrancar en esta PC."""
    try:
        r = correr(["ffmpeg", "-hide_banner", "-version"], timeout=20)
    except FileNotFoundError:
        return False, "No se encontro FFmpeg. Vuelve a descomprimir GrabaClip completo."
    except Exception as ex:
        return False, f"No se pudo ejecutar FFmpeg: {ex}"
    if r.returncode == 0:
        return True, ""
    c = _codigo(r)
    return False, CODIGOS_ARRANQUE.get(c, f"FFmpeg no pudo arrancar (codigo 0x{c:08X}).")


def probar_encoders():
    """Prueba cada codificador. Devuelve {encoder: (funciona, motivo)}."""
    resultado = {}
    for enc in CANDIDATOS + ["libx264"]:
        try:
            r = correr(["ffmpeg", "-hide_banner", "-loglevel", "error",
                        "-f", "lavfi", "-i", "color=black:s=640x360:r=30",
                        "-frames:v", "5", "-c:v", enc, "-f", "null", "-"], timeout=20)
            ok = r.returncode == 0
            err = r.stderr.decode("utf-8", "replace")
            if not ok and not err.strip():
                c = _codigo(r)
                err = CODIGOS_ARRANQUE.get(c, f"FFmpeg termino con el codigo 0x{c:08X} sin dar detalles.")
                resultado[enc] = (False, err)
                continue
        except Exception as ex:
            ok, err = False, str(ex)
        resultado[enc] = (ok, "" if ok else _motivo(enc, err))
    return resultado


def elegir_encoder(resultados, preferido):
    """El preferido si funciona; si no (o si es 'auto'), la primera GPU que funcione."""
    if preferido in resultados and resultados[preferido][0]:
        return preferido
    for enc in CANDIDATOS:
        if resultados.get(enc, (False,))[0]:
            return enc
    return "libx264"


def detectar_encoder():
    """Prueba los codificadores por hardware y usa el primero que funcione."""
    return elegir_encoder(probar_encoders(), "auto")


def cargar_config():
    cfg = dict(CONFIG_INICIAL)
    guardado = {}
    try:
        with open(ARCHIVO_CONFIG, encoding="utf-8") as f:
            guardado = json.load(f)
    except Exception:
        pass
    cfg.update(guardado)
    if guardado and int(guardado.get("ui_version") or 0) < 6:  # el nuevo diseno estrena el tema Carmesi
        cfg["tema"] = "Carmesí"
    cfg["ui_version"] = 6
    if cfg.get("calidad") == "Maxima":
        cfg["calidad"] = "Máxima"
    if cfg.get("tema") not in TEMAS:
        cfg["tema"] = "Carmesí"
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

        filtro = filtro_video(encoder, fps, RESOLUCIONES.get(cfg["resolucion"], 0)) + "[v]"
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
            creationflags=BAJA_PRIORIDAD)

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
