"""Momentos automáticos: detecta kills mirando un pedacito fijo de la pantalla del juego.

No toca el juego ni su memoria: un FFmpeg aparte captura solo esa zona unas 4 veces por segundo
(ddagrab con recorte, o gfxcapture si se graba la ventana) y aquí se analiza la imagen.

- Fortnite: lee el contador de eliminaciones (el número junto a la calavera, arriba a la derecha).
  Si sube, son kills (puede subir varias de golpe al eliminar a un escuadrón).
- Overwatch: detecta el aviso amarillo de eliminación que aparece bajo la mira
  (calavera + nombre + daño). No depende del idioma del juego.

Las coordenadas están pensadas para 1920x1080 y se escalan con el alto de la pantalla
(el HUD de estos juegos crece con el alto). La zona capturada se escala de vuelta a 1080p
para que los patrones sirvan en cualquier resolución.
"""
import json
import os
import subprocess
import threading
import time

import nucleo as N

FPS = 4
DATOS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "momentos_datos.json")

# exe del juego -> clave
JUEGOS = {"fortniteclient-win64-shipping.exe": "fortnite", "overwatch.exe": "overwatch"}
NOMBRES = {"fortnite": "Fortnite", "overwatch": "Overwatch"}

# zona en coordenadas de 1080p: (ancla, x, y, ancho, alto). "der": x medido desde el borde derecho;
# "centro": x medido desde el centro de la pantalla.
ZONAS = {"fortnite": ("der", -320, 0, 130, 110),
         "overwatch": ("centro", -260, 700, 520, 200)}
# segundos sin otra kill para cerrar una racha (Overwatch y Fortnite cuentan rachas rápidas)
VENTANA_RACHA = {"fortnite": 10.0, "overwatch": 8.0}


# ---------------------------------------------------------------- Fortnite: contador ----
class LectorFortnite:
    """Lee el número de eliminaciones. Devuelve kills nuevas (0 si no cambió)."""
    UMBRAL = 190
    FILA = (34, 50)          # filas del contador dentro de la zona
    ICONO_X = (104, 126)     # columnas del ícono (calavera)

    def __init__(self, datos):
        import numpy as np
        self.np = np
        d = datos["fortnite"]
        self.P = np.array(d["digitos"], np.float32)
        self.icono = np.array([[c == "1" for c in fila] for fila in d["icono"]], np.float32)
        self.estable = None      # último valor confirmado
        self.candidato = None
        self.veces = 0
        self.ceros = 0

    def _cajas(self, img, y0, y1, x0=20, x1=104):
        b = img[y0:y1, x0:x1] > self.UMBRAL
        cols = b.any(0)
        out, x = [], 0
        while x < len(cols):
            if cols[x]:
                s = x
                while x < len(cols) and cols[x]:
                    x += 1
                filas = self.np.where(b[:, s:x].any(1))[0]
                out.append((s + x0, x + x0, filas[0] + y0, filas[-1] + 1 + y0))
            else:
                x += 1
        return out

    def _rasgos(self, img, caja, W=10, H=14):
        np = self.np
        xa, xb, ya, yb = caja
        g = img[ya:yb, xa:xb].astype(np.float32) / 255
        h, w = g.shape
        yi, xi = np.linspace(0, h, H + 1), np.linspace(0, w, W + 1)
        f = np.zeros((H, W), np.float32)
        for i in range(H):
            for j in range(W):
                a, b_ = int(yi[i]), int(xi[j])
                f[i, j] = g[a:max(a + 1, int(yi[i + 1])), b_:max(b_ + 1, int(xi[j + 1]))].mean()
        f = (f - f.mean()) / (f.std() + 1e-6)
        return np.concatenate([f.ravel(), [w / h * 3]])

    def leer(self, gris):
        np = self.np
        y0, y1 = self.FILA
        ic = (gris[y0:y1, self.ICONO_X[0]:self.ICONO_X[1]] > self.UMBRAL).astype(np.float32)
        if ic.shape != self.icono.shape or 1 - np.abs(ic - self.icono).mean() < 0.85:
            return None  # no se ve el contador (mapa abierto, muerto, espectando…)
        cajas = [c for c in self._cajas(gris, y0, y1) if 8 <= c[3] - c[2] <= 11 and 2 <= c[1] - c[0] <= 9]
        if not cajas:
            return None
        cajas.sort()
        num = [cajas[-1]]
        for c in reversed(cajas[:-1]):
            if num[0][0] - c[1] <= 4:
                num.insert(0, c)
            else:
                break
        if num[-1][1] < 92 or len(num) > 3:
            return None
        texto = ""
        for c in num:
            d = ((self.P - self._rasgos(gris, c)) ** 2).sum(1)
            orden = np.argsort(d)
            if d[orden[0]] > 0.8 * self.P.shape[1]:
                return None
            texto += str(int(orden[0]))
        return int(texto)

    def procesar(self, rgb):
        gris = rgb.mean(2)
        v = self.leer(gris)
        if v is None:
            return 0
        # un valor cuenta cuando se lee igual 2 veces seguidas (medio segundo)
        if v == self.candidato:
            self.veces += 1
        else:
            self.candidato, self.veces = v, 1
        if self.veces < 2:
            return 0
        if self.estable is None:
            self.estable = v
            return 0
        if v > self.estable and v - self.estable <= 8:
            nuevas = v - self.estable
            self.estable = v
            self.ceros = 0
            return nuevas
        if v == 0 and self.estable > 0:
            self.ceros += 1
            if self.ceros >= 3 * FPS:  # 0 estable unos segundos: partida nueva
                self.estable = 0
                self.ceros = 0
        else:
            self.ceros = 0
        return 0


# ------------------------------------------------------- Overwatch: aviso de eliminación ----
class LectorOverwatch:
    """Cuenta los avisos amarillos nuevos (calavera + nombre) que aparecen bajo la mira."""

    def __init__(self, datos=None):
        import numpy as np
        self.np = np
        self.vistos = []   # [momento, ancho, firma] de los avisos en pantalla hace poco
        self.t = 0.0

    def avisos(self, rgb):
        np = self.np
        X0, Y0 = 700, 700
        a = rgb.astype(np.int16)
        r, g, b = a[..., 0], a[..., 1], a[..., 2]
        amarillo = (r > 185) & (g > 185) & (b < 130) & (np.abs(r - g) < 50)
        filas = amarillo.sum(1)
        out, y, H = [], 0, rgb.shape[0]
        while y < H:
            if filas[y] >= 50:
                s = y
                while y < H and filas[y] >= 30:
                    y += 1
                if 20 <= y - s <= 40:
                    cols = np.where(amarillo[s:y].mean(0) > 0.35)[0]
                    if len(cols):
                        x0, x1 = int(cols.min()), int(cols.max())
                        w = x1 - x0
                        if 100 <= w <= 240 and abs(X0 + (x0 + x1) / 2 - 960) < 45:
                            izq = a[s + 5:y - 5, x0 + 6:x0 + 30].sum(2) < 300   # calavera oscura
                            if izq.size and izq.mean() > 0.12:
                                txt = a[s + 6:y - 6, x0 + 32:x1 - 34].sum(2) < 300
                                n = max(1, txt.shape[1] // 16)
                                firma = np.array([txt[:, i * n:(i + 1) * n].mean() if txt.size else 0
                                                  for i in range(16)])
                                out.append((w, firma))
            else:
                y += 1
        return out

    def procesar(self, rgb):
        np = self.np
        self.t += 1 / FPS
        self.vistos = [v for v in self.vistos if self.t - v[0] < 3.0]
        nuevas = 0
        for w, firma in self.avisos(rgb):
            iguales = [v for v in self.vistos if abs(v[1] - w) <= 6 and np.abs(v[2] - firma).mean() < 0.15]
            if iguales:
                for v in iguales:
                    v[0] = self.t
            else:
                nuevas += 1
                self.vistos.append([self.t, w, firma])
        return nuevas


LECTORES = {"fortnite": LectorFortnite, "overwatch": LectorOverwatch}


def _zona_en_pantalla(juego, ancho, alto):
    """(x, y, w, h) en píxeles reales para una pantalla/ventana de ancho x alto."""
    ancla, x, y, w, h = ZONAS[juego]
    s = alto / 1080
    base = ancho if ancla == "der" else ancho / 2
    zx, zy, zw, zh = round(base + x * s), round(y * s), round(w * s), round(h * s)
    zx = max(0, min(zx, ancho - zw))
    zy = max(0, min(zy, alto - zh))
    return zx, zy, zw - zw % 2, zh - zh % 2


class Detector:
    """Un FFmpeg que captura la zona del juego y un hilo que la analiza.
    al_detectar(kills, juego) se llama cada vez que hay kills nuevas."""

    def __init__(self, juego, fuente, al_detectar):
        self.juego = juego
        self.fuente = fuente
        self.al_detectar = al_detectar
        self.proc = None
        self.vivo = False
        with open(DATOS, encoding="utf-8") as f:
            self.lector = LECTORES[juego](json.load(f))

    def _filtro(self):
        _, _, _, W, H = ZONAS[self.juego]
        fuente = self.fuente
        if fuente.get("tipo") == "ventana" and N.MODO_GPU.get("ventana"):
            ancho, alto = N.tamano_ventana(fuente["hwnd"])
            x, y, w, h = _zona_en_pantalla(self.juego, ancho, alto)
            base = (f"gfxcapture=hwnd={int(fuente['hwnd'])}:max_framerate={FPS}:capture_cursor=0,"
                    f"fps={FPS},hwdownload,format=bgra,crop={w}:{h}:{x}:{y}")
        else:
            idx = int(fuente.get("idx", 0))
            pantallas = N.monitores()
            ancho, alto = pantallas[idx] if idx < len(pantallas) else (1920, 1080)
            x, y, w, h = _zona_en_pantalla(self.juego, ancho, alto)
            base = (f"ddagrab=output_idx={idx}:framerate={FPS}:draw_mouse=0:offset_x={x}:offset_y={y}"
                    f":video_size={w}x{h},hwdownload,format=bgra")
        return base + f",scale={W}:{H}:flags=bicubic,format=rgb24", W, H

    def iniciar(self):
        filtro, W, H = self._filtro()
        os.makedirs(N.CARPETA_LOGS, exist_ok=True)
        self.proc = subprocess.Popen(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", filtro,
             "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"],
            stdout=subprocess.PIPE, stdin=subprocess.DEVNULL,
            stderr=open(os.path.join(N.CARPETA_LOGS, "momentos.log"), "w"),
            creationflags=N.BAJA_PRIORIDAD, bufsize=0)
        self.vivo = True
        threading.Thread(target=self._leer, args=(W, H), daemon=True).start()

    def _leer(self, W, H):
        import numpy as np
        tam = W * H * 3
        datos = bytearray()
        try:
            while self.vivo:
                bloque = self.proc.stdout.read(tam - len(datos))
                if not bloque:
                    break
                datos += bloque
                if len(datos) < tam:
                    continue
                img = np.frombuffer(bytes(datos), np.uint8).reshape(H, W, 3)
                datos = bytearray()
                try:
                    n = self.lector.procesar(img)
                except Exception:
                    n = 0
                if n:
                    self.al_detectar(n, self.juego)
        finally:
            self.vivo = False

    def detener(self):
        self.vivo = False
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.kill()
            except Exception:
                pass


TITULOS = {1: "Kill", 2: "Doble kill", 3: "Triple kill", 4: "Cuádruple kill", 5: "Penta kill"}


def titulo_racha(n):
    return TITULOS.get(n, f"Racha de {n} kills")


class Rachas:
    """Junta kills seguidas y, cuando la racha termina, pide guardar un solo clip que la cubra."""

    def __init__(self, guardar):
        self.guardar = guardar          # guardar(juego, kills, segundos_desde_la_primera)
        self._lock = threading.Lock()
        self.juego = None
        self.kills = 0
        self.primera = self.ultima = 0.0
        threading.Thread(target=self._vigilar, daemon=True).start()

    def agregar(self, n, juego):
        with self._lock:
            ahora = time.monotonic()
            if self.kills and (juego != self.juego or ahora - self.ultima > VENTANA_RACHA.get(juego, 8)):
                self._cerrar()
            if not self.kills:
                self.primera = ahora
                self.juego = juego
            self.kills += n
            self.ultima = ahora

    def _cerrar(self):
        if self.kills:
            juego, kills, dur = self.juego, self.kills, time.monotonic() - self.primera
            self.kills = 0
            threading.Thread(target=self.guardar, args=(juego, kills, dur), daemon=True).start()

    def _vigilar(self):
        while True:
            time.sleep(0.5)
            with self._lock:
                if self.kills and time.monotonic() - self.ultima > VENTANA_RACHA.get(self.juego, 8):
                    self._cerrar()
