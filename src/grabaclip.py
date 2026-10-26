"""
GrabaClip - Grabador de pantalla y clips instantaneos para Windows.
Version 0.7: clips organizados por juego.

Se abre con GrabaClip.exe. Si la interfaz moderna no se puede cargar,
abre la version clasica (grabaclip_clasico.py).
"""
import os
import sys
import glob
import json
import time
import base64
import shutil
import subprocess
import threading
import traceback

import nucleo as N
import ventana_activa as VA

try:
    import keyboard  # teclas rapidas globales
except ImportError:
    keyboard = None

ARCHIVO_UI = os.path.join(N.CARPETA_APP, "ui.html")
ARCHIVO_CANDADO = os.path.join(N.CARPETA_APP, ".abierto")
LANZADOR = os.path.join(N.CARPETA_APP, "GrabaClip.exe")
CARPETA_MINI = os.path.join(N.CARPETA_APP, "miniaturas")
ARCHIVO_INDICE = os.path.join(CARPETA_MINI, "indice.json")
ARCHIVO_ICONO = os.path.join(N.CARPETA_APP, "grabaclip.ico")


def identidad_en_barra():
    """Que Windows agrupe la ventana como 'GrabaClip' y no como Python."""
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("GrabaClip.App")
    except Exception:
        pass


def poner_icono(hwnd):
    """Cambia el icono de la ventana (barra de tareas y barra de titulo) por el de GrabaClip."""
    if not hwnd or not os.path.exists(ARCHIVO_ICONO):
        return
    try:
        import ctypes
        u32 = ctypes.windll.user32
        u32.LoadImageW.restype = ctypes.c_void_p
        u32.SendMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_void_p]
        grande = u32.LoadImageW(None, ARCHIVO_ICONO, 1, 256, 256, 0x10)  # IMAGE_ICON, LR_LOADFROMFILE
        chico = u32.LoadImageW(None, ARCHIVO_ICONO, 1, 32, 32, 0x10)
        if grande:
            u32.SendMessageW(hwnd, 0x80, 1, grande)  # WM_SETICON, ICON_BIG
        if chico:
            u32.SendMessageW(hwnd, 0x80, 0, chico)  # ICON_SMALL
    except Exception:
        pass
CLAVES_EDITABLES = {"duracion", "fps", "calidad", "resolucion", "mic", "apps", "ajuste_ms",
                    "tema", "iniciar_con_windows", "clips_al_abrir", "sonido_clip",
                    "por_juego"}


def sonido_ok():
    try:
        import winsound
        winsound.MessageBeep(winsound.MB_OK)
    except Exception:
        pass


class Api:
    """Todo lo que la interfaz (ui.html) puede pedirle al programa."""

    def __init__(self, minimizado=False):
        self._cfg = N.cargar_config()
        self._lock = threading.RLock()
        self._ventana = None
        self._lista = False
        self._bufer = None
        self._grab = None
        self._archivo_grab = None
        self._inicio_grab = None
        self._ultimo = None
        self._encoder = None
        self._teclas_pausadas = False
        self._minimizado = minimizado
        self._indice = self._leer_indice()
        self._pendientes = []
        self._hilo_mini = None
        self._encoders = {}
        self._fatal = None
        self._rastreador = VA.Rastreador()
        threading.Thread(target=self._preparar, daemon=True).start()
        threading.Thread(target=self._vigilar, daemon=True).start()
        self._registrar_teclas()

    # ---------- comunicacion con la interfaz ----------
    def _emitir(self, tipo, datos=None):
        if not (self._ventana and self._lista):
            return
        try:
            self._ventana.evaluate_js(f"window.recibir({json.dumps({'tipo': tipo, 'datos': datos})})")
        except Exception:
            pass

    def _aviso(self, texto, clase="info"):
        self._emitir("aviso", {"texto": texto, "clase": clase})

    def _estado(self):
        return {
            "clips": self._bufer is not None,
            "grabando": self._grab is not None,
            "inicio_grab": self._inicio_grab,
            "encoder": N.NOMBRES.get(self._encoder) if self._encoder else None,
            "directo": N.MODO_GPU["directo"],
            "encoder_id": self._encoder,
            "fatal": self._fatal,
            "encoder_pref": self._cfg.get("encoder", "auto"),
            "encoders": [{"id": e, "nombre": N.NOMBRES[e], "ok": ok, "motivo": motivo}
                         for e, (ok, motivo) in self._encoders.items()],
            "ultimo": os.path.basename(self._ultimo) if self._ultimo else None,
            "pistas": (self._bufer or self._grab).pistas if (self._bufer or self._grab) else [],
            "teclas": keyboard is not None,
            "audio": os.path.exists(N.AUDIOCAP),
        }

    def _avisar_estado(self):
        self._emitir("estado", self._estado())

    # ---------- llamadas desde la interfaz ----------
    def inicio(self):
        self._lista = True
        return {
            "cfg": self._cfg,
            "estado": self._estado(),
            "temas": N.TEMAS,
            "calidades": list(N.CALIDADES),
            "fps": N.FPS_OPCIONES,
            "resoluciones": list(N.RESOLUCIONES),
            "carpeta": N.CARPETA_SALIDA,
        }

    def guardar(self, cambios):
        with self._lock:
            antes = self._cfg.get("iniciar_con_windows")
            for k, v in (cambios or {}).items():
                if k in CLAVES_EDITABLES:
                    self._cfg[k] = v
            N.guardar_config(self._cfg)
            if "tema" in cambios:
                self._pintar_barra()
            if self._cfg.get("iniciar_con_windows") != antes:
                self._sincronizar_inicio()
        return self._cfg

    def apps(self):
        marcadas = [a.lower() for a in self._cfg["apps"]]
        lista = N.apps_con_sonido()
        for a in self._cfg["apps"]:
            if a.lower() not in [x.lower() for x in lista]:
                lista.append(a)
        lista.sort(key=str.lower)
        return [{"exe": e, "nombre": N.nombre_bonito(e), "marcada": e.lower() in marcadas}
                for e in lista]

    def alternar_clips(self):
        with self._lock:
            if self._bufer:
                self._bufer.detener()
                self._bufer = None
                self._aviso("Clips desactivados")
            else:
                if self._fatal:
                    self._aviso(self._fatal, "error")
                    return self._estado()
                if not self._encoder:
                    self._aviso("Espera un momento, todavía estoy detectando tu GPU", "error")
                    return self._estado()
                shutil.rmtree(N.CARPETA_BUFER, ignore_errors=True)
                os.makedirs(N.CARPETA_BUFER, exist_ok=True)
                trozos = int(self._cfg["duracion"]) // N.SEG + 3
                salida = os.path.join(N.CARPETA_BUFER, "seg%04d.ts")
                self._bufer = N.Sesion(int(self._cfg["fps"]), self._encoder, self._cfg,
                                       ["-f", "segment", "-segment_time", str(N.SEG),
                                        "-segment_wrap", str(trozos), "-reset_timestamps", "1",
                                        "-segment_format", "mpegts", salida],
                                       "bufer.log")
                msg = f"Clips activos: {N.tecla_bonita(self._cfg['tecla_clip'])} guarda los últimos {self._cfg['duracion']} s"
                self._aviso(msg + self._bufer.aviso, "error" if self._bufer.aviso else "ok")
        self._avisar_estado()
        return self._estado()

    def guardar_clip(self):
        with self._lock:
            if not self._bufer:
                self._aviso("Activa los clips primero", "error")
                return self._estado()
            trozos = sorted(glob.glob(os.path.join(N.CARPETA_BUFER, "*.ts")), key=os.path.getmtime)
            trozos = trozos[:-1]  # el ultimo todavía se esta escribiendo
            trozos = trozos[-max(1, int(self._cfg["duracion"]) // N.SEG):]
            if not trozos:
                self._aviso("Aún no hay suficiente video, espera unos segundos", "error")
                return self._estado()
            lista = os.path.join(N.CARPETA_BUFER, "lista.txt")
            with open(lista, "w", encoding="utf-8") as f:
                for t in trozos:
                    f.write("file '" + t.replace("\\", "/").replace("'", "'\\''") + "'\n")
            juego = self._carpeta_destino()
            destino = os.path.join(N.CARPETA_SALIDA, juego, f"clip_{N.marca_tiempo()}.mp4")
            os.makedirs(os.path.dirname(destino), exist_ok=True)
            args = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "concat", "-safe", "0", "-i", lista, "-map", "0", "-c", "copy"]
            if self._bufer.pistas:
                args += ["-bsf:a", "aac_adtstoasc"] + N.metadatos(self._bufer.pistas)
            args += ["-movflags", "+faststart", destino]
            r = N.correr(args)
            if r.returncode == 0:
                self._ultimo = destino
                if self._cfg.get("sonido_clip", True):
                    sonido_ok()
                self._aviso(f"Clip guardado en {juego or 'GrabaClip'}", "ok")
                self._emitir("biblioteca")
            else:
                os.makedirs(N.CARPETA_LOGS, exist_ok=True)
                with open(os.path.join(N.CARPETA_LOGS, "clip.log"), "wb") as f:
                    f.write(r.stderr)
                self._aviso("No se pudo guardar el clip", "error")
        self._avisar_estado()
        return self._estado()

    def alternar_grabacion(self):
        with self._lock:
            if self._grab:
                self._grab.detener()
                self._grab = None
                self._inicio_grab = None
                self._ultimo = self._archivo_grab
                self._aviso("Grabación guardada: " + os.path.basename(self._archivo_grab), "ok")
                self._emitir("biblioteca")
            else:
                if self._fatal:
                    self._aviso(self._fatal, "error")
                    return self._estado()
                if not self._encoder:
                    self._aviso("Espera un momento, todavía estoy detectando tu GPU", "error")
                    return self._estado()
                juego = self._carpeta_destino()
                self._archivo_grab = os.path.join(N.CARPETA_SALIDA, juego, f"grabacion_{N.marca_tiempo()}.mp4")
                os.makedirs(os.path.dirname(self._archivo_grab), exist_ok=True)
                self._grab = N.Sesion(int(self._cfg["fps"]), self._encoder, self._cfg,
                                      ["-movflags", "+faststart", self._archivo_grab], "grabacion.log")
                self._inicio_grab = time.time() * 1000
                if self._grab.aviso:
                    self._aviso("Grabando" + self._grab.aviso, "error")
                elif juego:
                    self._aviso(f"Grabando {juego}", "ok")
        self._avisar_estado()
        return self._estado()

    def elegir_encoder(self, preferido):
        """Cambiar con que se graba: 'auto', una GPU concreta o el procesador."""
        if self._bufer or self._grab:
            self._aviso("Desactiva los clips y deten la grabación para cambiarlo", "error")
            return self._estado()
        if preferido != "auto" and not self._encoders.get(preferido, (False,))[0]:
            self._aviso(self._encoders.get(preferido, (False, "No disponible"))[1] or "No disponible", "error")
            return self._estado()
        self._cfg["encoder"] = preferido
        N.guardar_config(self._cfg)
        self._encoder = None
        self._avisar_estado()

        def aplicar():
            self._aplicar_encoder()
            self._aviso("Ahora se graba con " + N.NOMBRES[self._encoder], "ok")
            self._avisar_estado()
        threading.Thread(target=aplicar, daemon=True).start()
        return self._estado()

    def _aplicar_encoder(self):
        elegido = N.elegir_encoder(self._encoders, self._cfg.get("encoder", "auto"))
        N.probar_gpu(elegido)
        self._encoder = elegido
        try:
            with open(os.path.join(N.CARPETA_LOGS, "gpu.txt"), "w", encoding="utf-8") as f:
                f.write(f"Preferencia: {self._cfg.get('encoder', 'auto')}\nElegido: {elegido}\n")
                f.write(f"Captura directa: {N.MODO_GPU['directo']}  Escala en GPU: {N.MODO_GPU['escala']}\n\n")
                for e, (ok, motivo) in self._encoders.items():
                    f.write(f"{e}: {'funciona' if ok else 'no funciona - ' + motivo}\n")
        except Exception:
            pass

    def abrir_carpeta(self):
        os.makedirs(N.CARPETA_SALIDA, exist_ok=True)
        os.startfile(N.CARPETA_SALIDA)

    def abrir_ultimo(self):
        if self._ultimo and os.path.exists(self._ultimo):
            os.startfile(self._ultimo)

    def pausar_teclas(self):
        self._teclas_pausadas = True
        if keyboard:
            try:
                keyboard.unhook_all_hotkeys()
            except Exception:
                pass

    def reanudar_teclas(self):
        self._teclas_pausadas = False
        self._registrar_teclas()

    def poner_tecla(self, cual, combo):
        if cual not in ("tecla_clip", "tecla_grab"):
            return {"ok": False, "msg": "Acción desconocida"}
        otra = "tecla_grab" if cual == "tecla_clip" else "tecla_clip"
        combo = (combo or "").strip().lower()
        resultado = {"ok": True, "msg": f"Nueva tecla: {N.tecla_bonita(combo)}"}
        if not combo:
            resultado = {"ok": False, "msg": "No reconocí esa tecla"}
        elif combo == self._cfg[otra]:
            resultado = {"ok": False, "msg": f"{N.tecla_bonita(combo)} ya se usa para la otra acción"}
        elif keyboard:
            try:
                keyboard.parse_hotkey(combo)
            except Exception:
                resultado = {"ok": False, "msg": "Esa tecla no se puede usar, prueba otra"}
        if resultado["ok"]:
            self._cfg[cual] = combo
            N.guardar_config(self._cfg)
        self.reanudar_teclas()
        resultado["cfg"] = self._cfg
        return resultado

    def tecla_bonita(self, combo):
        return N.tecla_bonita(combo)

    # ---------- biblioteca ----------
    def biblioteca(self):
        """Lista de videos en la carpeta, del mas nuevo al mas viejo."""
        try:
            archivos = glob.glob(os.path.join(glob.escape(N.CARPETA_SALIDA), "**", "*.mp4"), recursive=True)
        except Exception:
            archivos = []
        en_curso = self._archivo_grab if self._grab else None
        items = []
        faltan = []
        for ruta in archivos:
            if en_curso and os.path.normcase(ruta) == os.path.normcase(en_curso):
                continue
            try:
                st = os.stat(ruta)
            except OSError:
                continue
            nombre = os.path.basename(ruta)
            relativa = os.path.relpath(os.path.dirname(ruta), N.CARPETA_SALIDA)
            juego = "" if relativa in (".", "") else relativa.split(os.sep)[0]
            clave = f"{juego}/{nombre}|{int(st.st_mtime)}|{st.st_size}"
            info = self._indice.get(clave)
            item = {
                "ruta": ruta, "nombre": nombre, "clave": clave,
                "fecha": st.st_mtime * 1000, "tamano": st.st_size,
                "tipo": "clip" if nombre.lower().startswith("clip_") else "grabacion",
                "juego": juego,
                "duracion": info.get("dur") if info else None,
                "pistas": info.get("pistas") if info else None,
                "mini": self._mini_url(info) if info else None,
            }
            if not info:
                faltan.append((ruta, clave))
            items.append(item)
        items.sort(key=lambda x: x["fecha"], reverse=True)
        if faltan:
            self._pendientes = faltan
            if not (self._hilo_mini and self._hilo_mini.is_alive()):
                self._hilo_mini = threading.Thread(target=self._crear_miniaturas, daemon=True)
                self._hilo_mini.start()
        return items

    def reproducir(self, ruta):
        if self._ruta_valida(ruta):
            os.startfile(ruta)

    def mostrar_en_carpeta(self, ruta):
        if self._ruta_valida(ruta):
            subprocess.Popen(["explorer.exe", "/select,", os.path.normpath(ruta)])

    def eliminar(self, ruta):
        """Manda el video a la Papelera de reciclaje (se puede recuperar)."""
        if not self._ruta_valida(ruta):
            return False
        ok = mandar_a_papelera(ruta)
        self._aviso("Video enviado a la Papelera" if ok else "No se pudo eliminar el video",
                    "ok" if ok else "error")
        return ok

    def abrir_carpeta_juego(self, juego):
        ruta = os.path.join(N.CARPETA_SALIDA, juego) if juego else N.CARPETA_SALIDA
        base = os.path.normcase(os.path.abspath(N.CARPETA_SALIDA))
        if os.path.commonpath([base, os.path.normcase(os.path.abspath(ruta))]) == base and os.path.isdir(ruta):
            os.startfile(ruta)

    def _carpeta_destino(self):
        """Subcarpeta para el video segun el juego/app activo ('' = carpeta principal)."""
        if not self._cfg.get("por_juego", True):
            return ""
        return VA.limpiar_carpeta(self._rastreador.actual())

    def _ruta_valida(self, ruta):
        try:
            base = os.path.normcase(os.path.abspath(N.CARPETA_SALIDA))
            r = os.path.normcase(os.path.abspath(ruta))
            return os.path.commonpath([base, r]) == base and os.path.isfile(r)
        except Exception:
            return False

    def _leer_indice(self):
        try:
            with open(ARCHIVO_INDICE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _mini_url(self, info):
        archivo = os.path.join(CARPETA_MINI, info.get("mini", ""))
        if not info.get("mini") or not os.path.exists(archivo):
            return None
        with open(archivo, "rb") as f:
            return "data:image/jpeg;base64," + base64.b64encode(f.read()).decode()

    def _crear_miniaturas(self):
        os.makedirs(CARPETA_MINI, exist_ok=True)
        while self._pendientes:
            ruta, clave = self._pendientes.pop(0)
            if clave in self._indice:
                continue
            info = {"dur": None, "pistas": None, "mini": None}
            try:
                r = N.correr(["ffprobe", "-v", "error", "-show_entries",
                              "format=duration:stream=codec_type", "-of", "json", ruta], timeout=20)
                datos = json.loads(r.stdout.decode("utf-8", "replace") or "{}")
                info["dur"] = float(datos.get("format", {}).get("duration") or 0) or None
                info["pistas"] = sum(1 for x in datos.get("streams", []) if x.get("codec_type") == "audio")
            except Exception:
                pass
            nombre_mini = f"{abs(hash(clave)) % 10**12}.jpg"
            momento = min(2.0, (info["dur"] or 2) / 3)
            try:
                r = N.correr(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{momento:.2f}",
                              "-i", ruta, "-frames:v", "1", "-vf", "scale=320:-2", "-q:v", "4",
                              os.path.join(CARPETA_MINI, nombre_mini)], timeout=30)
                if r.returncode == 0:
                    info["mini"] = nombre_mini
            except Exception:
                pass
            self._indice[clave] = info
            try:
                with open(ARCHIVO_INDICE, "w", encoding="utf-8") as f:
                    json.dump(self._indice, f)
            except Exception:
                pass
            self._emitir("mini", {"clave": clave, "duracion": info["dur"], "pistas": info["pistas"],
                                  "mini": self._mini_url(info)})

    # ---------- interno ----------
    def _registrar_teclas(self):
        if not keyboard or self._teclas_pausadas:
            return
        try:
            keyboard.unhook_all_hotkeys()
        except Exception:
            pass
        acciones = (("tecla_clip", self.guardar_clip), ("tecla_grab", self.alternar_grabacion))
        for clave, funcion in acciones:
            def disparar(f=funcion):
                threading.Thread(target=f, daemon=True).start()
            try:
                keyboard.add_hotkey(self._cfg[clave], disparar)
            except Exception:
                self._cfg[clave] = N.CONFIG_INICIAL[clave]
                keyboard.add_hotkey(self._cfg[clave], disparar)

    def _preparar(self):
        ok, motivo = N.estado_ffmpeg()
        if not ok:
            self._fatal = motivo
            try:
                with open(os.path.join(N.CARPETA_LOGS, "gpu.txt"), "w", encoding="utf-8") as f:
                    f.write("FFmpeg no puede arrancar: " + motivo + "\n")
            except Exception:
                pass
            self._avisar_estado()
            self._emitir("fatal", motivo)
            return
        os.makedirs(N.CARPETA_SALIDA, exist_ok=True)
        self._encoders = N.probar_encoders()
        self._aplicar_encoder()
        self._avisar_estado()
        if self._cfg.get("clips_al_abrir") or self._minimizado:
            if self._cfg.get("clips_al_abrir"):
                self.alternar_clips()

    def _vigilar(self):
        while True:
            time.sleep(0.5)
            with self._lock:
                cambio = False
                if self._bufer and not self._bufer.viva():
                    self._bufer.cerrar_audio()
                    self._bufer = None
                    cambio = True
                    self._aviso("Los clips se detuvieron por un error (revisa la carpeta logs)", "error")
                if self._grab and not self._grab.viva():
                    self._grab.cerrar_audio()
                    self._grab = None
                    self._inicio_grab = None
                    cambio = True
                    self._aviso("La grabación se detuvo por un error (revisa la carpeta logs)", "error")
            if cambio:
                self._avisar_estado()

    def _sincronizar_inicio(self):
        """El lanzador (que corre fuera del 'sandbox' de Python de la Store) registra el inicio."""
        if not os.path.exists(LANZADOR):
            self._aviso("Falta GrabaClip.exe para configurar el inicio con Windows", "error")
            return
        try:
            import subprocess
            subprocess.Popen(["explorer.exe", LANZADOR])
        except Exception:
            pass

    def _pintar_barra(self):
        if not self._ventana:
            return
        t = N.TEMAS.get(self._cfg.get("tema"), N.TEMAS["Oscuro"])
        hwnd = None
        try:
            hwnd = int(self._ventana.native.Handle.ToInt64())
        except Exception:
            try:
                import ctypes
                hwnd = ctypes.windll.user32.FindWindowW(None, N.APP)
            except Exception:
                pass
        if hwnd:
            N.colorear_barra_titulo(None, t, hwnd)
            poner_icono(hwnd)

    def _cerrar(self):
        for s in (self._grab, self._bufer):
            if s:
                s.detener()
        if keyboard:
            try:
                keyboard.unhook_all()
            except Exception:
                pass


def mandar_a_papelera(ruta):
    try:
        import ctypes
        from ctypes import wintypes

        class SHFILEOPSTRUCTW(ctypes.Structure):
            _fields_ = [("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT),
                        ("pFrom", wintypes.LPCWSTR), ("pTo", wintypes.LPCWSTR),
                        ("fFlags", ctypes.c_ushort), ("fAnyOperationsAborted", wintypes.BOOL),
                        ("hNameMappings", ctypes.c_void_p), ("lpszProgressTitle", wintypes.LPCWSTR)]
        op = SHFILEOPSTRUCTW()
        op.wFunc = 3  # FO_DELETE
        op.pFrom = os.path.abspath(ruta) + "\0"
        op.fFlags = 0x40 | 0x10 | 0x04 | 0x400  # ALLOWUNDO | NOCONFIRMATION | SILENT | NOERRORUI
        return ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op)) == 0 and not op.fAnyOperationsAborted
    except Exception:
        return False


def quitar_marca_de_internet():
    """Windows marca los archivos descomprimidos de un zip descargado como 'de internet'
    (Zone.Identifier) y .NET se niega a cargar las DLL de la interfaz. Se quita esa marca."""
    if sys.platform != "win32":
        return
    for raiz in (N.CARPETA_APP, os.path.join(N.CARPETA_APP, "runtime")):
        for carpeta, _, archivos in os.walk(raiz):
            for nombre in archivos:
                if nombre.lower().endswith((".dll", ".exe", ".pyd")):
                    try:
                        os.remove(os.path.join(carpeta, nombre) + ":Zone.Identifier")
                    except OSError:
                        pass
            if raiz == N.CARPETA_APP:
                break  # en la carpeta principal solo el primer nivel


def modo_clasico(motivo):
    with open(os.path.join(N.CARPETA_LOGS, "interfaz.log"), "w", encoding="utf-8") as f:
        f.write(motivo)
    import runpy
    runpy.run_path(os.path.join(N.CARPETA_APP, "grabaclip_clasico.py"), run_name="__main__")


def main():
    os.makedirs(N.CARPETA_LOGS, exist_ok=True)
    candado = open(ARCHIVO_CANDADO, "w")  # el lanzador lo usa para saber que ya esta abierto
    minimizado = "--minimizado" in sys.argv
    quitar_marca_de_internet()
    try:
        import webview
    except Exception:
        modo_clasico(traceback.format_exc())
        return

    identidad_en_barra()
    api = Api(minimizado)
    t = N.TEMAS.get(api._cfg.get("tema"), N.TEMAS["Oscuro"])
    ventana = webview.create_window(
        N.APP, url=ARCHIVO_UI, js_api=api, width=1000, height=680, min_size=(820, 560),
        background_color=t["bg"], minimized=minimizado)
    api._ventana = ventana
    ventana.events.shown += api._pintar_barra
    ventana.events.closed += api._cerrar
    try:
        webview.start(debug=False)
    except Exception:
        api._cerrar()
        modo_clasico(traceback.format_exc())
    candado.close()


if __name__ == "__main__":
    main()
