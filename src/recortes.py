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
    def __init__(self):
        self._clave = secrets.token_urlsafe(16)
        self._permitidos = {}  # id -> ruta
        self._srv = None

    def _arrancar(self):
        if self._srv:
            return
        dueno = self

        class Manejador(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                partes = urllib.parse.urlparse(self.path).path.strip("/").split("/")
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

    def url(self, ruta):
        self._arrancar()
        ident = secrets.token_urlsafe(8)
        self._permitidos = {ident: ruta}  # solo el video que se está editando
        return f"http://127.0.0.1:{self._srv.server_address[1]}/{self._clave}/{ident}"

    def olvidar(self):
        self._permitidos = {}


def _nombre_libre(carpeta, base):
    n = 1
    while True:
        nombre = f"{base}_recorte{'' if n == 1 else n}.mp4"
        if not os.path.exists(os.path.join(carpeta, nombre)):
            return os.path.join(carpeta, nombre)
        n += 1


def recortar(ruta, inicio, fin, encoder, calidad, progreso=None):
    """Crea <nombre>_recorte.mp4 junto al original. Devuelve la ruta nueva."""
    inicio, fin = max(0.0, float(inicio)), float(fin)
    dur = fin - inicio
    if dur < 0.5:
        raise ValueError("El recorte tiene que durar al menos medio segundo")
    carpeta = os.path.dirname(ruta)
    salida = _nombre_libre(carpeta, os.path.splitext(os.path.basename(ruta))[0])
    temporal = salida + ".parcial.mp4"

    def intentar(enc):
        args = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-ss", f"{inicio:.3f}", "-i", ruta, "-t", f"{dur:.3f}",
                "-map", "0:v:0", "-map", "0:a?"]
        args += N.args_encoder(enc, calidad)
        args += ["-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
                 "-map_metadata", "0", "-movflags", "+faststart",
                 "-progress", "pipe:1", "-nostats", temporal]
        p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             creationflags=N.BAJA_PRIORIDAD)
        errores = []
        hilo = threading.Thread(target=lambda: errores.append(p.stderr.read()), daemon=True)
        hilo.start()
        for linea in p.stdout:
            linea = linea.decode("ascii", "replace").strip()
            if linea.startswith("out_time_us=") and progreso:
                try:
                    progreso(min(1.0, int(linea.split("=", 1)[1]) / 1e6 / dur))
                except ValueError:
                    pass
        p.wait()
        hilo.join(timeout=2)
        return p.returncode, (errores[0] if errores else b"")

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
        raise RuntimeError("FFmpeg no pudo recortar el video (revisa logs\\recorte.log)")
    os.replace(temporal, salida)
    return salida
