"""Recortar clips dentro de GrabaClip.

- ServidorVideo: un servidor HTTP mínimo, solo en 127.0.0.1 y con una clave al azar, para que el
  reproductor de la ventana pueda abrir el video (con saltos/seek, por eso soporta Range).
- recortar(): corta exacto al décimo de segundo volviendo a codificar con el mismo codificador
  que usa GrabaClip (GPU si hay), conservando todas las pistas de audio y sus nombres.
"""
import os
import re
import secrets
import subprocess
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import nucleo as N


class ServidorVideo:
    def __init__(self, carpeta_mini=None):
        self._clave = secrets.token_urlsafe(16)
        self._permitidos = {}  # id -> ruta
        self._mini = carpeta_mini  # miniaturas de la biblioteca (en vez de mandarlas en base64)
        self._srv = None

    def _arrancar(self):
        if self._srv:
            return
        dueno = self

        class Manejador(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _miniatura(self, nombre):
                if os.path.basename(nombre) != nombre or not nombre.lower().endswith(".jpg"):
                    self.send_error(404)
                    return
                try:
                    with open(os.path.join(dueno._mini, nombre), "rb") as f:
                        datos = f.read()
                except OSError:
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(datos)))
                self.send_header("Cache-Control", "max-age=31536000, immutable")
                self.end_headers()
                try:
                    self.wfile.write(datos)
                except OSError:
                    pass

            def do_GET(self):
                partes = urllib.parse.urlparse(self.path).path.strip("/").split("/")
                if len(partes) == 3 and partes[0] == dueno._clave and partes[1] == "m" and dueno._mini:
                    self._miniatura(urllib.parse.unquote(partes[2]))
                    return
                if len(partes) != 2 or partes[0] != dueno._clave or partes[1] not in dueno._permitidos:
                    self.send_error(404)
                    return
                ruta = dueno._permitidos[partes[1]]
                try:
                    tam = os.path.getsize(ruta)
                    f = open(ruta, "rb")
                except OSError:
                    self.send_error(404)
                    return
                with f:
                    inicio, fin = 0, tam - 1
                    rango = self.headers.get("Range")
                    m = re.match(r"bytes=(\d*)-(\d*)", rango or "")
                    if m and (m.group(1) or m.group(2)):
                        if m.group(1):
                            inicio = int(m.group(1))
                            fin = int(m.group(2)) if m.group(2) else tam - 1
                        else:
                            inicio = max(0, tam - int(m.group(2)))
                        fin = min(fin, tam - 1)
                        self.send_response(206)
                        self.send_header("Content-Range", f"bytes {inicio}-{fin}/{tam}")
                    else:
                        self.send_response(200)
                    largo = fin - inicio + 1
                    self.send_header("Content-Type", "video/mp4")
                    self.send_header("Accept-Ranges", "bytes")
                    self.send_header("Content-Length", str(largo))
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    f.seek(inicio)
                    falta = largo
                    try:
                        while falta > 0:
                            trozo = f.read(min(1 << 20, falta))
                            if not trozo:
                                break
                            self.wfile.write(trozo)
                            falta -= len(trozo)
                    except (ConnectionError, OSError):
                        pass  # el reproductor cerro la conexion al saltar

        self._srv = ThreadingHTTPServer(("127.0.0.1", 0), Manejador)
        self._srv.daemon_threads = True
        threading.Thread(target=self._srv.serve_forever, daemon=True).start()

    def url(self, ruta, lugar="editor"):
        """Un video permitido por 'lugar' (el editor y la vista previa de la biblioteca)."""
        self._arrancar()
        ident = secrets.token_urlsafe(8)
        self._lugares = getattr(self, "_lugares", {})
        self._lugares[lugar] = (ident, ruta)
        self._permitidos = {i: r for i, r in self._lugares.values()}
        return f"http://127.0.0.1:{self._srv.server_address[1]}/{self._clave}/{ident}"

    def url_mini(self, nombre):
        self._arrancar()
        return f"http://127.0.0.1:{self._srv.server_address[1]}/{self._clave}/m/{urllib.parse.quote(nombre)}"

    def olvidar(self, lugar=None):
        self._lugares = getattr(self, "_lugares", {})
        if lugar:
            self._lugares.pop(lugar, None)
        else:
            self._lugares.clear()
        self._permitidos = {i: r for i, r in self._lugares.values()}


def _nombre_libre(carpeta, base, sufijo="_recorte", ext=".mp4"):
    n = 1
    while True:
        nombre = f"{base}{sufijo}{'' if n == 1 else n}{ext}"
        if not os.path.exists(os.path.join(carpeta, nombre)):
            return os.path.join(carpeta, nombre)
        n += 1


def pistas_video(ruta):
    """Nombres de las pistas de audio, en orden (los que puso GrabaClip: Mezcla, Micrófono…)."""
    import json
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
                            "stream=index:stream_tags=handler_name,title", "-of", "json", ruta],
                           capture_output=True, creationflags=N.SIN_VENTANA, timeout=30)
        datos = json.loads(r.stdout or b"{}")
    except Exception:
        return []
    nombres = []
    for k, st in enumerate(datos.get("streams", [])):
        t = st.get("tags") or {}
        nombre = t.get("title") or t.get("handler_name") or ""
        if not nombre or nombre.lower() in ("soundhandler", "sound handler"):
            nombre = f"Pista {k + 1}"
        nombres.append(nombre)
    return nombres


VERTICAL = "crop=trunc(ih*9/16/2)*2:ih,scale=1080:1920:flags=lanczos,setsar=1"
VELOCIDADES = (1.0, 0.5, 0.25)

# ---------- textos dibujados en el video (marca de agua, títulos del resumen) ----------
# drawtext necesita un archivo de fuente y es delicado con ":" y "\" de las rutas de Windows,
# así que FFmpeg corre dentro de una carpeta temporal con la fuente copiada y los textos en
# archivos (textfile=), todo con nombres simples y relativos.
CARPETA_TEXTOS = os.path.join(N.CARPETA_BUFER, "textos")
FUENTES = ("segoeuib.ttf", "arialbd.ttf", "seguisb.ttf", "arial.ttf")


def _preparar_textos(textos):
    """textos: {nombre_archivo: texto}. Devuelve la carpeta (para cwd) o lanza error si no hay fuente."""
    import shutil
    os.makedirs(CARPETA_TEXTOS, exist_ok=True)
    fuente = os.path.join(CARPETA_TEXTOS, "fuente.ttf")
    if not os.path.exists(fuente):
        windir = os.environ.get("WINDIR", r"C:\Windows")
        for f in FUENTES:
            origen = os.path.join(windir, "Fonts", f)
            if os.path.exists(origen):
                shutil.copyfile(origen, fuente)
                break
        else:
            raise RuntimeError("No encontré una fuente de Windows para escribir el texto")
    for nombre, texto in textos.items():
        with open(os.path.join(CARPETA_TEXTOS, nombre), "w", encoding="utf-8") as f:
            f.write(texto.replace("\r", "").strip()[:80])
    return CARPETA_TEXTOS


def _drawtext(archivo, x, y, tam, extra=""):
    return (f"drawtext=fontfile=fuente.ttf:textfile={archivo}:fontcolor=white@0.9:fontsize={tam}"
            f":x={x}:y={y}:shadowcolor=black@0.7:shadowx=2:shadowy=2" + extra)


def filtro_marca(texto):
    """Marca de agua abajo a la derecha (tamaño relativo a la altura del video)."""
    return _drawtext("marca.txt", "w-tw-h/28", "h-th-h/28", "h/26")


def _atempo(velocidad):
    """atempo solo acepta 0.5..2: 0.25 se hace con dos de 0.5."""
    if velocidad >= 0.5:
        return f"atempo={velocidad:g}"
    return "atempo=0.5,atempo=" + f"{velocidad / 0.5:g}"


def recortar(ruta, inicio, fin, encoder, calidad, progreso=None, pistas=None, vertical=False,
             velocidad=1.0, marca=""):
    """Crea una copia junto al original: recortada, con solo las pistas elegidas
    (None = todas), y si se pide en vertical 9:16, en cámara lenta y con una marca de agua."""
    inicio, fin = max(0.0, float(inicio)), float(fin)
    dur = fin - inicio
    if dur < 0.5:
        raise ValueError("El recorte tiene que durar al menos medio segundo")
    velocidad = float(velocidad or 1)
    if velocidad not in VELOCIDADES:
        velocidad = 1.0
    marca = (marca or "").strip()
    carpeta = os.path.dirname(ruta)
    sufijo = "_vertical" if vertical else "_lento" if velocidad < 1 else "_recorte"
    salida = _nombre_libre(carpeta, os.path.splitext(os.path.basename(ruta))[0], sufijo)
    cwd = _preparar_textos({"marca.txt": marca}) if marca else None
    filtros_v = ([VERTICAL] if vertical else []) + ([f"setpts=PTS/{velocidad:g}"] if velocidad < 1 else []) \
        + ([filtro_marca(marca)] if marca else [])
    temporal = salida + ".parcial.mp4"
    if pistas is None:
        mapas_audio = ["-map", "0:a?"]
    else:
        mapas_audio = []
        for i in pistas:
            mapas_audio += ["-map", f"0:a:{int(i)}"]

    def intentar(enc):
        args = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-ss", f"{inicio:.3f}", "-t", f"{dur:.3f}", "-i", ruta, "-map", "0:v:0"] + mapas_audio
        if filtros_v:
            args += ["-vf", ",".join(filtros_v)]
        args += N.args_encoder(enc, calidad)
        args += ["-pix_fmt", "yuv420p"]
        if mapas_audio:
            if velocidad < 1:
                args += ["-af", _atempo(velocidad)]
            args += ["-c:a", "aac", "-b:a", "160k"]
        args += ["-map_metadata", "0", "-movflags", "+faststart", temporal]
        return _ffmpeg(args, dur / velocidad, progreso, cwd)

    codigo, err = intentar(encoder or "libx264")
    if codigo != 0 and encoder and encoder != "libx264":
        codigo, err = intentar("libx264")  # por si la GPU esta ocupada o fallo
    if codigo != 0 or not os.path.exists(temporal):
        try:
            os.remove(temporal)
        except OSError:
            pass
        os.makedirs(N.CARPETA_LOGS, exist_ok=True)
        with open(os.path.join(N.CARPETA_LOGS, "recorte.log"), "wb") as f:
            f.write(err or b"")
        raise RuntimeError("FFmpeg no pudo crear el video (revisa logs\\recorte.log)")
    os.replace(temporal, salida)
    return salida


def a_gif(ruta, inicio, fin, progreso=None, velocidad=1.0, marca="", ancho=480, fps=15):
    """GIF animado del tramo elegido, junto al original (paleta propia para que se vea bien)."""
    inicio, fin = max(0.0, float(inicio)), float(fin)
    dur = fin - inicio
    if dur < 0.5:
        raise ValueError("El GIF tiene que durar al menos medio segundo")
    if dur / float(velocidad or 1) > 20:
        raise ValueError("Para un GIF elige 20 segundos o menos (pesan mucho)")
    velocidad = float(velocidad or 1) if float(velocidad or 1) in VELOCIDADES else 1.0
    marca = (marca or "").strip()
    cwd = _preparar_textos({"marca.txt": marca}) if marca else None
    salida = _nombre_libre(os.path.dirname(ruta), os.path.splitext(os.path.basename(ruta))[0], "", ".gif")
    temporal = salida + ".parcial.gif"
    cadena = ([f"setpts=PTS/{velocidad:g}"] if velocidad < 1 else []) + \
        [f"fps={fps}", f"scale={ancho}:-2:flags=lanczos"] + ([filtro_marca(marca)] if marca else [])
    filtro = ",".join(cadena) + ",split[a][b];[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=4"
    args = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{inicio:.3f}", "-t", f"{dur:.3f}",
            "-i", ruta, "-filter_complex", filtro, "-loop", "0", "-f", "gif", temporal]
    codigo, err = _ffmpeg(args, dur / velocidad, progreso, cwd)
    if codigo != 0 or not os.path.exists(temporal):
        os.makedirs(N.CARPETA_LOGS, exist_ok=True)
        with open(os.path.join(N.CARPETA_LOGS, "gif.log"), "wb") as f:
            f.write(err or b"")
        raise RuntimeError("FFmpeg no pudo crear el GIF (revisa logs\\gif.log)")
    os.replace(temporal, salida)
    return salida


def unir(rutas, encoder, calidad, progreso=None, transicion=0.5, ultimos=None, etiquetas=None,
         titulo="", salida=None):
    """Une varios videos en uno, con un fundido corto entre cada uno.
    Usa la resolución y los FPS del primero y una sola pista de audio (la mezcla).
    ultimos: usar solo los últimos N segundos de cada video (la jugada suele estar al final).
    etiquetas: un texto por video, arriba a la izquierda los primeros segundos.
    titulo: texto grande en el centro al principio (para el resumen de la semana)."""
    if len(rutas) < 2:
        raise ValueError("Elige al menos dos videos para unir")
    infos = [info_video(r) for r in rutas]  # (dur, alto, fps, indice de la mezcla)
    if any(d <= 0 for d, *_ in infos):
        raise RuntimeError("No pude leer uno de los videos")
    desde = [0.0] * len(rutas)
    if ultimos:
        desde = [max(0.0, d - ultimos) for d, *_ in infos]
        infos = [(min(d, ultimos), a, f, m) for d, a, f, m in infos]
    textos = {}
    for k, et in enumerate(etiquetas or []):
        if et:
            textos[f"et{k}.txt"] = et
    if titulo:
        textos["titulo.txt"] = titulo
    cwd = _preparar_textos(textos) if textos else None
    import json
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height", "-of", "json", rutas[0]],
                       capture_output=True, creationflags=N.SIN_VENTANA, timeout=30)
    v0 = (json.loads(r.stdout or b"{}").get("streams") or [{}])[0]
    ancho, alto = int(v0.get("width") or 1920), int(v0.get("height") or 1080)
    ancho, alto = ancho - ancho % 2, alto - alto % 2
    fps = round(infos[0][2] or 60)
    t = min(transicion, min(d for d, *_ in infos) / 3)
    entradas, partes = [], []
    con_audio = [bool(pistas_video(r)) for r in rutas]
    for k, ruta in enumerate(rutas):
        entradas += (["-ss", f"{desde[k]:.3f}"] if desde[k] else []) + ["-i", ruta]
    silencio = len(rutas)  # entrada extra de silencio para los videos sin audio
    entradas += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
    for k, (dur, _, _, mezcla) in enumerate(infos):
        fuente_a = f"[{k}:a:{mezcla}]" if con_audio[k] else f"[{silencio}:a]"
        partes.append(f"[{k}:v:0]scale={ancho}:{alto}:force_original_aspect_ratio=decrease,"
                      f"pad={ancho}:{alto}:(ow-iw)/2:(oh-ih)/2,fps={fps},format=yuv420p,setsar=1,"
                      f"trim=duration={dur:.3f},setpts=PTS-STARTPTS"
                      + (f",{_drawtext(f'et{k}.txt', 'h/24', 'h/24', 'h/22', chr(58) + 'enable=lt(t' + chr(92) + ',3)')}"
                         if f"et{k}.txt" in textos else "")
                      + (f",{_drawtext('titulo.txt', '(w-tw)/2', '(h-th)/2', 'h/11', chr(58) + 'enable=lt(t' + chr(92) + ',2.5)')}"
                         if k == 0 and titulo else "")
                      + f"[v{k}]")
        partes.append(f"{fuente_a}aresample=48000,aformat=channel_layouts=stereo,"
                      f"atrim=duration={dur:.3f},asetpts=PTS-STARTPTS,apad=whole_dur={dur:.3f}[a{k}]")
    v_ant, a_ant, offset = "v0", "a0", 0.0
    for k in range(1, len(rutas)):
        offset += infos[k - 1][0] - t
        partes.append(f"[{v_ant}][v{k}]xfade=transition=fade:duration={t:.3f}:offset={offset:.3f}[vx{k}]")
        partes.append(f"[{a_ant}][a{k}]acrossfade=d={t:.3f}[ax{k}]")
        v_ant, a_ant = f"vx{k}", f"ax{k}"
    total = sum(d for d, *_ in infos) - t * (len(rutas) - 1)
    if not salida:
        salida = _nombre_libre(os.path.dirname(rutas[0]), f"clip_unido_{N.marca_tiempo()}", "")
    temporal = salida + ".parcial.mp4"

    def intentar(enc):
        args = (["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"] + entradas +
                ["-filter_complex", ";".join(partes), "-map", f"[{v_ant}]", "-map", f"[{a_ant}]"] +
                N.args_encoder(enc, calidad) +
                ["-c:a", "aac", "-b:a", "160k", "-metadata:s:a:0", "handler_name=Mezcla",
                 "-movflags", "+faststart", temporal])
        return _ffmpeg(args, total, progreso, cwd)

    codigo, err = intentar(encoder or "libx264")
    if codigo != 0 and encoder and encoder != "libx264":
        codigo, err = intentar("libx264")
    if codigo != 0 or not os.path.exists(temporal):
        try:
            os.remove(temporal)
        except OSError:
            pass
        os.makedirs(N.CARPETA_LOGS, exist_ok=True)
        with open(os.path.join(N.CARPETA_LOGS, "unir.log"), "wb") as f:
            f.write(err or b"")
        raise RuntimeError("FFmpeg no pudo unir los videos (revisa logs\\unir.log)")
    os.replace(temporal, salida)
    return salida


# ---------------- compartir ----------------

def _ffmpeg(args, dur, progreso, cwd=None):
    """Corre FFmpeg informando el avance (0..1). Devuelve (codigo, stderr)."""
    args = args[:1] + ["-progress", "pipe:1", "-nostats"] + args[1:]  # opciones globales, antes de la salida
    p = subprocess.Popen(args, stdout=subprocess.PIPE, cwd=cwd,
                         stderr=subprocess.PIPE, creationflags=N.BAJA_PRIORIDAD)
    errores = []
    hilo = threading.Thread(target=lambda: errores.append(p.stderr.read()), daemon=True)
    hilo.start()
    for linea in p.stdout:
        linea = linea.decode("ascii", "replace").strip()
        if linea.startswith("out_time_us=") and progreso and dur:
            try:
                progreso(min(1.0, int(linea.split("=", 1)[1]) / 1e6 / dur))
            except ValueError:
                pass
    p.wait()
    hilo.join(timeout=2)
    return p.returncode, (errores[0] if errores else b"")


def info_video(ruta):
    """(duracion_s, alto, fps, indice de la pista 'Mezcla' o 0)."""
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "format=duration:stream=codec_type,height,avg_frame_rate:stream_tags=handler_name",
                        "-of", "json", ruta], capture_output=True, creationflags=N.SIN_VENTANA, timeout=60)
    import json
    datos = json.loads(r.stdout or b"{}")
    dur = float(datos.get("format", {}).get("duration") or 0)
    alto, fps, mezcla, n_audio = 1080, 60.0, 0, 0
    for s in datos.get("streams", []):
        if s.get("codec_type") == "video":
            alto = int(s.get("height") or alto)
            try:
                a, b = (s.get("avg_frame_rate") or "60/1").split("/")
                fps = float(a) / float(b or 1) or fps
            except (ValueError, ZeroDivisionError):
                pass
        elif s.get("codec_type") == "audio":
            if (s.get("tags") or {}).get("handler_name") == "Mezcla":
                mezcla = n_audio
            n_audio += 1
    return dur, alto, fps, mezcla


LIMITE_DISCORD = 10 * 1000 * 1000  # Discord (gratis) acepta archivos de hasta 10 MB


def para_discord(ruta, encoder, progreso=None):
    """Crea <nombre>_discord.mp4 de menos de 10 MB, con una sola pista de audio (la mezcla)."""
    dur, alto, fps, mezcla = info_video(ruta)
    if dur <= 0:
        raise RuntimeError("No pude leer la duración del video")
    base = os.path.splitext(os.path.basename(ruta))[0]
    salida = os.path.join(os.path.dirname(ruta), base + "_discord.mp4")
    temporal = salida + ".parcial.mp4"
    audio_k = 96
    objetivo = LIMITE_DISCORD * 0.92  # margen para el contenedor
    for intento in range(3):
        video_k = int(objetivo * 8 / dur / 1000 - audio_k)
        if video_k < 150:
            raise RuntimeError(f"El video dura {round(dur)} s: es demasiado largo para que quepa en 10 MB. "
                               "Recórtalo primero (unos 2 minutos como máximo).")
        # menos bitrate -> menos resolución y fps, para que se vea nítido y no pixelado
        nuevo_alto = 1080 if video_k >= 4500 else 720 if video_k >= 1400 else 540 if video_k >= 700 else 360
        nuevo_alto = min(alto, nuevo_alto)
        nuevos_fps = min(fps, 60 if video_k >= 2500 else 30)
        filtro = f"scale=-2:{nuevo_alto}:flags=bicubic,fps={nuevos_fps:g}"
        enc = encoder if encoder in ("h264_nvenc", "h264_amf", "h264_qsv") else "libx264"
        if enc == "h264_nvenc":
            v = ["-c:v", "h264_nvenc", "-preset", "p6", "-rc", "vbr", "-multipass", "fullres"]
        elif enc == "h264_amf":
            v = ["-c:v", "h264_amf", "-quality", "quality", "-rc", "vbr_peak"]
        elif enc == "h264_qsv":
            v = ["-c:v", "h264_qsv", "-preset", "slow"]
        else:
            v = ["-c:v", "libx264", "-preset", "medium"]
        v += ["-b:v", f"{video_k}k", "-maxrate", f"{int(video_k * 1.3)}k", "-bufsize", f"{video_k * 2}k"]
        args = (["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", ruta,
                 "-map", "0:v:0", "-map", f"0:a:{mezcla}?", "-vf", filtro, "-pix_fmt", "yuv420p"] + v +
                ["-c:a", "aac", "-b:a", f"{audio_k}k", "-ac", "2", "-movflags", "+faststart", temporal])
        codigo, err = _ffmpeg(args, dur, progreso)
        if codigo != 0 and enc != "libx264":
            # si la GPU falla, se hace con el procesador
            codigo, err = _ffmpeg(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", ruta,
                                   "-map", "0:v:0", "-map", f"0:a:{mezcla}?", "-vf", filtro,
                                   "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "medium",
                                   "-b:v", f"{video_k}k", "-maxrate", f"{int(video_k * 1.3)}k",
                                   "-bufsize", f"{video_k * 2}k", "-c:a", "aac", "-b:a", f"{audio_k}k",
                                   "-ac", "2", "-movflags", "+faststart", temporal], dur, progreso)
        if codigo != 0 or not os.path.exists(temporal):
            os.makedirs(N.CARPETA_LOGS, exist_ok=True)
            with open(os.path.join(N.CARPETA_LOGS, "discord.log"), "wb") as f:
                f.write(err or b"")
            raise RuntimeError("FFmpeg no pudo crear la versión para Discord (revisa logs\\discord.log)")
        tam = os.path.getsize(temporal)
        if tam <= LIMITE_DISCORD:
            os.replace(temporal, salida)
            return salida, tam
        objetivo *= LIMITE_DISCORD * 0.9 / tam  # se pasó: otra vez con menos bitrate
    os.replace(temporal, salida)
    return salida, os.path.getsize(salida)
