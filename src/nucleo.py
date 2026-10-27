"""
GrabaClip - motor de grabacion (sin interfaz).
Lo usan grabaclip.py (interfaz moderna) y grabaclip_clasico.py (respaldo).
"""
import os
import sys
import glob
import json
import re
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
CARPETA_PREDETERMINADA = os.path.join(os.path.expanduser("~"), "Videos", APP)
CARPETA_SALIDA = CARPETA_PREDETERMINADA  # se cambia con usar_carpeta()


def carpeta_valida(ruta):
    """(ok, motivo): la carpeta existe (o se puede crear) y se puede escribir en ella."""
    try:
        os.makedirs(ruta, exist_ok=True)
        prueba = os.path.join(ruta, ".grabaclip_prueba")
        with open(prueba, "w") as f:
            f.write("ok")
        os.remove(prueba)
        return True, ""
    except Exception as ex:
        return False, f"No se puede guardar en esa carpeta ({ex.__class__.__name__})."


def usar_carpeta(ruta):
    """Cambia la carpeta donde se guardan los videos ('' = la predeterminada)."""
    global CARPETA_SALIDA
    CARPETA_SALIDA = os.path.abspath(ruta) if ruta else CARPETA_PREDETERMINADA
CARPETA_BUFER = os.path.join(tempfile.gettempdir(), APP + "_bufer")
CARPETA_LOGS = os.path.join(CARPETA_APP, "logs")
SEG = 2  # segundos que dura cada trocito del bufer
SIN_VENTANA = 0x08000000 if sys.platform == "win32" else 0
# prioridad "por debajo de lo normal": el juego siempre va primero
BAJA_PRIORIDAD = (0x00004000 | SIN_VENTANA) if sys.platform == "win32" else 0
# se rellena al abrir: si la GPU puede capturar y comprimir sin pasar por el procesador
MODO_GPU = {"directo": False, "escala": False, "ventana": False, "motivo_ventana": ""}
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
    if encoder == "av1_nvenc":
        # AV1: la escala de calidad es otra (0-63); +8 da una imagen parecida con ~35 % menos peso
        return ["-c:v", "av1_nvenc", "-preset", "p5" if q <= 19 else "p4", "-rc", "vbr",
                "-cq", str(q + 8), "-b:v", "0", "-spatial-aq", "1"]
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
    "av1_nvenc": "GPU NVIDIA (NVENC AV1)",
}
# variante AV1 de cada codificador (por ahora solo NVIDIA: RTX 40 o más nueva)
AV1 = {"h264_nvenc": "av1_nvenc"}


def _codec_de(ruta):
    try:
        r = correr(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_name",
                    "-of", "csv=p=0", ruta], timeout=15)
        return r.stdout.decode("utf-8", "replace").strip()
    except Exception:
        return ""


def probar_av1(encoder):
    """(funciona, motivo, contenedor). Prueba AV1 como lo usa el búfer. El contenedor es "mpegts"
    si este FFmpeg sabe meter AV1 en MPEG-TS (y entonces también sirve el búfer en RAM), o
    "matroska" si no (los trocitos del búfer en disco se guardan como .mkv)."""
    av1 = AV1.get(encoder)
    if not av1:
        return False, "AV1 por ahora solo funciona con tarjetas NVIDIA RTX 40 o más nuevas.", ""
    sin_tarjeta = "Tu tarjeta no puede comprimir en AV1 (hace falta una NVIDIA RTX 40 o más nueva)."
    os.makedirs(CARPETA_BUFER, exist_ok=True)
    for contenedor, ext in (("mpegts", "ts"), ("matroska", "mkv")):
        ruta = os.path.join(CARPETA_BUFER, f"prueba_av1.{ext}")
        try:
            r = correr(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                        "-f", "lavfi", "-i", "color=black:s=1280x720:r=30",
                        "-frames:v", "10", "-c:v", av1, "-f", contenedor, ruta], timeout=20)
        except Exception as ex:
            return False, str(ex)[:140], ""
        if r.returncode != 0:
            return False, sin_tarjeta, ""
        ok = _codec_de(ruta) == "av1"
        try:
            os.remove(ruta)
        except OSError:
            pass
        if ok:
            return True, "", contenedor
    return False, "Tu FFmpeg no puede guardar AV1 en el búfer.", ""


CONFIG_INICIAL = {"duracion": 30, "fps": "60", "calidad": "Alta", "resolucion": "Original",
                  "mic": True, "apps": [], "ajuste_ms": 0,
                  "tecla_clip": "f9", "tecla_grab": "f10", "tecla_activar": "f8",
                  "tecla_captura": "f7", "tecla_marca": "f6",
                  "tecla_clip_largo": "shift+f9", "tecla_mic": "ctrl+alt+m", "codec": "h264", "bufer_ram": False, "duracion_larga": 120, "tecla_ventana": "ctrl+shift+g",
                  "por_juego_cfg": {}, "vista_previa": True, "clip_al_cerrar": False, "idioma": "auto",
                  "perfil": "completo", "perfil_elegido": False, "tutorial_visto": False,
                  "temas_propios": {}, "esquinas": "normales", "tamano_texto": "normal",
                  "avisos": {}, "funciones": {"clips": True, "grabar": True, "capturas": True, "voz": True,
                                "overlay": True, "discord": True, "estadisticas": True}, "tema": "Carmesí", "ui_version": 6,
                  "iniciar_con_windows": False, "clips_al_abrir": False, "sonido_clip": True,
                  "por_juego": True, "encoder": "auto",
                  "captura": "juego", "ventana_exe": "", "escritorio_sin_juego": True, "monitor": 0,
                  "quitar_mudas": True, "orden_pistas": [],
                  "overlay": True, "overlay_indicador": True, "overlay_aviso": True, "overlay_pos": "der",
                  "voz": False, "voz_clip": ["jarvis sácale clip", "jarvis clipea eso"], "voz_grabar": [],
                  "voz_clips": [], "voz_idioma": "", "voz_confianza": 0.6, "carpeta": "", "avisar_updates": False,
                  "bandeja": True, "bandeja_aviso_visto": False,
                  "modo_audio": "una", "discord": False, "discord_juego": True,
                  "limite_gb": 0, "limite_grabaciones": False}

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
    # captura de una sola ventana (Windows.Graphics.Capture, FFmpeg 8+)
    ventana = "gfxcapture=monitor_idx=0:max_framerate=30:resize_mode=scale_aspect,fps=30"
    MODO_GPU["ventana"] = prueba(ventana + (_sufijo_gpu(encoder) if MODO_GPU["directo"]
                                            else ",hwdownload,format=bgra,format=yuv420p"))
    MODO_GPU["motivo_ventana"] = "" if MODO_GPU["ventana"] else \
        "Tu Windows o tu FFmpeg no permiten capturar una sola ventana (necesita Windows 10 1903+ y FFmpeg 8)."
    return MODO_GPU


def monitores():
    """Lista de pantallas [(ancho, alto)] en pixeles reales, en el orden de Windows."""
    if sys.platform != "win32":
        return []
    try:
        import ctypes
        from ctypes import wintypes
        u32 = ctypes.windll.user32
        anterior = None
        try:
            anterior = u32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))  # pixeles reales
        except Exception:
            pass
        lista = []
        Proc = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p,
                                  ctypes.POINTER(wintypes.RECT), ctypes.c_void_p)

        def cada(hmon, hdc, rect, dato):
            r = rect.contents
            lista.append((r.right - r.left, r.bottom - r.top))
            return 1
        u32.EnumDisplayMonitors(None, None, Proc(cada), None)
        if anterior:
            try:
                u32.SetThreadDpiAwarenessContext(ctypes.c_void_p(anterior))
            except Exception:
                pass
        return lista
    except Exception:
        return []


def tamano_ventana(hwnd):
    """(ancho, alto) del contenido de una ventana en pixeles reales, o (0, 0)."""
    try:
        import ctypes
        from ctypes import wintypes
        u32 = ctypes.windll.user32
        try:
            u32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
        except Exception:
            pass
        r = wintypes.RECT()
        if u32.GetClientRect(ctypes.c_void_p(hwnd), ctypes.byref(r)):
            return r.right - r.left, r.bottom - r.top
    except Exception:
        pass
    return 0, 0


def filtro_video(encoder, fps, alto_deseado, fuente=None):
    """fuente: {"tipo": "monitor", "idx": 0} o {"tipo": "ventana", "hwnd": 1234}."""
    fuente = fuente or {"tipo": "monitor", "idx": 0}
    if fuente["tipo"] == "ventana" and MODO_GPU["ventana"]:
        base = (f"gfxcapture=hwnd={int(fuente['hwnd'])}:max_framerate={fps}:capture_cursor=1"
                f":resize_mode=scale_aspect,fps={fps}")
        ancho_m, alto_m = tamano_ventana(fuente["hwnd"])
        # el tamano del video queda fijo; si la ventana cambia se ajusta con barras negras
        ancho_m, alto_m = ancho_m - ancho_m % 2, alto_m - alto_m % 2
    else:
        idx = int(fuente.get("idx", 0))
        base = f"ddagrab=output_idx={idx}:framerate={fps}:draw_mouse=1"
        pantallas = monitores()
        ancho_m, alto_m = pantallas[idx] if idx < len(pantallas) else alto_monitor()
    reducir = bool(alto_deseado) and (not alto_m or alto_m > alto_deseado)
    if MODO_GPU["directo"] and (not reducir or (MODO_GPU["escala"] and alto_m)):
        if reducir:
            ancho = round(ancho_m * alto_deseado / alto_m / 2) * 2
            base += f",scale_d3d11=width={ancho}:height={alto_deseado}"
        return base + _sufijo_gpu(encoder)
    escala = f"scale=-2:'min(ih,{alto_deseado})':flags=bicubic," if alto_deseado else ""
    return base + f",hwdownload,format=bgra,{escala}format=yuv420p"


# Perfiles: qué partes de GrabaClip se usan. Lo apagado no se carga ni registra teclas.
# Avisos por acción: si cada una muestra el overlay y/o toca su sonido (Ajustes → General)
EVENTOS_AVISO = ["clip", "grabacion", "captura", "marca", "clips", "mic"]
_AVISO_DEF = {"clips": {"overlay": False, "sonido": True}}  # la pastilla del indicador ya lo muestra


def aviso_evento(cfg, evento):
    base = dict(_AVISO_DEF.get(evento, {"overlay": True, "sonido": True}))
    guardado = (cfg.get("avisos") or {}).get(evento)
    if isinstance(guardado, dict):
        for k in ("overlay", "sonido"):
            if isinstance(guardado.get(k), bool):
                base[k] = guardado[k]
    return base


FUNCIONES = ["clips", "grabar", "capturas", "voz", "overlay", "discord", "estadisticas"]
PERFILES = {
    "completo": {"funciones": dict.fromkeys(FUNCIONES, True), "ajustes": {}},
    "esencial": {"funciones": {"clips": True, "grabar": True, "capturas": True, "voz": False, "overlay": False,
                               "discord": False, "estadisticas": False},
                 "ajustes": {"vista_previa": False}},
    "clips": {"funciones": {"clips": True, "grabar": False, "capturas": False, "voz": False, "overlay": True,
                            "discord": False, "estadisticas": False},
              "ajustes": {"vista_previa": False}},
    "grabacion": {"funciones": {"clips": False, "grabar": True, "capturas": False, "voz": False, "overlay": True,
                                "discord": False, "estadisticas": False},
                  "ajustes": {"vista_previa": False, "clips_al_abrir": False}},
}


def temas_todos(cfg):
    """Los temas de fábrica más los que creó el usuario."""
    propios = {k: v for k, v in (cfg.get("temas_propios") or {}).items() if isinstance(v, dict)}
    return {**TEMAS, **propios}


def _luz(hexa):
    r, g, b = (int(hexa[i:i + 2], 16) / 255 for i in (1, 3, 5))
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in (r, g, b)]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def tema_desde_colores(c):
    """Completa un tema propio: color del texto sobre el acento y si es oscuro o claro."""
    t = {k: c[k] for k in ("bg", "panel", "campo", "fg", "tenue", "acento", "borde")}
    t["acento_fg"] = "#000000" if _luz(t["acento"]) > 0.45 else "#ffffff"
    t["oscuro"] = _luz(t["bg"]) < 0.3
    return t


def captura_pantalla(fuente, destino):
    """Guarda una imagen PNG de lo que se ve ahora (ventana del juego o pantalla)."""
    fuente = fuente or {"tipo": "monitor", "idx": 0}
    if fuente.get("tipo") == "ventana" and MODO_GPU["ventana"]:
        base = f"gfxcapture=hwnd={int(fuente['hwnd'])}:max_framerate=30:capture_cursor=0"
    else:
        base = f"ddagrab=output_idx={int(fuente.get('idx', 0))}:framerate=30:draw_mouse=0"
    # el primer cuadro de la captura a veces sale vacío: se toma el tercero
    r = correr(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                base + ",hwdownload,format=bgra,select=gte(n\\,2)", "-frames:v", "1",
                "-update", "1", destino], timeout=15)
    return r.returncode == 0 and os.path.exists(destino), r.stderr.decode("utf-8", "replace")[-500:]


def capitulos(ruta, marcas):
    """Mete las marcas como capítulos del MP4 (se ven en VLC, DaVinci, etc.), sin recomprimir."""
    if not marcas or not os.path.exists(ruta):
        return False
    try:
        r = correr(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", ruta], timeout=30)
        dur = float(r.stdout.decode().strip() or 0)
    except Exception:
        dur = 0
    marcas = sorted(m for m in marcas if 0 <= m < (dur or 1e9))
    if not marcas:
        return False
    texto = [";FFMETADATA1"]
    puntos = [0.0] + marcas if marcas[0] > 0.5 else marcas
    for i, ini in enumerate(puntos):
        fin = puntos[i + 1] if i + 1 < len(puntos) else (dur or ini + 1)
        titulo = "Inicio" if (i == 0 and puntos[0] == 0.0 and marcas[0] > 0.5) else f"Marca {marcas.index(ini) + 1}"
        texto += ["[CHAPTER]", "TIMEBASE=1/1000", f"START={int(ini * 1000)}", f"END={int(fin * 1000)}", f"title={titulo}"]
    meta = ruta + ".capitulos.txt"
    temporal = ruta + ".capitulos.mp4"
    try:
        with open(meta, "w", encoding="utf-8") as f:
            f.write("\n".join(texto) + "\n")
        r = correr(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", ruta, "-i", meta,
                    "-map", "0", "-map_metadata", "0", "-map_chapters", "1", "-c", "copy",
                    "-movflags", "+faststart", temporal], timeout=1800)
        if r.returncode == 0:
            os.replace(temporal, ruta)
            return True
    except Exception:
        pass
    finally:
        for x in (meta, temporal):
            try:
                os.remove(x)
            except OSError:
                pass
    return False


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
    if cfg.get("tema") not in temas_todos(cfg):
        cfg["tema"] = "Carmesí"
    if "modo_audio" not in guardado and guardado.get("apps"):
        cfg["modo_audio"] = "separadas"  # quien ya tenia apps en pista propia las conserva
    if cfg.get("modo_audio") not in ("una", "separadas"):
        cfg["modo_audio"] = "una"
    if cfg.get("carpeta") and os.path.isdir(cfg["carpeta"]):
        usar_carpeta(cfg["carpeta"])
    else:
        usar_carpeta("")  # la carpeta elegida no está (p. ej. disco desconectado): se usa la normal sin olvidarla
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

    def __init__(self, fps, encoder, cfg, salida_args, nombre_log, fuente=None, a_tuberia=False):
        """a_tuberia=True: el video sale por stdout (búfer en memoria RAM) en vez de a archivos."""
        self.fuente = fuente or {"tipo": "monitor", "idx": int(cfg.get("monitor", 0))}
        self.audio = None
        self.pistas = []  # nombres de las pistas de audio, en orden
        self.aviso = ""
        os.makedirs(CARPETA_LOGS, exist_ok=True)

        especies = ["sys"]
        nombres_entrada = ["Sistema"]
        if cfg["mic"]:
            especies.append("mic")
            nombres_entrada.append("Microfono")
        separadas = cfg.get("modo_audio", "una") == "separadas"
        for exe in (cfg["apps"] if separadas else []):
            especies.append("app:" + exe)
            nombres_entrada.append(nombre_bonito(exe))

        self.especies = especies
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

        filtro = filtro_video(encoder, fps, RESOLUCIONES.get(cfg["resolucion"], 0), self.fuente) + "[v]"
        mapas = ["-map", "[v]"]
        if self.audio:
            if cfg["mic"]:
                filtro += ";[0:a][1:a]amix=inputs=2:duration=longest:normalize=0[mezcla]"
            # cada pista posible: clave -> (lo que se mapea, nombre)
            disponibles = {"mezcla": ("[mezcla]" if cfg["mic"] else "0:a", "Mezcla")}
            for i in range(1, len(especies)):  # micro y apps (el "Sistema" ya esta en la mezcla)
                disponibles[clave_pista(especies[i])] = (f"{i}:a", nombres_entrada[i])
            if not separadas:  # todo el audio (juego, apps y micro) en una sola pista
                disponibles = {"mezcla": disponibles["mezcla"]}
            for clave in orden_pistas(cfg):
                if clave in disponibles:
                    mapa, nombre = disponibles[clave]
                    mapas += ["-map", mapa]
                    self.pistas.append(nombre)

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
            stdin=subprocess.PIPE, stdout=subprocess.PIPE if a_tuberia else subprocess.DEVNULL, stderr=self.log,
            creationflags=BAJA_PRIORIDAD, bufsize=0 if a_tuberia else -1)

    def viva(self):
        return self.ffmpeg.poll() is None

    def perdio_pantalla(self):
        """True si FFmpeg se cerro porque Windows le quito la captura de pantalla un momento
        (DXGI_ERROR_ACCESS_LOST 887a0026: cambio de resolucion, juego en pantalla completa
        exclusiva, ventana de permisos de administrador, Ctrl+Alt+Supr...). Se puede reintentar."""
        try:
            self.log.flush()
            with open(self.log.name, encoding="utf-8", errors="replace") as f:
                texto = f.read()[-4000:].lower()
        except Exception:
            return False
        return any(c in texto for c in ("887a0026", "887a0005", "887a0007", "acquirenextframe failed"))

    def silenciar_mic(self, mudo):
        """Silencia o reactiva el micrófono sin cortar nada (audiocap manda silencio)."""
        if not self.audio or "mic" not in self.especies or self.audio.poll() is not None:
            return
        try:
            self.audio.stdin.write(b"mute 1\n" if mudo else b"mute 0\n")
            self.audio.stdin.flush()
        except Exception:
            pass

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


def clave_pista(especie):
    """'mic' -> 'mic', 'app:Overwatch.exe' -> 'app:overwatch.exe'."""
    return especie.lower()


def orden_pistas(cfg):
    """Orden final de las pistas: el que eligio el usuario y despues las nuevas."""
    base = ["mezcla"] + (["mic"] if cfg.get("mic") else []) + ["app:" + e.lower() for e in cfg.get("apps", [])]
    elegido = [c for c in (cfg.get("orden_pistas") or []) if c in base]
    return elegido + [c for c in base if c not in elegido]


def quitar_pistas_mudas(ruta, pistas, umbral_db=-70.0, proteger="Mezcla"):
    """Quita del video las pistas de audio sin sonido (nunca la mezcla).
    Devuelve la lista de pistas que quedaron."""
    if len(pistas) <= 1:
        return pistas
    conservar = [i for i, n in enumerate(pistas) if n == proteger]
    for i in range(len(pistas)):
        if i in conservar:
            continue
        try:
            r = correr(["ffmpeg", "-hide_banner", "-nostats", "-i", ruta, "-map", f"0:a:{i}",
                        "-af", "volumedetect", "-f", "null", "-"], timeout=600)
            texto = r.stderr.decode("utf-8", "replace")
            m = re.search(r"max_volume:\s*(-?[\d.]+|-inf) dB", texto)
            pico = -999.0 if (not m or m.group(1) == "-inf") else float(m.group(1))
        except Exception:
            pico = 0.0  # ante la duda, se conserva
        if pico > umbral_db:
            conservar.append(i)
    conservar.sort()
    if len(conservar) == len(pistas):
        return pistas
    temporal = ruta + ".tmp.mp4"
    args = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", ruta, "-map", "0:v"]
    for i in conservar:
        args += ["-map", f"0:a:{i}"]
    nuevas = [pistas[i] for i in conservar]
    args += ["-c", "copy"] + metadatos(nuevas) + ["-movflags", "+faststart", temporal]
    r = correr(args, timeout=1800)
    if r.returncode != 0 or not os.path.exists(temporal):
        try:
            os.remove(temporal)
        except OSError:
            pass
        return pistas
    os.replace(temporal, ruta)
    return nuevas


def metadatos(pistas):
    args = []
    for i, nombre in enumerate(pistas):
        args += [f"-metadata:s:a:{i}", f"title={nombre}",
                 f"-metadata:s:a:{i}", f"handler_name={nombre}"]
    return args
