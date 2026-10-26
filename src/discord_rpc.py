"""Discord Rich Presence de GrabaClip (sin dependencias).

Habla con la app de Discord abierta en la misma PC por su tubería local
(\\\\.\\pipe\\discord-ipc-N). No se conecta a internet por su cuenta: es Discord quien
muestra la actividad a tus amigos. Apagado por defecto (Ajustes > General).
"""
import json
import os
import struct
import threading
import time
import uuid

from idiomas import t

# ID público de la aplicación "GrabaClip" en el portal de desarrolladores de Discord.
# Discord muestra el nombre de esa aplicación ("Jugando a GrabaClip").
APP_ID = "1564255011373056132"
REPO = "https://github.com/s1xl/GrabaClip"
IMAGEN = "https://raw.githubusercontent.com/s1xl/GrabaClip/main/docs/icono.png"


class Presencia:
    def __init__(self):
        self._tuberia = None
        self._deseada = None      # actividad que se quiere mostrar (None = nada)
        self._enviada = "sin enviar"
        self._activo = False
        self._ultimo_envio = 0.0
        self._evento = threading.Event()
        self._lock = threading.Lock()
        threading.Thread(target=self._hilo, daemon=True).start()

    # ---------- desde GrabaClip ----------
    def actualizar(self, activo, estado, mostrar_juego=True):
        actividad = None
        if activo and APP_ID and (estado.get("clips") or estado.get("grabando")):
            juego = estado.get("fuente") if estado.get("fuente_tipo") == "ventana" else None
            if estado.get("grabando"):
                actividad = {"details": t("Grabando con GrabaClip")}
                if estado.get("inicio_grab"):
                    actividad["timestamps"] = {"start": int(estado["inicio_grab"] / 1000)}
            else:
                actividad = {"details": t("Clipeando con GrabaClip")}
            if juego and mostrar_juego:
                actividad["state"] = t("En " + juego[:100])
            elif estado.get("esperando"):
                actividad["state"] = t("Esperando un juego")
            else:
                actividad["state"] = t("Clips instantáneos activos" if not estado.get("grabando") else "Grabando la pantalla")
            actividad["assets"] = {"large_image": IMAGEN,
                                   "large_text": t("GrabaClip · clips instantáneos gratis y open source")}
            actividad["buttons"] = [{"label": t("Descargar GrabaClip"), "url": REPO}]
        with self._lock:
            self._activo = bool(activo and APP_ID)
            self._deseada = actividad
        self._evento.set()

    def cerrar(self):
        with self._lock:
            self._deseada = None
            self._activo = False
        try:
            if self._tuberia:
                self._mandar(1, {"cmd": "SET_ACTIVITY", "args": {"pid": os.getpid()}, "nonce": str(uuid.uuid4())})
        except Exception:
            pass
        self._desconectar()

    # ---------- protocolo ----------
    def _conectar(self):
        for i in range(10):
            try:
                t = open(rf"\\.\pipe\discord-ipc-{i}", "r+b", buffering=0)
            except OSError:
                continue
            self._tuberia = t
            try:
                self._mandar(0, {"v": 1, "client_id": APP_ID})
                op, datos = self._leer()
                if datos.get("evt") == "READY":
                    return True
            except Exception:
                pass
            self._desconectar()
        return False

    def _desconectar(self):
        try:
            if self._tuberia:
                self._tuberia.close()
        except Exception:
            pass
        self._tuberia = None
        self._enviada = "sin enviar"

    def _mandar(self, op, datos):
        cuerpo = json.dumps(datos).encode("utf-8")
        self._tuberia.write(struct.pack("<II", op, len(cuerpo)) + cuerpo)

    def _leer(self):
        cab = self._tuberia.read(8)
        if len(cab) < 8:
            raise ConnectionError("Discord se cerró")
        op, largo = struct.unpack("<II", cab)
        cuerpo = b""
        while len(cuerpo) < largo:
            trozo = self._tuberia.read(largo - len(cuerpo))
            if not trozo:
                raise ConnectionError("Discord se cerró")
            cuerpo += trozo
        return op, json.loads(cuerpo or b"{}")

    def _hilo(self):
        while True:
            self._evento.wait(15)  # cada 15 s reintenta por si Discord se abrió después
            self._evento.clear()
            with self._lock:
                activo, deseada = self._activo, self._deseada
            if not activo and not self._tuberia:
                continue
            clave = json.dumps(deseada, sort_keys=True)
            if clave == self._enviada and self._tuberia:
                continue
            espera = 4 - (time.time() - self._ultimo_envio)  # Discord limita los cambios seguidos
            if espera > 0:
                time.sleep(espera)
                with self._lock:
                    deseada = self._deseada
                clave = json.dumps(deseada, sort_keys=True)
            try:
                if not self._tuberia and not self._conectar():
                    continue
                args = {"pid": os.getpid()}
                if deseada:
                    args["activity"] = deseada
                self._mandar(1, {"cmd": "SET_ACTIVITY", "args": args, "nonce": str(uuid.uuid4())})
                self._leer()
                self._enviada = clave
                self._ultimo_envio = time.time()
                if not activo:
                    self._desconectar()
            except Exception:
                self._desconectar()
