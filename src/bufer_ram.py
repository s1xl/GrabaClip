"""Búfer de clips en memoria RAM (opcional, Ajustes → Video).

En vez de que FFmpeg escriba trocitos .ts al disco todo el tiempo, manda un solo MPEG-TS por
stdout y aquí se corta en trozos de N.SEG segundos, justo en cada fotograma clave (FFmpeg pone uno
cada N.SEG segundos). Solo al guardar un clip se escriben al disco los trozos que hacen falta.

Cómo se reconoce un fotograma clave sin decodificar nada: en MPEG-TS cada paquete mide 188 bytes;
el video es el PID 0x100 (el primer stream que mapea GrabaClip) y FFmpeg marca el inicio de cada
fotograma clave con "payload_unit_start" + "random_access_indicator" en el campo de adaptación.
"""
import collections
import os
import threading

PAQ = 188
PID_VIDEO = 0x100
CABEZA_VIDEO = b"\x47\x41\x00"  # sync + payload_unit_start + PID 0x100
CABEZA_PAT = b"\x47\x40\x00"    # PID 0
CABEZA_PMT = b"\x47\x50\x00"    # PID 0x1000 (el que usa FFmpeg)


class _Tanda:
    """Lo que sale de un FFmpeg (si se reinicia tras un corte, empieza otra tanda)."""

    def __init__(self):
        self.pat = None
        self.pmt = None
        self.trozos = collections.deque()
        self.actual = None  # trozo que se está llenando (None hasta el primer fotograma clave)
        self.bytes = 0

    def cabecera(self):
        return (self.pat or b"") + (self.pmt or b"")


class BuferRAM:
    def __init__(self):
        self._lock = threading.Lock()
        self._tandas = []
        self.max_trozos = 30

    # ---------- llenar ----------
    def nueva_tanda(self, salida, conservar=False):
        """salida: stdout de FFmpeg. conservar=True guarda la tanda anterior (como el búfer en disco)."""
        tanda = _Tanda()
        with self._lock:
            self._tandas = (self._tandas[-1:] if conservar else []) + [tanda]
        threading.Thread(target=self._leer, args=(tanda, salida), daemon=True).start()

    def _leer(self, tanda, salida):
        pend = bytearray()
        try:
            fd = salida.fileno()
            while True:
                bloque = os.read(fd, PAQ * 1024)
                if not bloque:
                    break
                pend += bloque
                completos = len(pend) - len(pend) % PAQ
                if completos:
                    self._procesar(tanda, pend, completos)
                    del pend[:completos]
        except Exception:
            pass
        finally:
            with self._lock:  # FFmpeg terminó: el último trozo queda completo
                if tanda.actual:
                    self._cerrar_trozo(tanda)
                tanda.actual = None

    @staticmethod
    def _buscar(datos, cab, desde, fin):
        """Primera aparición de cab al inicio de un paquete (posición múltiplo de 188)."""
        i = datos.find(cab, desde, fin)
        while i != -1 and i % PAQ:
            i = datos.find(cab, i + 1, fin)
        return i

    def _procesar(self, tanda, datos, fin):
        for cab, attr in ((CABEZA_PAT, "pat"), (CABEZA_PMT, "pmt")):
            if getattr(tanda, attr) is None:
                i = self._buscar(datos, cab, 0, fin)
                if i != -1:
                    setattr(tanda, attr, bytes(datos[i:i + PAQ]))
        inicio = 0
        pos = 0
        while True:
            i = self._buscar(datos, CABEZA_VIDEO, pos, fin)
            if i == -1:
                break
            pos = i + PAQ
            af = (datos[i + 3] >> 4) & 3
            if af in (2, 3) and datos[i + 4] > 0 and datos[i + 5] & 0x40:  # random_access_indicator
                with self._lock:
                    if tanda.actual is not None:
                        tanda.actual += datos[inicio:i]
                        self._cerrar_trozo(tanda)
                    tanda.actual = bytearray()
                inicio = i
        with self._lock:
            if tanda.actual is not None:
                tanda.actual += datos[inicio:fin]

    def _cerrar_trozo(self, tanda):
        tanda.trozos.append(bytes(tanda.actual))
        tanda.bytes += len(tanda.actual)
        tanda.actual = bytearray()
        total = sum(len(t.trozos) for t in self._tandas)
        while total > self.max_trozos:  # se tira lo más viejo, empezando por la tanda más vieja
            vieja = next(t for t in self._tandas if t.trozos)
            vieja.bytes -= len(vieja.trozos.popleft())
            total -= 1
        self._tandas = [t for t in self._tandas if t.trozos or t is self._tandas[-1]]

    # ---------- usar ----------
    def volcar(self, carpeta, cuantos):
        """Escribe los últimos `cuantos` trozos en archivos .ts (uno por tanda).
        Devuelve (rutas, cuántos trozos se escribieron)."""
        with self._lock:
            elegidos = []
            falta = cuantos
            for t in reversed(self._tandas):
                if falta <= 0:
                    break
                trozos = list(t.trozos)[-falta:]
                if trozos:
                    elegidos.insert(0, (t.cabecera(), trozos))
                    falta -= len(trozos)
        os.makedirs(carpeta, exist_ok=True)
        rutas = []
        for n, (cab, trozos) in enumerate(elegidos):
            ruta = os.path.join(carpeta, f"ram_{n}.ts")
            with open(ruta, "wb") as f:
                f.write(cab)  # PAT + PMT para que el trozo se pueda leer desde el principio
                for t in trozos:
                    f.write(t)
            rutas.append(ruta)
        return rutas, sum(len(tr) for _, tr in elegidos)

    def limpiar(self):
        with self._lock:
            self._tandas = []

    def megas(self):
        with self._lock:
            return round(sum(t.bytes + len(t.actual or b"") for t in self._tandas) / 1048576)
