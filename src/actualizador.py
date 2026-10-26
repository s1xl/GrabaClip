"""Actualizaciones de GrabaClip desde GitHub Releases.

Solo se conecta a internet cuando el usuario pulsa "Buscar actualizaciones" (o si activó
"Avisar al abrir"). Pasos:
  1. ultima()      -> consulta la última versión publicada en github.com/s1xl/GrabaClip
  2. descargar()   -> baja el .zip portable, comprueba su huella SHA-256 y lo descomprime en
                      <carpeta de GrabaClip>\\_actualizacion
  3. instalar()    -> abre este mismo archivo, pero el de la versión NUEVA y con su propio Python,
                      que espera a que GrabaClip se cierre, copia los archivos nuevos encima
                      (config.json, logs y miniaturas no vienen en el .zip, así que no se tocan)
                      y vuelve a abrir GrabaClip.
"""
import hashlib
import json
import os
import shutil
import ssl
import subprocess
import sys
import time
import urllib.request
import zipfile

REPO = "s1xl/GrabaClip"
API = f"https://api.github.com/repos/{REPO}/releases/latest"
CARPETA_APP = os.path.dirname(os.path.abspath(__file__))
CARPETA_TEMP = os.path.join(CARPETA_APP, "_actualizacion")
AGENTE = "GrabaClip-actualizador"
SIN_VENTANA = 0x08000000
DESLIGADO = 0x00000008


def version_local(carpeta=CARPETA_APP):
    try:
        with open(os.path.join(carpeta, "VERSION"), encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return "0"


def _numeros(v):
    partes = []
    for p in str(v).lstrip("vV").split("."):
        d = "".join(c for c in p if c.isdigit())
        partes.append(int(d) if d else 0)
    return tuple(partes + [0] * (3 - len(partes)))


def es_mas_nueva(remota, local):
    return _numeros(remota) > _numeros(local)


def _abrir(url, tiempo=20):
    pedido = urllib.request.Request(url, headers={"User-Agent": AGENTE,
                                                  "Accept": "application/vnd.github+json"})
    return urllib.request.urlopen(pedido, timeout=tiempo, context=ssl.create_default_context())


def ultima():
    """{'version', 'notas', 'url', 'tam', 'sha256'} de la última versión publicada."""
    with _abrir(API) as r:
        datos = json.load(r)
    zipe = next((a for a in datos.get("assets", [])
                 if a.get("name", "").endswith("-portable.zip")), None)
    if not zipe:
        raise RuntimeError("La versión publicada no trae el archivo portable")
    huella = (zipe.get("digest") or "")
    return {
        "version": datos.get("tag_name", "").lstrip("vV"),
        "notas": (datos.get("body") or "").strip()[:1500],
        "url": zipe["browser_download_url"],
        "tam": int(zipe.get("size") or 0),
        "sha256": huella.split(":", 1)[1].lower() if huella.startswith("sha256:") else "",
    }


def descargar(info, progreso=None):
    """Baja y descomprime la versión nueva. Devuelve la carpeta con los archivos nuevos."""
    shutil.rmtree(CARPETA_TEMP, ignore_errors=True)
    os.makedirs(CARPETA_TEMP, exist_ok=True)
    destino_zip = os.path.join(CARPETA_TEMP, "GrabaClip.zip")
    h = hashlib.sha256()
    bajado, ultimo_aviso = 0, 0.0
    with _abrir(info["url"], tiempo=60) as r, open(destino_zip, "wb") as f:
        total = int(r.headers.get("Content-Length") or info.get("tam") or 0)
        while True:
            trozo = r.read(1 << 20)
            if not trozo:
                break
            f.write(trozo)
            h.update(trozo)
            bajado += len(trozo)
            if progreso and time.time() - ultimo_aviso > 0.25:
                ultimo_aviso = time.time()
                progreso(bajado, total)
    if progreso:
        progreso(bajado, bajado)
    if info.get("sha256") and h.hexdigest() != info["sha256"]:
        raise RuntimeError("El archivo descargado está dañado (la huella no coincide). Prueba otra vez.")
    with zipfile.ZipFile(destino_zip) as z:
        raiz = os.path.realpath(CARPETA_TEMP)
        for nombre in z.namelist():  # nada fuera de la carpeta temporal
            if not os.path.realpath(os.path.join(raiz, nombre)).startswith(raiz + os.sep):
                raise RuntimeError("El archivo descargado no es válido")
        z.extractall(CARPETA_TEMP)
    os.remove(destino_zip)
    nueva = os.path.join(CARPETA_TEMP, "GrabaClip")
    if not os.path.isfile(os.path.join(nueva, "grabaclip.py")):
        raise RuntimeError("El archivo descargado no trae GrabaClip")
    return nueva


def instalar(nueva):
    """Abre el instalador de la versión nueva; GrabaClip se debe cerrar justo después."""
    python = os.path.join(nueva, "runtime", "python", "pythonw.exe")
    script = os.path.join(nueva, "actualizador.py")
    if not os.path.isfile(script):
        script = os.path.abspath(__file__)
    if not os.path.isfile(python):
        raise RuntimeError("Falta Python en la versión descargada")
    subprocess.Popen([python, "-I", script, "--instalar", nueva, CARPETA_APP, str(os.getpid())],
                     cwd=nueva, creationflags=SIN_VENTANA | DESLIGADO, close_fds=True)


def limpiar_restos():
    """Al abrir la versión nueva se borra la carpeta temporal (si el instalador ya terminó)."""
    if os.path.isdir(CARPETA_TEMP):
        shutil.rmtree(CARPETA_TEMP, ignore_errors=True)


# ---------------- lo que corre el instalador, con GrabaClip cerrado ----------------

def _esperar_proceso(pid, segundos=60):
    try:
        import ctypes
        k = ctypes.windll.kernel32
        h = k.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
        if h:
            k.WaitForSingleObject(h, int(segundos * 1000))
            k.CloseHandle(h)
    except Exception:
        time.sleep(3)


def _copiar(origen, destino, log):
    fallidos = []
    for base, carpetas, archivos in os.walk(origen):
        rel = os.path.relpath(base, origen)
        dest_base = destino if rel == "." else os.path.join(destino, rel)
        os.makedirs(dest_base, exist_ok=True)
        for a in archivos:
            o, d = os.path.join(base, a), os.path.join(dest_base, a)
            for intento in range(20):  # un archivo puede seguir en uso unos segundos
                try:
                    shutil.copy2(o, d)
                    break
                except OSError as ex:
                    if intento == 19:
                        fallidos.append(d)
                        log.write(f"no se pudo copiar {d}: {ex}\n")
                    time.sleep(0.5)
    return fallidos


def _actualizar_registro(destino, version):
    """Si GrabaClip se instaló con el instalador, que Configuración > Aplicaciones muestre la versión nueva."""
    try:
        import winreg
        ruta = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\GrabaClip"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, ruta, 0, winreg.KEY_READ | winreg.KEY_SET_VALUE) as k:
            lugar = winreg.QueryValueEx(k, "InstallLocation")[0]
            if os.path.normcase(os.path.abspath(lugar)) == os.path.normcase(os.path.abspath(destino)):
                winreg.SetValueEx(k, "DisplayVersion", 0, winreg.REG_SZ, version)
    except Exception:
        pass


def _instalar_ahora(nueva, destino, pid):
    os.makedirs(os.path.join(destino, "logs"), exist_ok=True)
    with open(os.path.join(destino, "logs", "actualizacion.txt"), "w", encoding="utf-8") as log:
        log.write(f"{time.ctime()}  {version_local(destino)} -> {version_local(nueva)}\n")
        _esperar_proceso(pid)
        candado = os.path.join(destino, ".abierto")
        for _ in range(60):  # GrabaClip mantiene abierto este archivo mientras funciona
            try:
                if os.path.exists(candado):
                    os.remove(candado)
                break
            except OSError:
                time.sleep(0.5)
        time.sleep(1)  # FFmpeg y el ayudante de audio terminan de cerrarse
        fallidos = _copiar(nueva, destino, log)
        log.write("listo\n" if not fallidos else f"{len(fallidos)} archivos no se copiaron\n")
        log.flush()
    _actualizar_registro(destino, version_local(destino))
    exe = os.path.join(destino, "GrabaClip.exe")
    if os.path.isfile(exe):
        subprocess.Popen([exe], cwd=destino, creationflags=DESLIGADO, close_fds=True)


if __name__ == "__main__" and len(sys.argv) >= 5 and sys.argv[1] == "--instalar":
    _instalar_ahora(sys.argv[2], sys.argv[3], int(sys.argv[4]))
