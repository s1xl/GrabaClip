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
import overlay as OV
import sonidos as SND
import voz as VZ
import actualizador as ACT

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
                    "por_juego", "captura", "ventana_exe", "escritorio_sin_juego", "monitor",
                    "quitar_mudas", "orden_pistas", "overlay", "overlay_indicador", "overlay_aviso",
                    "overlay_pos", "voz", "voz_clip", "voz_grabar", "voz_clips", "voz_idioma",
                    "voz_confianza", "avisar_updates"}


def sonido_ok():
    try:
        import winsound
        winsound.MessageBeep(winsound.MB_OK)
    except Exception:
        pass


def sonido_encendido(encendido):
    """Dos tonos que suben = clips activados; un tono grave = desactivados."""
    try:
        import winsound
        if encendido:
            winsound.Beep(880, 90)
            winsound.Beep(1320, 120)
        else:
            winsound.Beep(520, 180)
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
        self._clips_on = False      # el usuario activo los clips (aunque se este esperando un juego)
        self._clave_bufer = None    # que se esta grabando en el bufer ahora
        self._cambio_pendiente = 0
        self._fallos = []
        self._update = None         # info de una version nueva encontrada en GitHub
        self._actualizando = False
        self._perdidas = []         # reinicios por "se perdio la pantalla" en el ultimo minuto
        self._gen_bufer = 0
        self._parte_grab = 1
        self._monitores = []
        self._rastreador = VA.Rastreador()
        self._sonidos = SND.Sonidos(os.path.join(N.CARPETA_APP, "sonidos"))
        self._voz = VZ.Voz(self._por_voz, lambda e: self._emitir("voz", e))
        self._voz_iniciada = False
        self._overlay = OV.Overlay(lambda: self._cfg,
                                   lambda: N.TEMAS.get(self._cfg.get("tema"), N.TEMAS["Carmesí"]))
        threading.Thread(target=self._preparar, daemon=True).start()
        threading.Thread(target=self._al_abrir_updates, daemon=True).start()
        threading.Thread(target=self._vigilar, daemon=True).start()
        threading.Thread(target=self._seguir_juego, daemon=True).start()
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
            "clips": self._clips_on,
            "esperando": self._clips_on and self._bufer is None,
            "fuente": self._bufer.fuente.get("nombre") if self._bufer else None,
            "fuente_tipo": self._bufer.fuente.get("tipo") if self._bufer else None,
            "ventana_ok": N.MODO_GPU["ventana"],
            "motivo_ventana": N.MODO_GPU["motivo_ventana"],
            "monitores": self._monitores,
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
        estado = self._estado()
        self._overlay.actualizar(estado)
        self._emitir("estado", estado)

    # ---------- llamadas desde la interfaz ----------
    def inicio(self):
        self._lista = True
        if not self._voz_iniciada:  # System.Speech necesita que pywebview ya haya cargado .NET
            self._voz_iniciada = True
            self._voz.configurar(self._cfg)
        return {
            "cfg": self._cfg,
            "estado": self._estado(),
            "temas": N.TEMAS,
            "calidades": list(N.CALIDADES),
            "fps": N.FPS_OPCIONES,
            "resoluciones": list(N.RESOLUCIONES),
            "carpeta": N.CARPETA_SALIDA,
            "voz": self._voz.estado,
            "version": ACT.version_local(),
            "update": self._update,
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
            if any(k.startswith("voz") for k in (cambios or {})):
                self._voz.configurar(self._cfg)
        return self._cfg

    def apps(self):
        marcadas = [a.lower() for a in self._cfg["apps"]]
        lista = N.apps_con_sonido()
        abiertas = {x.lower() for x in lista}
        for a in self._cfg["apps"]:
            if a.lower() not in [x.lower() for x in lista]:
                lista.append(a)
        lista.sort(key=str.lower)
        return [{"exe": e, "nombre": N.nombre_bonito(e), "marcada": e.lower() in marcadas,
                 "abierta": e.lower() in abiertas} for e in lista]

    def ventanas(self):
        """Juegos y programas con ventana abierta, para elegir cual grabar."""
        return [{"exe": v["exe"], "nombre": v["nombre"], "titulo": v["titulo"]}
                for v in VA.ventanas_abiertas() if v["exe"] not in VA.PROPIOS]

    def alternar_clips(self):
        with self._lock:
            if self._clips_on:
                self._clips_on = False
                self._parar_bufer()
                self._aviso("Clips desactivados")
            else:
                if self._fatal:
                    self._aviso(self._fatal, "error")
                    return self._estado()
                if not self._encoder:
                    self._aviso("Espera un momento, todavía estoy detectando tu GPU", "error")
                    return self._estado()
                self._clips_on = True
                self._fallos = []
                fuente = self._fuente_deseada()
                if fuente:
                    self._iniciar_bufer(fuente)
                else:
                    self._aviso("Clips listos: empezarán a grabar cuando abras un juego", "ok")
        self._avisar_estado()
        return self._estado()

    # ---------- que se graba: la ventana del juego o una pantalla ----------
    def _fuente_deseada(self):
        cfg = self._cfg
        if cfg.get("captura", "juego") == "juego" and N.MODO_GPU["ventana"]:
            exe = (cfg.get("ventana_exe") or "").lower()
            if exe:
                hwnd = VA.ventana_de(exe)
                nombre = next((v["nombre"] for v in VA.ventanas_abiertas() if v["exe"] == exe), exe)
            else:
                juego = self._rastreador.juego_actual()
                hwnd, nombre = (juego["hwnd"], juego["nombre"]) if juego else (None, None)
            if hwnd:
                return {"tipo": "ventana", "hwnd": int(hwnd), "nombre": nombre}
            if not cfg.get("escritorio_sin_juego", True):
                return None
        idx = int(cfg.get("monitor", 0) or 0)
        if self._monitores and idx >= len(self._monitores):
            idx = 0
        return {"tipo": "monitor", "idx": idx, "nombre": f"Pantalla {idx + 1}"}

    @staticmethod
    def _clave(fuente):
        if not fuente:
            return None
        return ("v", fuente["hwnd"]) if fuente["tipo"] == "ventana" else ("m", fuente["idx"])

    def _iniciar_bufer(self, fuente, conservar=False):
        """conservar=True: se reinicia tras un corte y se guardan los segundos ya grabados."""
        self._gen_bufer += 1
        gen = self._gen_bufer
        if conservar:
            for viejo in glob.glob(os.path.join(N.CARPETA_BUFER, "*.ts")):
                nombre = os.path.basename(viejo)
                if not nombre.startswith(f"g{gen - 1}_"):  # solo se queda la tanda anterior
                    try:
                        os.remove(viejo)
                    except OSError:
                        pass
        else:
            shutil.rmtree(N.CARPETA_BUFER, ignore_errors=True)
        os.makedirs(N.CARPETA_BUFER, exist_ok=True)
        trozos = int(self._cfg["duracion"]) // N.SEG + 3
        salida = os.path.join(N.CARPETA_BUFER, f"g{gen}_seg%04d.ts")
        self._bufer = N.Sesion(int(self._cfg["fps"]), self._encoder, self._cfg,
                               ["-f", "segment", "-segment_time", str(N.SEG),
                                "-segment_wrap", str(trozos), "-reset_timestamps", "1",
                                "-segment_format", "mpegts", salida],
                               "bufer.log", fuente)
        self._clave_bufer = self._clave(fuente)
        self._inicio_bufer = time.time()
        if conservar:
            return
        que = fuente["nombre"] if fuente["tipo"] == "ventana" else "la pantalla"
        msg = f"Clips activos en {que}: {N.tecla_bonita(self._cfg['tecla_clip'])} guarda los últimos {self._cfg['duracion']} s"
        self._aviso(msg + self._bufer.aviso, "error" if self._bufer.aviso else "ok")

    def _parar_bufer(self):
        if self._bufer:
            self._bufer.detener()
        self._bufer = None
        self._clave_bufer = None

    def _seguir_juego(self):
        """Mientras los clips estan activos, cambia lo que se graba si cambia el juego."""
        while True:
            time.sleep(2)
            try:
                with self._lock:
                    if not self._clips_on or not self._encoder:
                        self._cambio_pendiente = 0
                        continue
                    fuente = self._fuente_deseada()
                    clave = self._clave(fuente)
                    if clave == self._clave_bufer and (self._bufer or not fuente):
                        self._cambio_pendiente = 0
                        continue
                    # se espera dos vueltas (unos 4 s) para no saltar con cada Alt+Tab
                    self._cambio_pendiente += 1
                    if self._bufer and self._cambio_pendiente < 2:
                        continue
                    self._cambio_pendiente = 0
                    self._parar_bufer()
                    if fuente:
                        self._iniciar_bufer(fuente)
                    else:
                        self._aviso("Se cerró el juego: los clips esperan a que abras otro")
                self._avisar_estado()
            except Exception:
                pass

    def guardar_clip(self):
        with self._lock:
            if not self._bufer:
                self._aviso("No hay ningún juego abierto para guardar un clip" if self._clips_on
                            else "Activa los clips primero", "error")
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
            juego = self._carpeta_destino(self._bufer.fuente)
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
                    self._sonidos.tocar("clip")
                extra = ""
                if self._cfg.get("quitar_mudas", True) and len(self._bufer.pistas) > 1:
                    quedan = N.quitar_pistas_mudas(destino, self._bufer.pistas)
                    quitadas = len(self._bufer.pistas) - len(quedan)
                    if quitadas:
                        extra = f" (sin {quitadas} {'pista vacía' if quitadas == 1 else 'pistas vacías'})"
                self._aviso(f"Clip guardado en {juego or 'GrabaClip'}{extra}", "ok")
                self._overlay.clip_guardado("Clip guardado",
                                            f"{juego or 'Escritorio'} · {self._cfg['duracion']} s")
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
                pistas, archivo = self._grab.pistas, self._archivo_grab
                self._grab = None
                self._inicio_grab = None
                self._ultimo = archivo
                self._aviso("Grabación guardada: " + os.path.basename(archivo), "ok")
                self._overlay.clip_guardado("Grabación guardada", os.path.basename(os.path.dirname(archivo)) or "GrabaClip")
                if self._cfg.get("sonido_clip", True):
                    self._sonidos.tocar("clip")
                self._terminar_grabacion(archivo, pistas)
            else:
                if self._fatal:
                    self._aviso(self._fatal, "error")
                    return self._estado()
                if not self._encoder:
                    self._aviso("Espera un momento, todavía estoy detectando tu GPU", "error")
                    return self._estado()
                fuente = self._fuente_deseada() or {"tipo": "monitor", "idx": int(self._cfg.get("monitor", 0) or 0),
                                                    "nombre": "Pantalla"}
                self._parte_grab = 1
                juego = self._empezar_grabacion(fuente)
                if self._grab.aviso:
                    self._aviso("Grabando" + self._grab.aviso, "error")
                elif juego:
                    self._aviso(f"Grabando {juego}", "ok")
        self._avisar_estado()
        return self._estado()

    def _empezar_grabacion(self, fuente, base=None):
        juego = self._carpeta_destino(fuente)
        if base:  # continuacion despues de un corte: grabacion_..._parte2.mp4
            nombre = f"{base}_parte{self._parte_grab}.mp4"
        else:
            nombre = f"grabacion_{N.marca_tiempo()}.mp4"
        self._archivo_grab = os.path.join(N.CARPETA_SALIDA, juego, nombre)
        os.makedirs(os.path.dirname(self._archivo_grab), exist_ok=True)
        self._grab = N.Sesion(int(self._cfg["fps"]), self._encoder, self._cfg,
                              ["-movflags", "+faststart", self._archivo_grab], "grabacion.log", fuente)
        if not base:
            self._inicio_grab = time.time() * 1000
        return juego

    def _puede_reintentar(self):
        ahora = time.time()
        self._perdidas = [t for t in self._perdidas if ahora - t < 60] + [ahora]
        return len(self._perdidas) <= 8

    def elegir_encoder(self, preferido):
        """Cambiar con que se graba: 'auto', una GPU concreta o el procesador."""
        if self._clips_on or self._grab:
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
                f.write(f"Captura directa: {N.MODO_GPU['directo']}  Escala en GPU: {N.MODO_GPU['escala']}  "
                        f"Captura de ventana: {N.MODO_GPU['ventana']}\n")
                f.write(f"Pantallas: {self._monitores}\n\n")
                for e, (ok, motivo) in self._encoders.items():
                    f.write(f"{e}: {'funciona' if ok else 'no funciona - ' + motivo}\n")
        except Exception:
            pass

    def elegir_carpeta(self):
        """Abre el selector de carpetas de Windows para elegir donde guardar los videos."""
        if self._grab:
            return {"ok": False, "msg": "Termina la grabación antes de cambiar la carpeta."}
        try:
            import webview
            tipo = webview.FileDialog.FOLDER if hasattr(webview, "FileDialog") else webview.FOLDER_DIALOG
            elegida = self._ventana.create_file_dialog(tipo, directory=N.CARPETA_SALIDA)
        except Exception as ex:
            return {"ok": False, "msg": f"No se pudo abrir el selector: {ex}"}
        if not elegida:
            return {"ok": False, "msg": ""}
        ruta = elegida[0] if isinstance(elegida, (list, tuple)) else elegida
        ok, motivo = N.carpeta_valida(ruta)
        if not ok:
            return {"ok": False, "msg": motivo}
        self._cfg["carpeta"] = ruta
        N.usar_carpeta(ruta)
        N.guardar_config(self._cfg)
        self._emitir("biblioteca")
        return {"ok": True, "carpeta": N.CARPETA_SALIDA, "msg": "Los nuevos videos se guardarán en " + N.CARPETA_SALIDA}

    def restablecer_carpeta(self):
        if self._grab:
            return {"ok": False, "carpeta": N.CARPETA_SALIDA, "msg": "Termina la grabación antes de cambiar la carpeta."}
        self._cfg["carpeta"] = ""
        N.usar_carpeta("")
        N.guardar_config(self._cfg)
        self._emitir("biblioteca")
        return {"ok": True, "carpeta": N.CARPETA_SALIDA, "msg": "Se usará otra vez Videos\\GrabaClip"}

    # ---------- actualizaciones ----------
    def _al_abrir_updates(self):
        time.sleep(15)
        ACT.limpiar_restos()  # restos de una actualizacion anterior
        if self._cfg.get("avisar_updates"):
            r = self.buscar_actualizacion(silencioso=True)
            if r.get("hay"):
                self._aviso(f"Hay una versión nueva de GrabaClip ({r['version']}). Actualízala en Ajustes → General", "ok")

    def buscar_actualizacion(self, silencioso=False):
        try:
            info = ACT.ultima()
        except Exception as ex:
            return {"ok": False, "msg": "No pude revisar GitHub. ¿Tienes internet?" if not silencioso else "",
                    "detalle": str(ex)}
        local = ACT.version_local()
        hay = ACT.es_mas_nueva(info["version"], local)
        self._update = info if hay else None
        self._emitir("update", self._update)
        return {"ok": True, "hay": hay, "version": info["version"], "local": local,
                "tam": info["tam"], "notas": info["notas"],
                "msg": "" if hay else f"Ya tienes la versión más reciente ({local})"}

    def actualizar(self):
        with self._lock:
            if self._actualizando:
                return {"ok": False, "msg": "La actualización ya está en marcha"}
            if self._grab:
                return {"ok": False, "msg": "Termina la grabación antes de actualizar"}
            if not self._update:
                return {"ok": False, "msg": "Primero busca actualizaciones"}
            self._actualizando = True
        threading.Thread(target=self._hacer_actualizacion, args=(dict(self._update),), daemon=True).start()
        return {"ok": True}

    def _hacer_actualizacion(self, info):
        def progreso(hecho, total):
            self._emitir("update_progreso", {"hecho": hecho, "total": total})
        try:
            nueva = ACT.descargar(info, progreso)
            self._emitir("update_progreso", {"fase": "instalando"})
            with self._lock:
                if self._grab:
                    raise RuntimeError("Empezó una grabación; termínala y vuelve a pulsar Actualizar")
                self._clips_on = False
                self._parar_bufer()
            ACT.instalar(nueva)
        except Exception as ex:
            self._actualizando = False
            self._emitir("update_progreso", {"error": str(ex)})
            self._aviso("No se pudo actualizar: " + str(ex), "error")
            return
        time.sleep(0.5)
        threading.Timer(8, lambda: os._exit(0)).start()  # por si algo deja abierto el proceso
        try:
            self._ventana.destroy()  # el instalador espera a que GrabaClip se cierre
        except Exception:
            os._exit(0)

    def voz_idiomas(self):
        return VZ.Voz.idiomas()

    def _por_voz(self, accion, frase, confianza):
        """Una frase de voz reconocida: hace lo mismo que la tecla correspondiente."""
        funcion = {"clip": self.guardar_clip, "grabar": self.alternar_grabacion,
                   "clips": self._alternar_clips_con_tecla}.get(accion)
        if funcion:
            threading.Thread(target=funcion, daemon=True).start()

    def probar_overlay(self):
        """Muestra el aviso de ejemplo y toca el sonido, para ver como queda."""
        self._overlay.clip_guardado("Clip guardado", f"Así se verá · {self._cfg['duracion']} s")
        if self._cfg.get("sonido_clip", True):
            self._sonidos.tocar("clip")
        if not self._cfg.get("overlay", True) or not self._cfg.get("overlay_aviso", True):
            self._aviso("El overlay está desactivado, solo sonó el aviso", "info")

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
        teclas = ("tecla_clip", "tecla_grab", "tecla_activar")
        if cual not in teclas:
            return {"ok": False, "msg": "Acción desconocida"}
        otras = [self._cfg.get(t) for t in teclas if t != cual]
        combo = (combo or "").strip().lower()
        resultado = {"ok": True, "msg": f"Nueva tecla: {N.tecla_bonita(combo)}"}
        if not combo:
            resultado = {"ok": False, "msg": "No reconocí esa tecla"}
        elif combo in otras:
            resultado = {"ok": False, "msg": f"{N.tecla_bonita(combo)} ya se usa en otra tecla rápida"}
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

    def _carpeta_destino(self, fuente=None):
        """Subcarpeta para el video segun el juego/app ('' = carpeta principal)."""
        if not self._cfg.get("por_juego", True):
            return ""
        if fuente and fuente.get("tipo") == "ventana" and fuente.get("nombre"):
            return VA.limpiar_carpeta(fuente["nombre"])
        return VA.limpiar_carpeta(self._rastreador.actual())

    def _terminar_grabacion(self, archivo, pistas):
        """Despues de grabar: quitar pistas vacias (en segundo plano) y avisar a la biblioteca."""
        def tarea():
            if self._cfg.get("quitar_mudas", True) and len(pistas) > 1 and os.path.exists(archivo):
                N.quitar_pistas_mudas(archivo, pistas)
            self._emitir("biblioteca")
        threading.Thread(target=tarea, daemon=True).start()

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
        acciones = (("tecla_clip", self.guardar_clip), ("tecla_grab", self.alternar_grabacion),
                    ("tecla_activar", self._alternar_clips_con_tecla))
        for clave, funcion in acciones:
            def disparar(f=funcion):
                threading.Thread(target=f, daemon=True).start()
            try:
                keyboard.add_hotkey(self._cfg[clave], disparar)
            except Exception:
                self._cfg[clave] = N.CONFIG_INICIAL[clave]
                keyboard.add_hotkey(self._cfg[clave], disparar)

    def _alternar_clips_con_tecla(self):
        antes = self._clips_on
        self.alternar_clips()
        if self._cfg.get("sonido_clip", True) and self._clips_on != antes:
            self._sonidos.tocar("activar" if self._clips_on else "desactivar")

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
        self._monitores = [f"Pantalla {i + 1} ({a}×{b})" for i, (a, b) in enumerate(N.monitores())]
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
                if self._bufer and not self._bufer.viva() and self._bufer.perdio_pantalla() \
                        and self._clips_on and self._puede_reintentar():
                    # Windows corto la captura un momento (p. ej. el juego cambio a pantalla completa):
                    # se reanuda sola y los segundos ya grabados siguen disponibles para el clip
                    fuente = self._bufer.fuente
                    self._bufer.cerrar_audio()
                    time.sleep(1)
                    self._iniciar_bufer(fuente, conservar=True)
                    cambio = True
                if self._bufer and not self._bufer.viva():
                    era_ventana = self._bufer.fuente.get("tipo") == "ventana"
                    self._bufer.cerrar_audio()
                    self._bufer = None
                    self._clave_bufer = None
                    cambio = True
                    ahora = time.time()
                    self._fallos = [t for t in self._fallos if ahora - t < 60] + [ahora]
                    if len(self._fallos) >= 3 or not era_ventana:
                        # falla de verdad: se apagan los clips
                        self._clips_on = False
                        self._aviso("Los clips se detuvieron por un error (revisa la carpeta logs)", "error")
                    # si era una ventana (p. ej. se cerro el juego), _seguir_juego elige otra fuente
                if self._grab and not self._grab.viva() and self._grab.perdio_pantalla() \
                        and self._puede_reintentar():
                    # se guarda lo grabado y se sigue en un archivo "_parte2"
                    fuente, pistas, archivo = self._grab.fuente, self._grab.pistas, self._archivo_grab
                    self._grab.cerrar_audio()
                    base = os.path.splitext(os.path.basename(archivo))[0].split("_parte")[0]
                    if os.path.exists(archivo) and os.path.getsize(archivo) > 0:
                        self._terminar_grabacion(archivo, pistas)
                    time.sleep(1)
                    self._parte_grab += 1
                    self._empezar_grabacion(fuente, base)
                    self._aviso(f"Windows cortó la captura un momento; la grabación sigue en la parte {self._parte_grab}", "ok")
                    cambio = True
                if self._grab and not self._grab.viva():
                    era_ventana = self._grab.fuente.get("tipo") == "ventana"
                    pistas, archivo = self._grab.pistas, self._archivo_grab
                    self._grab.cerrar_audio()
                    self._grab = None
                    self._inicio_grab = None
                    cambio = True
                    if era_ventana and archivo and os.path.exists(archivo) and os.path.getsize(archivo) > 0:
                        self._ultimo = archivo
                        self._aviso("La grabación terminó porque se cerró la ventana del juego", "ok")
                        self._terminar_grabacion(archivo, pistas)
                    else:
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
        try:
            self._voz.apagar()
        except Exception:
            pass
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
