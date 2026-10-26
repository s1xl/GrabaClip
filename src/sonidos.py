"""
Sonidos suaves de GrabaClip. Se generan una sola vez como archivos .wav
(campanitas con desvanecimiento) para no depender de los pitidos de Windows.
"""
import os
import math
import wave
import struct
import threading

FRECUENCIA = 44100


def _campanita(notas, volumen=0.32):
    """notas: [(hz, inicio_s, duracion_s)]. Tono con armonicos suaves y caida exponencial."""
    total = max(i + d for _, i, d in notas) + 0.05
    muestras = [0.0] * int(total * FRECUENCIA)
    for hz, inicio, dur in notas:
        a = int(inicio * FRECUENCIA)
        n = int(dur * FRECUENCIA)
        for k in range(n):
            t = k / FRECUENCIA
            ataque = min(1.0, t / 0.006)                 # sin chasquido al empezar
            caida = math.exp(-t * 7.5)
            v = (math.sin(2 * math.pi * hz * t)
                 + 0.28 * math.sin(2 * math.pi * hz * 2 * t) * math.exp(-t * 12)
                 + 0.10 * math.sin(2 * math.pi * hz * 3 * t) * math.exp(-t * 18))
            if a + k < len(muestras):
                muestras[a + k] += v * ataque * caida
    pico = max(1e-9, max(abs(x) for x in muestras))
    return [x / pico * volumen for x in muestras]


SONIDOS = {
    # clip guardado: do-sol agudo, como una notificacion amable
    "clip": [(1046.5, 0.0, 0.42), (1567.98, 0.09, 0.55)],
    # clips activados: dos notas que suben
    "activar": [(659.25, 0.0, 0.30), (987.77, 0.08, 0.40)],
    # clips desactivados: dos notas que bajan
    "desactivar": [(987.77, 0.0, 0.30), (659.25, 0.08, 0.40)],
}


def _escribir(ruta, muestras):
    with wave.open(ruta, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(FRECUENCIA)
        w.writeframes(b"".join(struct.pack("<h", int(max(-1, min(1, x)) * 32767)) for x in muestras))


def preparar(carpeta):
    """Crea los .wav si faltan. Devuelve {nombre: ruta}."""
    os.makedirs(carpeta, exist_ok=True)
    rutas = {}
    for nombre, notas in SONIDOS.items():
        ruta = os.path.join(carpeta, nombre + ".wav")
        if not os.path.exists(ruta):
            try:
                _escribir(ruta, _campanita(notas))
            except Exception:
                continue
        rutas[nombre] = ruta
    return rutas


class Sonidos:
    def __init__(self, carpeta):
        self.rutas = {}
        threading.Thread(target=lambda: self.rutas.update(preparar(carpeta)), daemon=True).start()

    def tocar(self, nombre):
        ruta = self.rutas.get(nombre)
        try:
            import winsound
            if ruta and os.path.exists(ruta):
                winsound.PlaySound(ruta, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
            else:
                winsound.MessageBeep(winsound.MB_OK)
        except Exception:
            pass
