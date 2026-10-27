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
import queue
import threading
import traceback

import nucleo as N
import ventana_activa as VA
import overlay as OV
import sonidos as SND
import voz as VZ
import actualizador as ACT
import bandeja as BJ
import recortes as RC
import discord_rpc as DR
import idiomas as I18N
import bufer_ram as BR

try:
    import keyboard  # teclas rapidas globales
except ImportError:
    keyboard = None

ARCHIVO_UI = os.path.join(N.CARPETA_APP, "ui.html")
ARCHIVO_CANDADO = os.path.join(N.CARPETA_APP, ".abierto")
LANZADOR = os.path.join(N.CARPETA_APP, "GrabaClip.exe")
CARPETA_MINI = os.path.join(N.CARPETA_APP, "miniaturas")
ARCHIVO_INDICE = os.path.join(CARPETA_MINI, "indice.json")
ARCHIVO_FAVORITOS = os.path.join(N.CARPETA_APP, "favoritos.json")
ARCHIVO_MARCAS = os.path.join(N.CARPETA_APP, "marcas.json")
ARCHIVO_ETIQUETAS = os.path.join(N.CARPETA_APP, "etiquetas.json")
# en un respaldo de ajustes no van cosas propias de esta PC (carpetas, ventanas, pantallas)
NO_RESPALDAR = {"carpeta", "ventana_exe", "monitor", "encoder", "mic", "apps", "orden_pistas",
                "perfil_elegido", "tutorial_visto", "bandeja_aviso_visto", "ui_version", "voz_idioma"}
NO_VALIDOS = set('<>:"/\\|?*')
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
                    "voz_confianza", "avisar_updates", "bandeja", "modo_audio", "rendimiento", "discord", "discord_juego", "limite_gb", "limite_grabaciones",
                    "duracion_larga", "por_juego_cfg", "vista_previa", "clip_al_cerrar", "idioma",
                    "esquinas", "tamano_texto", "tutorial_visto", "avisos", "codec", "bufer_ram", "marca_texto", "medidor", "webcam", "webcam_pos", "webcam_tam"}


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
        I18N.elegir(self._cfg.get("idioma", "auto"))
        if I18N.ajustar_frases(self._cfg):
            N.guardar_config(self._cfg)
        self._lock = threading.RLock()
        self._ventana = None
        self._lista = False
        self._bufer = None
        self._grab = None
        self._archivo_grab = None
        self._inicio_grab = None
        self._ultimo = None
        self._encoder = None
        self._av1 = (False, "", "")   # (funciona, motivo, contenedor del búfer)
        self._ram = BR.BuferRAM()
        self._bufer_en_ram = False
        self._mic_mudo = False
        self._webcam_fallida = False  # la webcam no abrió (otra app la usa): se sigue sin ella
        self._teclas_pausadas = False
        self._minimizado = minimizado
        self._indice = self._leer_indice()
        self._favoritos = self._leer_favoritos()
        self._marcas = self._leer_json(ARCHIVO_MARCAS, {})  # ruta de la grabación -> segundos marcados
        self._etiquetas = self._leer_json(ARCHIVO_ETIQUETAS, {})  # ruta -> ["jugadas", "para subir"…]
        self._medidor = None
        self._inicio_parte = None
        self._pendientes = []
        self._hilo_mini = None
        self._encoders = {}
        self._fatal = None
        self._clips_on = False      # el usuario activo los clips (aunque se este esperando un juego)
        self._clave_bufer = None    # que se esta grabando en el bufer ahora
        self._cambio_pendiente = 0
        self._fallos = []
        self._bandeja = None
        self._saliendo = False
        self._presencia = DR.Presencia()
        self._cola_ui = queue.Queue()
        self._emisor_ocupado = 0
        self._emisor_actual = None
        self._candado_mostrar = threading.Lock()
        self._candado_recuperar = threading.Lock()
        self._ultimo_mostrar = 0.0
        self._servidor_video = RC.ServidorVideo(CARPETA_MINI)
        self._url_ui = None          # para volver a cargar la interfaz al mostrar la ventana
        self._recortando = False
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
        self._overlay = OV.Overlay(self._cfg_efectiva,
                                   lambda: N.temas_todos(self._cfg).get(self._cfg.get("tema"), N.TEMAS["Carmesí"]))
        threading.Thread(target=self._hilo_emisor, daemon=True).start()
        threading.Thread(target=self._preparar, daemon=True).start()
        threading.Thread(target=self._al_abrir_updates, daemon=True).start()
        threading.Thread(target=self._vigilar, daemon=True).start()
        threading.Thread(target=self._seguir_juego, daemon=True).start()
        self._registrar_teclas()

    # ---------- comunicacion con la interfaz ----------
    def _emitir(self, tipo, datos=None):
        """Manda un mensaje a la interfaz SIN esperar: lo entrega un hilo propio.
        (evaluate_js de pywebview espera la respuesta para siempre si la página se recarga justo
        en ese momento; si eso pasaba con el candado tomado, GrabaClip dejaba de responder.)"""
        if not (self._ventana and self._lista):
            return
        self._cola_ui.put(f"window.recibir({json.dumps({'tipo': tipo, 'datos': datos})})")
        if self._emisor_ocupado and time.time() - self._emisor_ocupado > 5:
            self._emisor_ocupado = 0  # el hilo anterior se trabó: se reemplaza
            threading.Thread(target=self._hilo_emisor, daemon=True).start()

    def _hilo_emisor(self):
        mio = object()
        self._emisor_actual = mio
        while self._emisor_actual is mio:
            js = self._cola_ui.get()
            if not self._lista:
                continue
            self._emisor_ocupado = time.time()
            try:
                self._ventana.evaluate_js(js)
            except Exception:
                pass
            if self._emisor_actual is mio:
                self._emisor_ocupado = 0

    def _avisar(self, evento, sonido=None, titulo=None, detalle=""):
        """Sonido y/o overlay de una acción, según lo elegido para esa acción en Ajustes."""
        quiere = N.aviso_evento(self._cfg, evento)
        if sonido and quiere["sonido"] and self._cfg.get("sonido_clip", True):
            self._sonidos.tocar(sonido)
        if titulo is not None and quiere["overlay"]:
            self._overlay.clip_guardado(titulo, detalle)

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
            "mic_mudo": self._mic_mudo,
            "av1_ok": self._av1[0],
            "av1_motivo": self._av1[1],
            "av1_ram": self._av1[2] == "mpegts",
            "codec_activo": "av1" if self._encoder_video() != self._encoder else "h264",
            "en_ram": self._bufer_en_ram and self._bufer is not None,
            "ram_mb": self._ram.megas() if self._bufer_en_ram else 0,
            "webcam_fallida": self._webcam_fallida,
        }

    def estado(self):
        return self._estado()

    def camaras(self):
        return N.camaras()

    # ---------- AV1 y búfer en RAM ----------
    def _encoder_video(self):
        """El codificador para clips y grabaciones: la variante AV1 si se eligió y funciona."""
        if self._cfg.get("codec") == "av1" and self._av1[0] and self._encoder in N.AV1:
            return N.AV1[self._encoder]
        return self._encoder

    def _usar_ram(self):
        if not self._cfg.get("bufer_ram"):
            return False
        return self._encoder_video() == self._encoder or self._av1[2] == "mpegts"

    def _formato_bufer(self):
        """("mpegts", "ts") normalmente; ("matroska", "mkv") si es AV1 y este FFmpeg no lo mete en TS."""
        if self._encoder_video() != self._encoder and self._av1[2] == "matroska":
            return "matroska", "mkv"
        return "mpegts", "ts"

    # ---------- silenciar el micrófono ----------
    def alternar_mic(self):
        if not self._cfg.get("mic"):
            self._aviso("El micrófono no se está grabando (Ajustes → Audio)", "error")
            return self._estado()
        self._mic_mudo = not self._mic_mudo
        for ses in (self._bufer, self._grab):
            if ses:
                ses.silenciar_mic(self._mic_mudo)
        self._avisar("mic", "desactivar" if self._mic_mudo else "activar",
                     I18N.t_overlay("Micrófono apagado" if self._mic_mudo else "Micrófono encendido"),
                     N.tecla_bonita(self._cfg.get("tecla_mic", "")))
        self._aviso("Micrófono apagado: no se graba tu voz" if self._mic_mudo else "Micrófono encendido", "info")
        self._avisar_estado()
        return self._estado()

    def _avisar_estado(self):
        estado = self._estado()
        self._overlay.actualizar(estado)
        self._presencia.actualizar(self._cfg.get("discord"), estado, self._cfg.get("discord_juego", True))
        if self._bandeja:
            estado_txt = ("Grabando la pantalla" if self._grab else "Clips activos" if self._bufer else
                          "Esperando un juego" if self._clips_on else "Clips apagados")
            self._bandeja.texto("GrabaClip · " + I18N.t(estado_txt))
        self._emitir("estado", estado)

    # ---------- llamadas desde la interfaz ----------
    def inicio(self):
        self._lista = True
        if not self._voz_iniciada:  # System.Speech necesita que pywebview ya haya cargado .NET
            self._voz_iniciada = True
            self._voz.configurar(self._cfg_efectiva())
        return {
            "cfg": self._cfg,
            "estado": self._estado(),
            "temas": N.temas_todos(self._cfg),
            "temas_fabrica": list(N.TEMAS),
            "calidades": list(N.CALIDADES),
            "fps": N.FPS_OPCIONES,
            "resoluciones": list(N.RESOLUCIONES),
            "carpeta": N.CARPETA_SALIDA,
            "voz": self._voz.estado,
            "version": ACT.version_local(),
            "discord_listo": bool(DR.APP_ID),
            "idioma": I18N.ACTUAL,
            "rtl": I18N.ACTUAL in I18N.RTL,
            "idiomas": I18N.IDIOMAS,
            "catalogo": I18N.catalogo(I18N.ACTUAL),
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
            if any(k.startswith("voz") or k == "rendimiento" for k in (cambios or {})):
                self._voz.configurar(self._cfg_efectiva())
            if "limite_gb" in (cambios or {}) or "limite_grabaciones" in (cambios or {}):
                threading.Thread(target=self._aplicar_limite, daemon=True).start()
            if "idioma" in (cambios or {}):
                I18N.elegir(self._cfg.get("idioma", "auto"))
                if I18N.ajustar_frases(self._cfg):
                    N.guardar_config(self._cfg)
                    self._voz.configurar(self._cfg_efectiva())
                self._overlay.refrescar()
                self._avisar_estado()
            if "discord" in (cambios or {}) or "discord_juego" in (cambios or {}):
                self._avisar_estado()
            if any(k.startswith("webcam") for k in (cambios or {})):
                self._webcam_fallida = False
            if "rendimiento" in (cambios or {}):
                self._overlay.refrescar()
                self._avisar_estado()
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
        if not self._funcion("clips") and not self._clips_on:
            self._aviso("Los clips están apagados en tu perfil (Ajustes → General → Perfil)", "error")
            return self._estado()
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
                if not self._grab:
                    self._webcam_fallida = False  # se vuelve a intentar con la webcam
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
                hwnd, nombre, exe = (juego["hwnd"], juego["nombre"], juego["exe"]) if juego else (None, None, None)
            if hwnd:
                return {"tipo": "ventana", "hwnd": int(hwnd), "nombre": nombre, "exe": (exe or "").lower()}
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
            for viejo in glob.glob(os.path.join(N.CARPETA_BUFER, "g*_seg*.*")):
                nombre = os.path.basename(viejo)
                if not nombre.startswith(f"g{gen - 1}_"):  # solo se queda la tanda anterior
                    try:
                        os.remove(viejo)
                    except OSError:
                        pass
        else:
            shutil.rmtree(N.CARPETA_BUFER, ignore_errors=True)
            self._ram.limpiar()
        os.makedirs(N.CARPETA_BUFER, exist_ok=True)
        trozos = self._segundos_bufer() // N.SEG + 3
        cfg_s = self._cfg_sesion(fuente)
        if conservar and self._bufer_en_ram != self._usar_ram():
            conservar = False  # cambió el modo: lo anterior ya no sirve
        self._bufer_en_ram = self._usar_ram()
        if self._bufer_en_ram:
            # todo por stdout; BuferRAM lo corta en trozos de N.SEG segundos en la memoria
            self._ram.max_trozos = trozos
            self._bufer = N.Sesion(int(cfg_s["fps"]), self._encoder_video(), cfg_s,
                                   ["-f", "mpegts", "pipe:1"], "bufer.log", fuente, a_tuberia=True)
            self._ram.nueva_tanda(self._bufer.ffmpeg.stdout, conservar)
        else:
            formato, ext = self._formato_bufer()
            salida = os.path.join(N.CARPETA_BUFER, f"g{gen}_seg%04d.{ext}")
            self._bufer = N.Sesion(int(cfg_s["fps"]), self._encoder_video(), cfg_s,
                                   ["-f", "segment", "-segment_time", str(N.SEG),
                                    "-segment_wrap", str(trozos), "-reset_timestamps", "1",
                                    "-segment_format", formato, salida],
                                   "bufer.log", fuente)
        if self._mic_mudo:
            self._bufer.silenciar_mic(True)
        self._clave_bufer = self._clave(fuente)
        self._inicio_bufer = time.time()
        if conservar:
            return
        self._avisar_poco_espacio()
        que = fuente["nombre"] if fuente["tipo"] == "ventana" else "la pantalla"
        msg = f"Clips activos en {que}: {N.tecla_bonita(self._cfg['tecla_clip'])} guarda los últimos {self._cfg['duracion']} s"
        self._aviso(msg + self._bufer.aviso, "error" if self._bufer.aviso else "ok")

    def _parar_bufer(self):
        if self._bufer:
            self._bufer.detener()
        self._bufer = None
        self._clave_bufer = None
        self._ram.limpiar()  # devuelve la memoria

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
                    if self._bufer and self._bufer.fuente.get("tipo") == "ventana" \
                            and not VA.ventana_viva(self._bufer.fuente.get("hwnd")):
                        self._bufer.detener()
                        self._clip_de_cierre(self._bufer)  # se cerró el juego
                    self._parar_bufer()
                    if fuente:
                        self._iniciar_bufer(fuente)
                    else:
                        self._aviso("Se cerró el juego: los clips esperan a que abras otro")
                self._avisar_estado()
            except Exception:
                pass

    def guardar_clip_largo(self):
        return self.guardar_clip(int(self._cfg.get("duracion_larga") or 120), "Clip largo")

    def guardar_clip(self, segundos=None, titulo="Clip guardado"):
        segundos = int(segundos or self._cfg["duracion"])
        with self._lock:
            if not self._bufer:
                self._aviso("No hay ningún juego abierto para guardar un clip" if self._clips_on
                            else "Activa los clips primero", "error")
                return self._estado()
            self._guardar_tramo(segundos, self._bufer.fuente, self._bufer.pistas, titulo)
        self._avisar_estado()
        return self._estado()

    def _guardar_tramo(self, segundos, fuente, pistas, titulo="Clip guardado", sufijo="", quitar_ultimo=True):
        """Junta los últimos trozos del búfer en un MP4 (sin recomprimir)."""
        with self._lock:
            if self._bufer_en_ram:
                trozos, n_trozos = self._ram.volcar(os.path.join(N.CARPETA_BUFER, "ram"), max(1, segundos // N.SEG))
            else:
                trozos = sorted(glob.glob(os.path.join(N.CARPETA_BUFER, "g*_seg*.*")), key=os.path.getmtime)
                if quitar_ultimo:
                    trozos = trozos[:-1]  # el ultimo todavía se esta escribiendo
                trozos = [t for t in trozos if os.path.getsize(t) > 0][-max(1, segundos // N.SEG):]
                n_trozos = len(trozos)
            if not trozos:
                self._aviso("Aún no hay suficiente video, espera unos segundos", "error")
                return None
            lista = os.path.join(N.CARPETA_BUFER, "lista.txt")
            with open(lista, "w", encoding="utf-8") as f:
                for t in trozos:
                    f.write("file '" + t.replace("\\", "/").replace("'", "'\\''") + "'\n")
            juego = self._carpeta_destino(fuente)
            destino = os.path.join(N.CARPETA_SALIDA, juego, f"clip_{N.marca_tiempo()}{sufijo}.mp4")
            os.makedirs(os.path.dirname(destino), exist_ok=True)
            args = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "concat", "-safe", "0", "-i", lista, "-map", "0", "-c", "copy"]
            if pistas:
                args += ["-bsf:a", "aac_adtstoasc"] + N.metadatos(pistas)
            args += ["-movflags", "+faststart", destino]
            r = N.correr(args)
            if r.returncode != 0:
                os.makedirs(N.CARPETA_LOGS, exist_ok=True)
                with open(os.path.join(N.CARPETA_LOGS, "clip.log"), "wb") as f:
                    f.write(r.stderr)
                self._aviso("No se pudo guardar el clip", "error")
                return None
            self._ultimo = destino
            self._avisar("clip", "clip")
            extra = ""
            if self._cfg.get("quitar_mudas", True) and len(pistas or []) > 1:
                quedan = N.quitar_pistas_mudas(destino, pistas)
                quitadas = len(pistas) - len(quedan)
                if quitadas:
                    extra = f" (sin {quitadas} {'pista vacía' if quitadas == 1 else 'pistas vacías'})"
            self._aviso(f"{titulo} en {juego or 'GrabaClip'}{extra}", "ok")
            threading.Thread(target=self._aplicar_limite, args=(destino,), daemon=True).start()
            real = n_trozos * N.SEG
            self._avisar("clip", titulo=I18N.t_overlay(titulo), detalle=f"{juego or I18N.t_overlay('Escritorio')} · "
                         + (f"{real // 60}:{real % 60:02d} min" if real >= 60 else f"{real} s"))
            self._emitir("biblioteca")
            return destino

    def _clip_de_cierre(self, sesion):
        """Al cerrarse el juego, guarda solo el último tramo (si se activó en Ajustes)."""
        if not sesion or not self._cfg.get("clip_al_cerrar") or sesion.fuente.get("tipo") != "ventana":
            return
        if getattr(sesion, "_cierre_guardado", False):
            return
        sesion._cierre_guardado = True
        if time.time() - (self._inicio_bufer or 0) < 20:  # el juego apenas estuvo abierto
            return
        self._guardar_tramo(int(self._cfg["duracion"]), sesion.fuente, sesion.pistas,
                            "Clip del final de la partida", "_final", quitar_ultimo=False)

    def alternar_grabacion(self):
        if not self._funcion("grabar") and not self._grab:
            self._aviso("La grabación está apagada en tu perfil (Ajustes → General → Perfil)", "error")
            return self._estado()
        with self._lock:
            if self._grab:
                self._grab.detener()
                pistas, archivo = self._grab.pistas, self._archivo_grab
                self._grab = None
                self._inicio_grab = None
                self._ultimo = archivo
                self._aviso("Grabación guardada: " + os.path.basename(archivo), "ok")
                self._avisar("grabacion", "clip", I18N.t_overlay("Grabación guardada"),
                             os.path.basename(os.path.dirname(archivo)) or "GrabaClip")
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
                self._avisar_poco_espacio()
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
        cfg_s = self._cfg_sesion(fuente)
        self._grab = N.Sesion(int(cfg_s["fps"]), self._encoder_video(), cfg_s,
                              ["-movflags", "+faststart", self._archivo_grab], "grabacion.log", fuente)
        if self._mic_mudo:
            self._grab.silenciar_mic(True)
        if not base:
            self._inicio_grab = time.time() * 1000
        self._inicio_parte = time.time()
        return juego

    def _segundos_bufer(self):
        """El búfer guarda lo suficiente para el clip normal y para el clip largo."""
        return max(int(self._cfg["duracion"]), int(self._cfg.get("duracion_larga") or 0))

    def _cfg_sesion(self, fuente):
        """Ajustes de video propios del juego (si se configuraron) sobre los generales."""
        exe = ((fuente or {}).get("exe") or "").lower()
        propio = (self._cfg.get("por_juego_cfg") or {}).get(exe) or {}
        cambios = {k: v for k, v in propio.items() if k in ("fps", "calidad", "resolucion") and v}
        if self._webcam_fallida and self._cfg.get("webcam"):
            cambios["webcam"] = ""
        return dict(self._cfg, **cambios) if cambios else self._cfg

    def _alternar_ventana(self):
        """Tecla para mostrar u ocultar GrabaClip sin buscar el ícono."""
        try:
            visible = bool(self._ventana.native.Visible)
            import System.Windows.Forms as WF
            minimizada = self._ventana.native.WindowState == WF.FormWindowState.Minimized
            import ctypes
            delante = ctypes.windll.user32.GetForegroundWindow() == int(self._ventana.native.Handle.ToInt64())
        except Exception:
            visible, minimizada, delante = False, False, False
        if visible and not minimizada and delante:
            if self._bandeja and self._cfg.get("bandeja", True):
                self._esconder()
            else:
                self._ventana.minimize()
        else:
            self._mostrar_ventana()

    def vista_previa(self, ruta):
        if not self._ruta_valida(ruta) or not ruta.lower().endswith(".mp4"):
            return None
        return self._servidor_video.url(ruta, "vista")

    def ventanas_juegos(self):
        """Para 'Ajustes por juego': ventanas abiertas y juegos ya configurados."""
        lista = {v["exe"].lower(): v["nombre"] for v in VA.ventanas_abiertas() if v["exe"] not in VA.PROPIOS}
        for exe, c in (self._cfg.get("por_juego_cfg") or {}).items():
            lista.setdefault(exe, c.get("nombre") or exe)
        return [{"exe": e, "nombre": n} for e, n in sorted(lista.items(), key=lambda x: x[1].lower())]

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
        self._av1 = N.probar_av1(elegido)
        self._encoder = elegido
        try:
            with open(os.path.join(N.CARPETA_LOGS, "gpu.txt"), "w", encoding="utf-8") as f:
                f.write(f"Preferencia: {self._cfg.get('encoder', 'auto')}\nElegido: {elegido}\n")
                f.write(f"Captura directa: {N.MODO_GPU['directo']}  Escala en GPU: {N.MODO_GPU['escala']}  "
                        f"Captura de ventana: {N.MODO_GPU['ventana']}\n")
                f.write(f"Pantallas: {self._monitores}\n\n")
                for e, (ok, motivo) in self._encoders.items():
                    f.write(f"{e}: {'funciona' if ok else 'no funciona - ' + motivo}\n")
                f.write(f"AV1: {'funciona (' + self._av1[2] + ')' if self._av1[0] else 'no - ' + self._av1[1]}\n")
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
        self._aplicar_limite()
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
            self._saliendo = True
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

    # ---------- accesos directos (escritorio y menú Inicio) ----------
    @staticmethod
    def _carpeta_conocida(donde):
        """Escritorio o menú Inicio del usuario (respeta OneDrive y carpetas movidas)."""
        import ctypes
        import uuid as _uuid
        guid = {"escritorio": "{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}",
                "inicio": "{A77F5D77-2E2B-44C3-A6A2-ABA601054A51}"}[donde]

        class GUID(ctypes.Structure):
            _fields_ = [("bytes", ctypes.c_byte * 16)]
        g = GUID()
        ctypes.memmove(ctypes.byref(g), _uuid.UUID(guid).bytes_le, 16)
        ruta = ctypes.c_wchar_p()
        shell32, ole32 = ctypes.windll.shell32, ctypes.windll.ole32
        if shell32.SHGetKnownFolderPath(ctypes.byref(g), 0, None, ctypes.byref(ruta)) != 0:
            raise OSError("no se encontró la carpeta")
        try:
            return ruta.value
        finally:
            ole32.CoTaskMemFree(ruta)

    def _ruta_acceso(self, donde):
        return os.path.join(self._carpeta_conocida(donde), "GrabaClip.lnk")

    def accesos(self):
        estado = {"instalado": os.path.normcase(N.CARPETA_APP).startswith(
            os.path.normcase(os.path.join(os.environ.get("LOCALAPPDATA", "~~"), "Programs")))}
        for d in ("escritorio", "inicio"):
            try:
                estado[d] = os.path.exists(self._ruta_acceso(d))
            except Exception:
                estado[d] = None
        return estado

    def crear_acceso(self, donde):
        """Crea GrabaClip.lnk apuntando a GrabaClip.exe (con PowerShell y WScript.Shell, sin ventana)."""
        try:
            destino = self._ruta_acceso(donde)
        except Exception:
            return {"ok": False, "msg": "No encontré esa carpeta de Windows"}
        if not os.path.exists(LANZADOR):
            return {"ok": False, "msg": "Falta GrabaClip.exe en la carpeta de la app"}
        script = ("$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:GC_LNK); "
                  "$s.TargetPath = $env:GC_EXE; $s.WorkingDirectory = $env:GC_DIR; "
                  "$s.IconLocation = $env:GC_ICO; $s.Description = 'GrabaClip'; $s.Save()")
        entorno = dict(os.environ, GC_LNK=destino, GC_EXE=LANZADOR, GC_DIR=N.CARPETA_APP,
                       GC_ICO=(ARCHIVO_ICONO if os.path.exists(ARCHIVO_ICONO) else LANZADOR) + ",0")
        try:
            r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                                "-Command", script], env=entorno, capture_output=True, timeout=30,
                               creationflags=N.SIN_VENTANA)
        except Exception:
            return {"ok": False, "msg": "No se pudo crear el acceso directo"}
        if r.returncode != 0 or not os.path.exists(destino):
            return {"ok": False, "msg": "No se pudo crear el acceso directo"}
        return {"ok": True, "msg": "Acceso directo creado en el escritorio" if donde == "escritorio"
                else "GrabaClip ya aparece en el menú Inicio", "accesos": self.accesos()}

    def quitar_acceso(self, donde):
        try:
            ruta = self._ruta_acceso(donde)
            if os.path.exists(ruta):
                os.remove(ruta)  # solo el GrabaClip.lnk que crea la app
        except Exception:
            return {"ok": False, "msg": "No se pudo quitar el acceso directo"}
        return {"ok": True, "msg": "Acceso directo quitado", "accesos": self.accesos()}

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
        teclas = ("tecla_clip", "tecla_grab", "tecla_activar", "tecla_captura", "tecla_marca",
                  "tecla_clip_largo", "tecla_ventana", "tecla_mic")
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
            archivos += glob.glob(os.path.join(glob.escape(N.CARPETA_SALIDA), "**", "captura_*.png"), recursive=True)
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
                "tipo": ("clip" if nombre.lower().startswith("clip_") else
                         "captura" if nombre.lower().endswith(".png") else "grabacion"),
                "marcas": len(self._marcas.get(self._clave_fav(ruta), [])),
                "fav": self._es_favorito(ruta),
                "etiquetas": self._etiquetas.get(self._clave_fav(ruta), []),
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

    # ---------- recortar ----------
    def abrir_editor(self, ruta):
        if not self._ruta_valida(ruta):
            return {"ok": False, "msg": "No encuentro ese video"}
        return {"ok": True, "url": self._servidor_video.url(ruta),
                "marcas": self._marcas.get(self._clave_fav(ruta), []),
                "pistas": RC.pistas_video(ruta)}

    def cerrar_editor(self):
        self._servidor_video.olvidar("editor")

    def recortar(self, ruta, inicio, fin, reemplazar=False, pistas=None, vertical=False, velocidad=1, marca=""):
        if not self._ruta_valida(ruta):
            return {"ok": False, "msg": "No encuentro ese video"}
        if self._recortando:
            return {"ok": False, "msg": "Ya hay un recorte en marcha"}
        self._recortando = True
        threading.Thread(target=self._hacer_recorte, args=(ruta, inicio, fin, bool(reemplazar), pistas, bool(vertical),
                                                           velocidad, str(marca or "")[:60]),
                         daemon=True).start()
        return {"ok": True}

    def exportar_gif(self, ruta, inicio, fin, velocidad=1, marca=""):
        """GIF del tramo elegido en el editor; queda copiado para pegarlo en Discord."""
        if not self._ruta_valida(ruta):
            return {"ok": False, "msg": "No encuentro ese video"}
        if self._recortando:
            return {"ok": False, "msg": "Espera a que termine lo que se está preparando"}
        self._recortando = True

        def tarea():
            try:
                gif = RC.a_gif(ruta, inicio, fin, lambda x: self._emitir("recorte", {"pct": round(x * 100)}),
                               velocidad, str(marca or "")[:60])
                copiado = True
                try:
                    self._al_portapapeles(gif)
                except Exception:
                    copiado = False
                mb = f"{os.path.getsize(gif) / 1e6:.1f}".replace(".", ",")
                self._emitir("recorte", {"fin": True, "ok": True, "ruta": gif})
                self._aviso(f"GIF listo ({mb} MB)" + (": ya está copiado, pégalo con Ctrl+V" if copiado else ""), "ok")
            except Exception as ex:
                self._emitir("recorte", {"fin": True, "ok": False, "msg": str(ex)})
                self._aviso(str(ex), "error")
            finally:
                self._recortando = False
        threading.Thread(target=tarea, daemon=True).start()
        return {"ok": True}

    # ---------- resumen de la semana ----------
    def resumen_semana(self):
        """Un video con lo mejor de los últimos 7 días: favoritos primero, si no los más nuevos."""
        if self._recortando:
            return {"ok": False, "msg": "Espera a que termine lo que se está preparando"}
        limite = (time.time() - 7 * 86400) * 1000
        clips = [v for v in self.biblioteca() if v["tipo"] == "clip" and v["fecha"] >= limite
                 and not v["nombre"].lower().endswith(("_discord.mp4",))]
        favs = [v for v in clips if v["fav"]]
        elegidos = favs[:12] if len(favs) >= 3 else (favs + [v for v in clips if not v["fav"]])[:8]
        if len(elegidos) < 2:
            return {"ok": False, "msg": "Necesitas al menos 2 clips de esta semana para el resumen"}
        elegidos.sort(key=lambda v: v["fecha"])
        self._recortando = True

        def tarea():
            import datetime
            try:
                etiquetas = []
                for v in elegidos:
                    dia = datetime.datetime.fromtimestamp(v["fecha"] / 1000).strftime("%d/%m")
                    etiquetas.append(f"{v['juego'] or 'GrabaClip'} · {dia}")
                salida = os.path.join(N.CARPETA_SALIDA, f"resumen_semana_{N.marca_tiempo()}.mp4")
                nueva = RC.unir([v["ruta"] for v in elegidos], self._encoder, self._cfg.get("calidad"),
                                lambda x: self._emitir("resumen", {"pct": round(x * 100)}),
                                ultimos=8, etiquetas=etiquetas, titulo=I18N.t("Mi semana en GrabaClip"),
                                salida=salida)
                self._ultimo = nueva
                self._emitir("resumen", {"fin": True, "ok": True, "ruta": nueva})
                self._aviso(f"Resumen listo: {len(elegidos)} clips en {os.path.basename(nueva)}", "ok")
                self._emitir("biblioteca")
            except Exception as ex:
                self._emitir("resumen", {"fin": True, "ok": False})
                self._aviso(str(ex), "error")
            finally:
                self._recortando = False
        threading.Thread(target=tarea, daemon=True).start()
        return {"ok": True, "n": len(elegidos), "favs": len(favs) >= 3}

    def unir(self, rutas):
        rutas = [r for r in (rutas or []) if self._ruta_valida(r) and r.lower().endswith(".mp4")]
        if len(rutas) < 2:
            return {"ok": False, "msg": "Elige al menos dos videos para unir"}
        if self._recortando:
            return {"ok": False, "msg": "Espera a que termine lo que se está preparando"}
        self._recortando = True
        rutas.sort(key=lambda r: os.path.getmtime(r))  # en el orden en que se grabaron

        def tarea():
            try:
                nueva = RC.unir(rutas, self._encoder, self._cfg.get("calidad"),
                                lambda x: self._emitir("unir", {"pct": round(x * 100)}))
                self._ultimo = nueva
                self._emitir("unir", {"fin": True, "ok": True})
                self._aviso(f"Clips unidos: {os.path.basename(nueva)}", "ok")
                self._emitir("biblioteca")
            except Exception as ex:
                self._emitir("unir", {"fin": True, "ok": False})
                self._aviso(str(ex), "error")
            finally:
                self._recortando = False
        threading.Thread(target=tarea, daemon=True).start()
        return {"ok": True}

    def _hacer_recorte(self, ruta, inicio, fin, reemplazar, pistas=None, vertical=False, velocidad=1, marca=""):
        try:
            nueva = RC.recortar(ruta, inicio, fin, self._encoder, self._cfg.get("calidad"),
                                lambda x: self._emitir("recorte", {"pct": round(x * 100)}),
                                pistas=pistas, vertical=vertical, velocidad=velocidad, marca=marca)
            if reemplazar:
                self._servidor_video.olvidar()
                time.sleep(0.6)  # que el reproductor suelte el archivo
                if mandar_a_papelera(ruta):  # el original queda en la Papelera por si acaso
                    os.replace(nueva, ruta)
                    nueva = ruta
            self._ultimo = nueva
            self._emitir("recorte", {"fin": True, "ok": True, "ruta": nueva})
            self._aviso("Recorte guardado: " + os.path.basename(nueva) +
                        (" (el original está en la Papelera)" if reemplazar and nueva == ruta else ""), "ok")
            self._emitir("biblioteca")
        except Exception as ex:
            self._emitir("recorte", {"fin": True, "ok": False, "msg": str(ex)})
            self._aviso(str(ex), "error")
        finally:
            self._recortando = False

    # ---------- estadísticas ----------
    def estadisticas(self):
        """Resumen de la biblioteca: por juego, por semana y totales."""
        import datetime
        items = self.biblioteca()
        por_juego, semanas = {}, {}
        hoy = datetime.date.today()
        lunes = hoy - datetime.timedelta(days=hoy.weekday())
        for v in items:
            j = v["juego"] or "Sin clasificar"
            d = por_juego.setdefault(j, {"juego": j, "clips": 0, "grabaciones": 0, "capturas": 0, "segundos": 0, "bytes": 0})
            d[{"clip": "clips", "grabacion": "grabaciones", "captura": "capturas"}[v["tipo"]]] += 1
            d["segundos"] += v.get("duracion") or 0
            d["bytes"] += v["tamano"]
            if v["tipo"] == "clip":
                fecha = datetime.date.fromtimestamp(v["fecha"] / 1000)
                ini = fecha - datetime.timedelta(days=fecha.weekday())
                semanas[ini] = semanas.get(ini, 0) + 1
        ultimas = []
        for k in range(11, -1, -1):  # las últimas 12 semanas, de la más vieja a la actual
            ini = lunes - datetime.timedelta(weeks=k)
            ultimas.append({"desde": ini.strftime("%d/%m"), "clips": semanas.get(ini, 0)})
        mejor = max(semanas.items(), key=lambda x: x[1]) if semanas else None
        dias = {}
        for v in items:
            if v["tipo"] == "clip":
                d = datetime.date.fromtimestamp(v["fecha"] / 1000)
                dias[d] = dias.get(d, 0) + 1
        # racha: días seguidos con al menos un clip, contando hasta hoy (o hasta ayer si hoy aún no hay)
        d = hoy if dias.get(hoy) else hoy - datetime.timedelta(days=1)
        racha = 0
        while dias.get(d):
            racha += 1
            d -= datetime.timedelta(days=1)
        return {
            "juegos": sorted(por_juego.values(), key=lambda x: (-x["clips"], -x["grabaciones"], x["juego"])),
            "semanas": ultimas,
            "mejor_semana": {"desde": mejor[0].strftime("%d/%m/%Y"), "clips": mejor[1]} if mejor else None,
            "totales": {"clips": sum(1 for v in items if v["tipo"] == "clip"),
                        "grabaciones": sum(1 for v in items if v["tipo"] == "grabacion"),
                        "capturas": sum(1 for v in items if v["tipo"] == "captura"),
                        "favoritos": sum(1 for v in items if v.get("fav")),
                        "segundos": sum(v.get("duracion") or 0 for v in items),
                        "bytes": sum(v["tamano"] for v in items)},
            "racha": racha,
        }

    # ---------- espacio en disco ----------
    def _avisar_poco_espacio(self):
        try:
            libre = shutil.disk_usage(N.CARPETA_SALIDA).free
        except OSError:
            return
        if libre < 3e9:
            gb = f"{libre / 1e9:.1f}".replace(".", ",")
            self._aviso(f"Queda poco espacio en el disco ({gb} GB). Borra videos o pon un límite en Ajustes → General", "error")

    def _videos_en_disco(self):
        try:
            rutas = glob.glob(os.path.join(glob.escape(N.CARPETA_SALIDA), "**", "*.mp4"), recursive=True)
        except Exception:
            rutas = []
        lista = []
        for r in rutas:
            try:
                st = os.stat(r)
            except OSError:
                continue
            lista.append((r, st.st_size, st.st_mtime, os.path.basename(r).lower().startswith("clip_")))
        return lista

    def espacio(self):
        lista = self._videos_en_disco()
        try:
            libre = shutil.disk_usage(N.CARPETA_SALIDA).free
        except OSError:
            libre = None
        return {"total": sum(t for _, t, _, _ in lista), "n": len(lista),
                "clips": sum(t for _, t, _, c in lista if c), "n_clips": sum(1 for x in lista if x[3]),
                "libre": libre, "limite_gb": self._cfg.get("limite_gb", 0)}

    def _aplicar_limite(self, proteger=None):
        """Si los videos pasan del límite elegido, los más viejos van a la Papelera
        (solo clips, salvo que se incluyan las grabaciones). Nunca el clip recién guardado
        ni la grabación en curso."""
        limite = float(self._cfg.get("limite_gb") or 0) * 1e9
        if limite <= 0:
            return
        if not hasattr(self, "_candado_limite"):
            self._candado_limite = threading.Lock()
        if not self._candado_limite.acquire(blocking=False):
            return
        try:
            lista = self._videos_en_disco()
            total = sum(t for _, t, _, _ in lista)
            if total <= limite:
                return
            intocables = {os.path.normcase(p) for p in (proteger, self._archivo_grab if self._grab else None) if p}
            intocables |= {os.path.normcase(os.path.abspath(x[0])) for x in lista if self._es_favorito(x[0])}
            candidatos = sorted((x for x in lista
                                 if (x[3] or self._cfg.get("limite_grabaciones"))
                                 and os.path.normcase(x[0]) not in intocables), key=lambda x: x[2])
            meta = limite * 0.95  # un poco de margen para no borrar con cada clip nuevo
            enviados, liberado = 0, 0
            for ruta, tam, _, _ in candidatos[:300]:
                if total - liberado <= meta:
                    break
                if mandar_a_papelera(ruta):
                    enviados += 1
                    liberado += tam
            if enviados:
                gb = f"{liberado / 1e9:.1f}".replace(".", ",")
                self._aviso(f"Se enviaron {enviados} {'video viejo' if enviados == 1 else 'videos viejos'} a la Papelera "
                            f"({gb} GB) para no pasar de {self._cfg['limite_gb']} GB", "ok")
                self._emitir("biblioteca")
                self._emitir("espacio", self.espacio())
            elif total > limite:
                self._aviso("Tus videos pasan del límite de espacio, pero no queda nada que se pueda mandar a la Papelera"
                            + ("" if self._cfg.get("limite_grabaciones") else " (las grabaciones no se tocan)"), "error")
        finally:
            self._candado_limite.release()

    # ---------- compartir ----------
    def _al_portapapeles(self, ruta):
        """Copia el ARCHIVO (como Ctrl+C en el Explorador): se pega con Ctrl+V en Discord, etc."""
        from System import Action
        from System.Collections.Specialized import StringCollection
        import System.Windows.Forms as WF
        error = []

        def hacer():
            try:
                lista = StringCollection()
                lista.Add(os.path.normpath(ruta))
                WF.Clipboard.SetFileDropList(lista)
            except Exception as ex:
                error.append(ex)
        self._ventana.native.Invoke(Action(hacer))  # el portapapeles necesita el hilo de la ventana
        if error:
            raise error[0]

    def copiar_clip(self, ruta):
        if not self._ruta_valida(ruta):
            return {"ok": False, "msg": "No encuentro ese video"}
        try:
            self._al_portapapeles(ruta)
        except Exception:
            return {"ok": False, "msg": "No se pudo copiar al portapapeles"}
        return {"ok": True, "msg": "Clip copiado: pégalo con Ctrl+V en Discord, WhatsApp o una carpeta"}

    def preparar_discord(self, ruta):
        if not self._ruta_valida(ruta):
            return {"ok": False, "msg": "No encuentro ese video"}
        if self._recortando:
            return {"ok": False, "msg": "Espera a que termine lo que se está preparando"}
        self._recortando = True
        threading.Thread(target=self._hacer_discord, args=(ruta,), daemon=True).start()
        return {"ok": True}

    def _hacer_discord(self, ruta):
        try:
            nueva, tam = RC.para_discord(ruta, self._encoder,
                                         lambda x: self._emitir("compartir", {"pct": round(x * 100)}))
            copiado = True
            try:
                self._al_portapapeles(nueva)
            except Exception:
                copiado = False
            mb = f"{tam / 1e6:.1f}".replace(".", ",")
            self._emitir("compartir", {"fin": True, "ok": True, "ruta": nueva, "mb": mb, "copiado": copiado})
            self._aviso(f"Versión para Discord lista ({mb} MB)" +
                        (": ya está copiada, pégala con Ctrl+V" if copiado else ""), "ok")
            self._emitir("biblioteca")
        except Exception as ex:
            self._emitir("compartir", {"fin": True, "ok": False, "msg": str(ex)})
            self._aviso(str(ex), "error")
        finally:
            self._recortando = False

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
            marcas = self._marcas.get(self._clave_fav(archivo))
            if marcas:
                N.capitulos(archivo, marcas)  # las marcas también quedan como capítulos del MP4
            self._emitir("biblioteca")
        threading.Thread(target=tarea, daemon=True).start()

    def _ruta_valida(self, ruta):
        try:
            base = os.path.normcase(os.path.abspath(N.CARPETA_SALIDA))
            r = os.path.normcase(os.path.abspath(ruta))
            return os.path.commonpath([base, r]) == base and os.path.isfile(r)
        except Exception:
            return False

    # ---------- favoritos, renombrar y varios ----------
    @staticmethod
    def _clave_fav(ruta):
        return os.path.normcase(os.path.abspath(ruta))

    @staticmethod
    def _leer_json(ruta, defecto):
        try:
            with open(ruta, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return defecto

    @staticmethod
    def _guardar_json(ruta, datos):
        try:
            with open(ruta, "w", encoding="utf-8") as f:
                json.dump(datos, f, ensure_ascii=False)
        except Exception:
            pass

    # ---------- capturas de pantalla y marcas ----------
    def tomar_captura(self):
        if self._fatal:
            self._aviso(self._fatal, "error")
            return
        fuente = (self._bufer.fuente if self._bufer else None) or (self._grab.fuente if self._grab else None) \
            or self._fuente_deseada() or {"tipo": "monitor", "idx": int(self._cfg.get("monitor", 0) or 0)}
        juego = self._carpeta_destino(fuente)
        destino = os.path.join(N.CARPETA_SALIDA, juego, f"captura_{N.marca_tiempo()}.png")
        os.makedirs(os.path.dirname(destino), exist_ok=True)
        ok, err = N.captura_pantalla(fuente, destino)
        if not ok:
            with open(os.path.join(N.CARPETA_LOGS, "captura.log"), "w", encoding="utf-8") as f:
                f.write(err)
            self._aviso("No se pudo tomar la captura (revisa logs\\captura.log)", "error")
            return
        self._ultimo = destino
        self._avisar("captura", "clip", I18N.t_overlay("Captura guardada"), juego or I18N.t_overlay("Escritorio"))
        self._aviso(f"Captura guardada en {juego or 'GrabaClip'}", "ok")
        self._emitir("biblioteca")

    def poner_marca(self):
        if not self._grab or not self._inicio_parte:
            self._aviso(f"Las marcas son para grabaciones: pulsa {N.tecla_bonita(self._cfg['tecla_grab'])} para grabar", "error")
            self._avisar("marca", "desactivar")
            return
        seg = max(0.0, time.time() - self._inicio_parte - 0.5)
        clave = self._clave_fav(self._archivo_grab)
        lista = self._marcas.setdefault(clave, [])
        lista.append(round(seg, 2))
        self._guardar_json(ARCHIVO_MARCAS, self._marcas)
        m, s = divmod(int(seg), 60)
        h, m = divmod(m, 60)
        tiempo = f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
        self._avisar("marca", "activar", I18N.t_overlay(f"Marca {len(lista)}"), tiempo)
        self._aviso(f"Marca {len(lista)} en {tiempo}", "ok")

    def _leer_favoritos(self):
        try:
            with open(ARCHIVO_FAVORITOS, encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            return set()

    def _guardar_favoritos(self):
        try:
            with open(ARCHIVO_FAVORITOS, "w", encoding="utf-8") as f:
                json.dump(sorted(self._favoritos), f, ensure_ascii=False, indent=1)
        except Exception:
            pass

    def _es_favorito(self, ruta):
        return self._clave_fav(ruta) in self._favoritos

    def alternar_favorito(self, ruta):
        if not self._ruta_valida(ruta):
            return None
        c = self._clave_fav(ruta)
        if c in self._favoritos:
            self._favoritos.discard(c)
        else:
            self._favoritos.add(c)
        self._guardar_favoritos()
        return c in self._favoritos

    def favoritos_varios(self, rutas, valor):
        for r in rutas or []:
            if self._ruta_valida(r):
                (self._favoritos.add if valor else self._favoritos.discard)(self._clave_fav(r))
        self._guardar_favoritos()
        return True

    def renombrar(self, ruta, texto):
        """El nombre conserva el prefijo clip_ / grabacion_ (así se sabe qué tipo es)."""
        if not self._ruta_valida(ruta):
            return {"ok": False, "msg": "No encuentro ese video"}
        if self._grab and os.path.normcase(ruta) == os.path.normcase(self._archivo_grab or ""):
            return {"ok": False, "msg": "No se puede renombrar la grabación en curso"}
        ext = os.path.splitext(ruta)[1].lower() or ".mp4"
        texto = " ".join((texto or "").replace(ext, "").split()).strip(" .")
        if not texto:
            return {"ok": False, "msg": "Escribe un nombre"}
        if any(c in NO_VALIDOS for c in texto) or len(texto) > 120:
            return {"ok": False, "msg": 'El nombre no puede tener < > : " / \\ | ? * ni ser tan largo'}
        viejo = os.path.basename(ruta)
        prefijo = next((p for p in ("clip_", "captura_", "grabacion_") if viejo.lower().startswith(p)), "grabacion_")
        if texto.lower().startswith(prefijo):
            texto = texto[len(prefijo):]
        nuevo = os.path.join(os.path.dirname(ruta), f"{prefijo}{texto}{ext}")
        if os.path.normcase(nuevo) == os.path.normcase(ruta):
            return {"ok": True, "ruta": ruta, "nombre": viejo}
        if os.path.exists(nuevo):
            return {"ok": False, "msg": "Ya hay un video con ese nombre en la misma carpeta"}
        try:
            st = os.stat(ruta)
            os.rename(ruta, nuevo)
        except OSError:
            return {"ok": False, "msg": "No se pudo renombrar (¿está abierto en otro programa?)"}
        # se conservan la miniatura y el favorito
        juego = os.path.relpath(os.path.dirname(ruta), N.CARPETA_SALIDA)
        juego = "" if juego in (".", "") else juego.split(os.sep)[0]
        viejo_c = f"{juego}/{viejo}|{int(st.st_mtime)}|{st.st_size}"
        if viejo_c in self._indice:
            self._indice[f"{juego}/{os.path.basename(nuevo)}|{int(st.st_mtime)}|{st.st_size}"] = self._indice.pop(viejo_c)
            try:
                with open(ARCHIVO_INDICE, "w", encoding="utf-8") as f:
                    json.dump(self._indice, f)
            except Exception:
                pass
        if self._clave_fav(ruta) in self._marcas:
            self._marcas[self._clave_fav(nuevo)] = self._marcas.pop(self._clave_fav(ruta))
            self._guardar_json(ARCHIVO_MARCAS, self._marcas)
        if self._clave_fav(ruta) in self._favoritos:
            self._favoritos.discard(self._clave_fav(ruta))
            self._favoritos.add(self._clave_fav(nuevo))
            self._guardar_favoritos()
        if self._clave_fav(ruta) in self._etiquetas:
            self._etiquetas[self._clave_fav(nuevo)] = self._etiquetas.pop(self._clave_fav(ruta))
            self._guardar_json(ARCHIVO_ETIQUETAS, self._etiquetas)
        if self._ultimo and os.path.normcase(self._ultimo) == os.path.normcase(ruta):
            self._ultimo = nuevo
        return {"ok": True, "ruta": nuevo, "nombre": os.path.basename(nuevo)}

    # ---------- etiquetas propias ----------
    def lista_etiquetas(self):
        """Todas las etiquetas en uso, con cuántos videos tiene cada una (de las que aún existen)."""
        cuenta = {}
        for clave, tags in list(self._etiquetas.items()):
            if not os.path.exists(clave):
                continue
            for t in tags:
                cuenta[t] = cuenta.get(t, 0) + 1
        return sorted(({"nombre": t, "n": n} for t, n in cuenta.items()), key=lambda x: x["nombre"].lower())

    def etiquetar(self, rutas, etiqueta, valor=True):
        """Pone (valor=True) o quita una etiqueta a uno o varios videos."""
        etiqueta = " ".join(str(etiqueta or "").split())[:24]
        if not etiqueta:
            return {"ok": False, "msg": "Escribe un nombre para la etiqueta"}
        n = 0
        for r in rutas or []:
            if not self._ruta_valida(r):
                continue
            clave = self._clave_fav(r)
            tags = [t for t in self._etiquetas.get(clave, []) if t.lower() != etiqueta.lower()]
            if valor:
                tags.append(etiqueta)
            if tags:
                self._etiquetas[clave] = tags
            else:
                self._etiquetas.pop(clave, None)
            n += 1
        # se limpian las de videos que ya no existen
        self._etiquetas = {k: v for k, v in self._etiquetas.items() if os.path.exists(k)}
        self._guardar_json(ARCHIVO_ETIQUETAS, self._etiquetas)
        return {"ok": True, "n": n, "etiquetas": self.lista_etiquetas()}

    def borrar_etiqueta(self, etiqueta):
        """Quita una etiqueta de todos los videos (los videos no se tocan)."""
        for clave in list(self._etiquetas):
            self._etiquetas[clave] = [t for t in self._etiquetas[clave] if t != etiqueta]
            if not self._etiquetas[clave]:
                del self._etiquetas[clave]
        self._guardar_json(ARCHIVO_ETIQUETAS, self._etiquetas)
        return self.lista_etiquetas()

    # ---------- respaldo de ajustes ----------
    def exportar_ajustes(self):
        """Guarda los ajustes y los temas propios en un archivo .json para otra PC o un amigo."""
        try:
            import webview
            tipo = webview.FileDialog.SAVE if hasattr(webview, "FileDialog") else webview.SAVE_DIALOG
            destino = self._ventana.create_file_dialog(
                tipo, directory=os.path.join(os.path.expanduser("~"), "Documents"),
                save_filename=f"GrabaClip-ajustes-{time.strftime('%Y-%m-%d')}.json",
                file_types=("Ajustes de GrabaClip (*.json)",))
        except Exception:
            return {"ok": False, "msg": "No se pudo abrir la ventana para guardar"}
        if not destino:
            return {"ok": False, "cancelado": True}
        destino = destino[0] if isinstance(destino, (list, tuple)) else destino
        if not destino.lower().endswith(".json"):
            destino += ".json"
        datos = {"grabaclip": ACT.version_local(),
                 "ajustes": {k: v for k, v in self._cfg.items() if k not in NO_RESPALDAR}}
        try:
            with open(destino, "w", encoding="utf-8") as f:
                json.dump(datos, f, ensure_ascii=False, indent=1)
        except Exception:
            return {"ok": False, "msg": "No se pudo guardar el archivo"}
        return {"ok": True, "msg": "Ajustes guardados en " + os.path.basename(destino)}

    def importar_ajustes(self):
        if self._clips_on or self._grab:
            return {"ok": False, "msg": "Desactiva los clips y detén la grabación para cargar ajustes"}
        try:
            import webview
            tipo = webview.FileDialog.OPEN if hasattr(webview, "FileDialog") else webview.OPEN_DIALOG
            elegido = self._ventana.create_file_dialog(
                tipo, directory=os.path.join(os.path.expanduser("~"), "Documents"),
                file_types=("Ajustes de GrabaClip (*.json)",))
        except Exception:
            return {"ok": False, "msg": "No se pudo abrir la ventana para elegir el archivo"}
        if not elegido:
            return {"ok": False, "cancelado": True}
        ruta = elegido[0] if isinstance(elegido, (list, tuple)) else elegido
        try:
            with open(ruta, encoding="utf-8") as f:
                datos = json.load(f)
            nuevos = datos.get("ajustes")
            assert isinstance(nuevos, dict)
        except Exception:
            return {"ok": False, "msg": "Ese archivo no es un respaldo de GrabaClip"}
        with self._lock:
            n = 0
            def numero(x):
                return isinstance(x, (int, float)) and not isinstance(x, bool)
            for k, v in nuevos.items():
                if k not in N.CONFIG_INICIAL or k in NO_RESPALDAR:
                    continue
                base = N.CONFIG_INICIAL[k]
                # solo claves conocidas y con el mismo tipo de dato que el valor de fábrica
                if type(v) is type(base) or (numero(v) and numero(base)):
                    self._cfg[k] = v
                    n += 1
            N.guardar_config(self._cfg)
            I18N.elegir(self._cfg.get("idioma", "auto"))
            self._registrar_teclas()
            self._voz.configurar(self._cfg_efectiva())
            self._overlay.refrescar()
            self._pintar_barra()
        self._avisar_estado()
        return {"ok": True, "msg": f"Ajustes cargados ({n})", "cfg": self._cfg,
                "temas": N.temas_todos(self._cfg)}

    # ---------- medidor de impacto ----------
    def medir_impacto(self):
        """CPU, memoria, disco y codificador de video que usan GrabaClip y sus FFmpeg."""
        if self._medidor is None:
            try:
                import medidor as MD
                self._medidor = MD.Medidor()
            except Exception:
                self._medidor = False
        if not self._medidor:
            return None
        try:
            return self._medidor.medir()
        except Exception:
            return None

    def eliminar_varios(self, rutas):
        n = 0
        for r in rutas or []:
            if self._ruta_valida(r) and mandar_a_papelera(r):
                self._favoritos.discard(self._clave_fav(r))
                n += 1
        self._guardar_favoritos()
        self._aviso(f"{n} {'video enviado' if n == 1 else 'videos enviados'} a la Papelera" if n
                    else "No se pudo eliminar", "ok" if n else "error")
        return n

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
        return self._servidor_video.url_mini(info["mini"])

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
            momento = 0 if ruta.lower().endswith(".png") else min(2.0, (info["dur"] or 2) / 3)
            if ruta.lower().endswith(".png"):
                info["dur"], info["pistas"] = None, None
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
                    ("tecla_activar", self._alternar_clips_con_tecla), ("tecla_captura", self.tomar_captura),
                    ("tecla_marca", self.poner_marca), ("tecla_clip_largo", self.guardar_clip_largo),
                    ("tecla_ventana", self._alternar_ventana), ("tecla_mic", self.alternar_mic))
        necesita = {"tecla_clip": "clips", "tecla_activar": "clips", "tecla_clip_largo": "clips",
                    "tecla_grab": "grabar", "tecla_marca": "grabar", "tecla_captura": "capturas"}
        for clave, funcion in acciones:
            if not self._funcion(necesita.get(clave, "")):
                continue  # función apagada en el perfil: ni siquiera se escucha la tecla
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
        if self._clips_on != antes:
            self._avisar("clips", "activar" if self._clips_on else "desactivar",
                         I18N.t_overlay("Clips activados" if self._clips_on else "Clips desactivados"),
                         f"{N.tecla_bonita(self._cfg['tecla_clip'])} · {self._cfg['duracion']} s" if self._clips_on else "GrabaClip")

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
        if self._cfg.get("clips_al_abrir") and self._funcion("clips"):
            self.alternar_clips()

    def _vigilar(self):
        while True:
            time.sleep(0.5)
            with self._lock:
                cambio = False
                if self._bufer and not self._bufer.viva() and self._bufer.fallo_webcam() and self._clips_on:
                    fuente = self._bufer.fuente
                    self._bufer.cerrar_audio()
                    self._webcam_fallida = True
                    self._aviso("No se pudo abrir la webcam (¿la está usando otra app?): los clips siguen sin ella", "error")
                    self._iniciar_bufer(fuente, conservar=True)
                    cambio = True
                if self._grab and not self._grab.viva() and self._grab.fallo_webcam():
                    fuente, pistas, archivo = self._grab.fuente, self._grab.pistas, self._archivo_grab
                    self._grab.cerrar_audio()
                    self._webcam_fallida = True
                    base = os.path.splitext(os.path.basename(archivo))[0].split("_parte")[0]
                    if os.path.exists(archivo) and os.path.getsize(archivo) > 0:
                        self._terminar_grabacion(archivo, pistas)
                        self._parte_grab += 1
                        self._empezar_grabacion(fuente, base)
                    else:
                        self._empezar_grabacion(fuente, base if self._parte_grab > 1 else None)
                    self._aviso("No se pudo abrir la webcam (¿la está usando otra app?): se graba sin ella", "error")
                    cambio = True
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
                    if era_ventana and not VA.ventana_viva(self._bufer.fuente.get("hwnd")):
                        self._clip_de_cierre(self._bufer)  # se cerró el juego
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
        t = N.temas_todos(self._cfg).get(self._cfg.get("tema"), N.TEMAS["Oscuro"])
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

    def _funcion(self, nombre):
        return (self._cfg.get("funciones") or {}).get(nombre, True)

    def _cfg_efectiva(self):
        """Modo rendimiento y perfil: apagan partes sin olvidar lo que el usuario eligió en cada una."""
        cambios = {}
        if self._cfg.get("rendimiento"):
            cambios.update(overlay=False, voz=False)
        if not self._funcion("voz"):
            cambios["voz"] = False
        if not self._funcion("overlay"):
            cambios["overlay"] = False
        if not self._funcion("discord"):
            cambios["discord"] = False
        return dict(self._cfg, **cambios) if cambios else self._cfg

    # ---------- temas propios ----------
    def guardar_tema(self, nombre, colores):
        import re as _re
        nombre = " ".join((nombre or "").split())[:30]
        if not nombre:
            return {"ok": False, "msg": "Ponle un nombre a tu tema"}
        if nombre in N.TEMAS:
            return {"ok": False, "msg": "Ese nombre ya lo usa un tema de fábrica"}
        try:
            if any(not _re.fullmatch(r"#[0-9a-fA-F]{6}", str(colores[k]))
                   for k in ("bg", "panel", "campo", "fg", "tenue", "acento", "borde")):
                raise ValueError
            tema = N.tema_desde_colores({k: str(v).lower() for k, v in colores.items()})
        except Exception:
            return {"ok": False, "msg": "Algún color no es válido"}
        propios = dict(self._cfg.get("temas_propios") or {})
        propios[nombre] = tema
        self._cfg["temas_propios"] = propios
        self._cfg["tema"] = nombre
        N.guardar_config(self._cfg)
        self._pintar_barra()
        self._overlay.refrescar()
        return {"ok": True, "temas": N.temas_todos(self._cfg), "tema": nombre}

    def borrar_tema(self, nombre):
        propios = dict(self._cfg.get("temas_propios") or {})
        if nombre not in propios:
            return {"ok": False, "msg": "Ese tema no se puede borrar"}
        del propios[nombre]
        self._cfg["temas_propios"] = propios
        if self._cfg.get("tema") == nombre:
            self._cfg["tema"] = "Carmesí"
        N.guardar_config(self._cfg)
        self._pintar_barra()
        return {"ok": True, "temas": N.temas_todos(self._cfg), "tema": self._cfg["tema"]}

    def elegir_perfil(self, perfil, funciones=None):
        """Aplica un perfil (o 'personalizado' con las funciones elegidas una por una)."""
        with self._lock:
            if perfil == "personalizado":
                f = {k: bool((funciones or {}).get(k, self._funcion(k))) for k in N.FUNCIONES}
                ajustes = {}
            elif perfil in N.PERFILES:
                f, ajustes = dict(N.PERFILES[perfil]["funciones"]), dict(N.PERFILES[perfil]["ajustes"])
            else:
                return {"ok": False, "msg": "Perfil desconocido"}
            if not f["grabar"] and self._grab:
                return {"ok": False, "msg": "Termina la grabación antes de cambiar de perfil"}
            if not f["clips"] and self._clips_on:
                self._clips_on = False
                self._parar_bufer()
            self._cfg.update(ajustes)
            self._cfg["funciones"] = f
            self._cfg["perfil"] = perfil
            self._cfg["perfil_elegido"] = True
            N.guardar_config(self._cfg)
            self._registrar_teclas()
            self._voz.configurar(self._cfg_efectiva())
            self._overlay.refrescar()
        self._avisar_estado()
        return {"ok": True, "cfg": self._cfg}

    # ---------- liberar la interfaz cuando no se ve ----------
    def _liberar_interfaz(self):
        """Con la ventana escondida se descarga la página: WebView2 libera casi toda su memoria."""
        if self._ventana_visible():
            return  # la volvieron a abrir justo ahora
        try:
            self._url_ui = self._url_ui or self._ventana.get_current_url() or ARCHIVO_UI
            self._lista = False
            while not self._cola_ui.empty():  # lo pendiente ya no le sirve a la página
                try:
                    self._cola_ui.get_nowait()
                except queue.Empty:
                    break
            fondo = N.temas_todos(self._cfg).get(self._cfg.get("tema"), N.TEMAS["Carmesí"])["bg"]
            self._ventana.load_html(f"<html><body style='background:{fondo}'></body></html>")
            # (ya no se baja MemoryUsageTargetLevel: al volver a "Normal" WebView2 tenía que traer
            # todo de vuelta del disco y la ventana quedaba gris, "No responde")
        except Exception:
            pass

    def _recuperar_interfaz(self):
        """Vuelve a cargar la página (en un hilo aparte: nunca se espera desde un clic)."""
        if self._lista or not self._url_ui:
            return
        if not self._candado_recuperar.acquire(blocking=False):
            return  # ya se está cargando
        try:
            for intento in range(2):
                if intento and not self._ventana_visible():
                    return  # la escondieron otra vez mientras cargaba
                t0 = time.monotonic()
                self._ventana.load_url(self._url_ui)
                for _ in range(200):  # hasta 20 s a que la página avise que está lista
                    if self._lista or self._saliendo:
                        if time.monotonic() - t0 > 4:
                            self._log_bandeja(f"la interfaz tardó {time.monotonic() - t0:.1f} s en cargar")
                        return
                    time.sleep(0.1)
                self._log_bandeja(f"la interfaz no cargó (intento {intento + 1})")
        except Exception:
            self._log_bandeja(traceback.format_exc())
        finally:
            self._candado_recuperar.release()

    def _ventana_visible(self):
        try:
            return bool(self._ventana.native.Visible)
        except Exception:
            return False

    def _log_bandeja(self, texto):
        try:
            os.makedirs(N.CARPETA_LOGS, exist_ok=True)
            with open(os.path.join(N.CARPETA_LOGS, "bandeja.txt"), "a", encoding="utf-8") as f:
                f.write(time.ctime() + "  " + texto.rstrip() + "\n")
        except Exception:
            pass

    def _nivel_memoria(self, bajo):
        try:
            from System import Action
            from Microsoft.Web.WebView2.Core import CoreWebView2MemoryUsageTargetLevel as Nivel
            form = self._ventana.native
            core = form.browser.webview.CoreWebView2

            def hacer():
                core.MemoryUsageTargetLevel = Nivel.Low if bajo else Nivel.Normal
            form.Invoke(Action(hacer))
        except Exception:
            pass

    # ---------- bandeja (junto al reloj) ----------
    def _crear_bandeja(self):
        if self._bandeja or not self._ventana:
            return
        try:
            b = BJ.Bandeja(self._ventana.native, ARCHIVO_ICONO, {
                "abrir": self._mostrar_ventana,
                "clip": self.guardar_clip,
                "clips": self.alternar_clips,
                "grabar": self.alternar_grabacion,
                "salir": self.salir,
                "apagando": lambda: setattr(self, "_saliendo", True),
            }, lambda: {"clips": self._clips_on, "grabando": bool(self._grab)})
            b.crear()
            self._bandeja = b
            threading.Thread(target=self._vigilar_ventana, daemon=True).start()
        except Exception:
            with open(os.path.join(N.CARPETA_LOGS, "bandeja.txt"), "w", encoding="utf-8") as f:
                f.write(traceback.format_exc())
            return
        self._avisar_estado()
        if self._minimizado and self._cfg.get("bandeja", True):
            self._ventana.hide()  # al iniciar con Windows: directo junto al reloj
            time.sleep(1.5)
            self._liberar_interfaz()

    def _vigilar_ventana(self):
        """Diagnóstico: si la ventana deja de responder (Windows la marcaría "No responde"),
        se guarda qué estaba haciendo cada hilo en logs\\bloqueo.txt (una vez por sesión).
        Pregunta con SendMessageTimeout, que no necesita al hilo de la ventana ni al de Python.
        Además, faulthandler.dump_traceback_later escribe desde C aunque Python entero esté trabado."""
        import ctypes
        import faulthandler
        u32 = ctypes.windll.user32
        u32.SendMessageTimeoutW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p,
                                            ctypes.c_uint, ctypes.c_uint, ctypes.POINTER(ctypes.c_size_t)]
        try:
            hwnd = ctypes.c_void_p(int(self._ventana.native.Handle.ToInt64()))
        except Exception:
            return
        os.makedirs(N.CARPETA_LOGS, exist_ok=True)
        ruta = os.path.join(N.CARPETA_LOGS, "bloqueo.txt")
        sin_resp = 0
        while not self._saliendo:
            time.sleep(3)
            r = ctypes.c_size_t()
            ok = u32.SendMessageTimeoutW(hwnd, 0, None, None, 0x0002, 3000, ctypes.byref(r))  # WM_NULL, SMTO_ABORTIFHUNG
            if ok:
                if sin_resp:
                    self._log_bandeja(f"la ventana volvió a responder tras ~{sin_resp * 6} s")
                    try:
                        faulthandler.cancel_dump_traceback_later()
                    except Exception:
                        pass
                sin_resp = 0
                continue
            sin_resp += 1
            if sin_resp == 1:  # red de seguridad: si en 20 s Python tampoco puede escribir, lo hace C
                try:
                    self._f_bloqueo = open(ruta, "a", encoding="utf-8")
                    self._f_bloqueo.write(f"\n{time.ctime()}  la ventana no responde (volcado automático)\n")
                    self._f_bloqueo.flush()
                    faulthandler.dump_traceback_later(20, repeat=False, file=self._f_bloqueo)
                except Exception:
                    pass
            if sin_resp == 3:
                try:
                    faulthandler.cancel_dump_traceback_later()
                    with open(ruta, "a", encoding="utf-8") as f:
                        f.write(f"\n{time.ctime()}  la ventana lleva ~15 s sin responder\n\n")
                        faulthandler.dump_traceback(file=f, all_threads=True)
                except Exception:
                    pass

    def _al_cerrar_ventana(self):
        """Botón X: si la bandeja está activa, se esconde la ventana y GrabaClip sigue funcionando."""
        if self._saliendo or not self._bandeja or not self._cfg.get("bandeja", True):
            return True
        try:
            import ctypes
            if ctypes.windll.user32.GetSystemMetrics(0x2000):  # SM_SHUTTINGDOWN: Windows se apaga
                self._saliendo = True
                return True
        except Exception:
            pass
        threading.Thread(target=self._esconder, daemon=True).start()
        return False

    def _esconder(self):
        try:
            self._ventana.hide()
        except Exception:
            return
        self._liberar_interfaz()
        if not self._cfg.get("bandeja_aviso_visto"):
            self._cfg["bandeja_aviso_visto"] = True
            N.guardar_config(self._cfg)
            self._bandeja.globo(I18N.t("GrabaClip sigue funcionando"),
                                I18N.t("Está junto al reloj (en los íconos ocultos). Clic derecho para salir."))

    def _mostrar_ventana(self):
        """Clic, doble clic o "Abrir" en el ícono de la bandeja (o abrir GrabaClip.exe otra vez).
        La ventana se muestra directo en su hilo con BeginInvoke (sin esperar a nadie: así un
        doble clic nunca deja la bandeja trabada) y la página se recarga después, en otro hilo."""
        with self._candado_mostrar:
            ahora = time.monotonic()
            if ahora - self._ultimo_mostrar < 1.0:
                return  # doble clic = varias llamadas seguidas; basta con la primera
            self._ultimo_mostrar = ahora
        try:
            from System import Action
            import System.Windows.Forms as WF
            form = self._ventana.native

            def hacer():
                try:
                    if not form.Visible:
                        form.Show()
                    if form.WindowState == WF.FormWindowState.Minimized:
                        form.WindowState = WF.FormWindowState.Normal
                    form.Activate()
                    form.BringToFront()
                    try:
                        import ctypes
                        u32 = ctypes.windll.user32
                        hwnd = ctypes.c_void_p(form.Handle.ToInt64())
                        u32.ShowWindow(hwnd, 9)  # SW_RESTORE
                        u32.SetForegroundWindow(hwnd)
                    except Exception:
                        pass
                except Exception:
                    self._log_bandeja(traceback.format_exc())
            form.BeginInvoke(Action(hacer))
        except Exception:
            self._log_bandeja(traceback.format_exc())
            try:
                self._ventana.show()
            except Exception:
                pass
        threading.Thread(target=self._recuperar_interfaz, daemon=True).start()

    def salir(self):
        self._saliendo = True
        if self._bandeja:
            self._bandeja.quitar()
        try:
            self._ventana.destroy()
        except Exception:
            os._exit(0)

    def _cerrar(self):
        try:
            self._presencia.cerrar()
        except Exception:
            pass
        if self._bandeja:
            self._bandeja.quitar()
            self._bandeja = None
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
        # ALLOWUNDO | NOCONFIRMATION | SILENT | NOERRORUI | WANTNUKEWARNING (si no cabe en la
        # Papelera, Windows pregunta en vez de borrarlo para siempre sin avisar)
        op.fFlags = 0x40 | 0x10 | 0x04 | 0x400 | 0x4000
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
    t = N.temas_todos(api._cfg).get(api._cfg.get("tema"), N.TEMAS["Oscuro"])
    ventana = webview.create_window(
        N.APP, url=ARCHIVO_UI, js_api=api, width=1000, height=680, min_size=(820, 560),
        background_color=t["bg"], minimized=minimizado)
    api._ventana = ventana
    ventana.events.shown += api._pintar_barra
    ventana.events.shown += api._crear_bandeja
    ventana.events.closing += api._al_cerrar_ventana
    ventana.events.closed += api._cerrar
    try:
        webview.start(debug=False)
    except Exception:
        api._cerrar()
        modo_clasico(traceback.format_exc())
    candado.close()


if __name__ == "__main__":
    main()
