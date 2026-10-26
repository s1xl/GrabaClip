"""
Detecta que juego o programa esta en primer plano, para guardar cada clip en su carpeta.
"""
import os
import re
import sys
import time
import threading

# Nombres limpios para juegos y apps conocidos (exe en minusculas -> nombre de carpeta)
CONOCIDOS = {
    "fortniteclient-win64-shipping.exe": "Fortnite",
    "valorant-win64-shipping.exe": "Valorant",
    "overwatch.exe": "Overwatch",
    "cs2.exe": "Counter-Strike 2",
    "csgo.exe": "Counter-Strike GO",
    "r5apex.exe": "Apex Legends",
    "r5apex_dx12.exe": "Apex Legends",
    "league of legends.exe": "League of Legends",
    "rocketleague.exe": "Rocket League",
    "gta5.exe": "GTA V",
    "gta5_enhanced.exe": "GTA V",
    "rdr2.exe": "Red Dead Redemption 2",
    "robloxplayerbeta.exe": "Roblox",
    "javaw.exe": "Minecraft",
    "minecraft.windows.exe": "Minecraft",
    "eldenring.exe": "Elden Ring",
    "cod.exe": "Call of Duty",
    "cod24-cod.exe": "Call of Duty",
    "modernwarfare.exe": "Call of Duty",
    "dota2.exe": "Dota 2",
    "pubg-win64-shipping.exe": "PUBG",
    "tslgame.exe": "PUBG",
    "rainbowsix.exe": "Rainbow Six Siege",
    "rainbowsix_be.exe": "Rainbow Six Siege",
    "marvel-win64-shipping.exe": "Marvel Rivals",
    "deltaforce-win64-shipping.exe": "Delta Force",
    "fc25.exe": "EA FC 25",
    "fc26.exe": "EA FC 26",
    "destiny2.exe": "Destiny 2",
    "warframe.x64.exe": "Warframe",
    "helldivers2.exe": "Helldivers 2",
    "cyberpunk2077.exe": "Cyberpunk 2077",
    "thefinals.exe": "The Finals",
    "discord.exe": "Discord",
    "discordptb.exe": "Discord",
    "discordcanary.exe": "Discord",
    "chrome.exe": "Navegador",
    "msedge.exe": "Navegador",
    "firefox.exe": "Navegador",
    "opera.exe": "Navegador",
    "brave.exe": "Navegador",
    "explorer.exe": "Escritorio",
    "resolve.exe": "DaVinci Resolve",
}
# procesos de GrabaClip / del sistema que nunca cuentan como "lo que estas jugando"
PROPIOS = {"python.exe", "pythonw.exe", "grabaclip.exe", "msedgewebview2.exe", "audiocap.exe",
           "ffmpeg.exe", "shellexperiencehost.exe", "searchhost.exe", "startmenuexperiencehost.exe",
           "lockapp.exe", "textinputhost.exe", "applicationframehost.exe"}
SIN_NOMBRE = "Otros"


def limpiar_carpeta(nombre):
    nombre = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", nombre or "").strip(" .")
    nombre = re.sub(r"\s+", " ", nombre)
    return nombre[:60] or SIN_NOMBRE


_CACHE_DESC = {}


def _descripcion(ruta):
    if ruta not in _CACHE_DESC:
        _CACHE_DESC[ruta] = _leer_descripcion(ruta)
    return _CACHE_DESC[ruta]


def _leer_descripcion(ruta):
    """FileDescription del .exe (p. ej. 'Overwatch'), o '' si no tiene."""
    try:
        import ctypes
        from ctypes import wintypes
        ver = ctypes.windll.version
        tam = ver.GetFileVersionInfoSizeW(ruta, None)
        if not tam:
            return ""
        buf = ctypes.create_string_buffer(tam)
        if not ver.GetFileVersionInfoW(ruta, 0, tam, buf):
            return ""
        ptr = ctypes.c_void_p()
        largo = wintypes.UINT()
        if not ver.VerQueryValueW(buf, "\\VarFileInfo\\Translation", ctypes.byref(ptr), ctypes.byref(largo)) or not largo.value:
            idiomas = [(0x0409, 0x04B0)]
        else:
            arr = (ctypes.c_ushort * (largo.value // 2)).from_address(ptr.value)
            idiomas = [(arr[i], arr[i + 1]) for i in range(0, len(arr) - 1, 2)]
        for lang, cp in idiomas:
            clave = f"\\StringFileInfo\\{lang:04x}{cp:04x}\\FileDescription"
            if ver.VerQueryValueW(buf, clave, ctypes.byref(ptr), ctypes.byref(largo)) and largo.value:
                texto = ctypes.wstring_at(ptr.value, largo.value).strip("\x00 ").strip()
                if texto:
                    return texto
    except Exception:
        pass
    return ""


# apps que nunca se consideran "el juego" para la captura de ventana
NO_JUEGO = PROPIOS | {
    "explorer.exe", "discord.exe", "discordptb.exe", "discordcanary.exe", "chrome.exe", "msedge.exe",
    "firefox.exe", "opera.exe", "opera_gx.exe", "brave.exe", "spotify.exe", "steam.exe",
    "steamwebhelper.exe", "epicgameslauncher.exe", "battle.net.exe", "taskmgr.exe", "claude.exe",
    "nvidia app.exe", "nvidia overlay.exe", "obs64.exe", "systemsettings.exe", "windowsterminal.exe",
    "cmd.exe", "powershell.exe", "code.exe", "notepad.exe", "whatsapp.exe", "telegram.exe",
}


def _ruta_de(hwnd):
    import ctypes
    from ctypes import wintypes
    u32, k32 = ctypes.windll.user32, ctypes.windll.kernel32
    pid = wintypes.DWORD()
    u32.GetWindowThreadProcessId(ctypes.c_void_p(hwnd), ctypes.byref(pid))
    ruta = ""
    h = k32.OpenProcess(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
    if h:
        buf = ctypes.create_unicode_buffer(1024)
        n = wintypes.DWORD(1024)
        if k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)):
            ruta = buf.value
        k32.CloseHandle(h)
    return pid.value, ruta


def _titulo(hwnd):
    import ctypes
    t = ctypes.create_unicode_buffer(256)
    ctypes.windll.user32.GetWindowTextW(ctypes.c_void_p(hwnd), t, 256)
    return t.value


def nombre_para(exe, ruta, titulo=""):
    """Nombre limpio para carpetas y para mostrar (Overwatch, Fortnite...)."""
    if exe in CONOCIDOS:
        return CONOCIDOS[exe]
    nombre = _descripcion(ruta) if ruta else ""
    if not nombre or len(nombre) > 40:
        nombre = os.path.splitext(os.path.basename(ruta))[0] if ruta else titulo
    return limpiar_carpeta(nombre) if nombre else None


def en_primer_plano():
    """Devuelve (exe, nombre_carpeta, hwnd) de la ventana activa, o (None, None, None)."""
    if sys.platform != "win32":
        return None, None, None
    try:
        import ctypes
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        if not hwnd:
            return None, None, None
        pid, ruta = _ruta_de(hwnd)
        if pid == os.getpid():
            return "grabaclip.exe", None, hwnd
        exe = os.path.basename(ruta).lower() if ruta else ""
        if exe in PROPIOS:
            return exe, None, hwnd
        return exe or None, nombre_para(exe, ruta, _titulo(hwnd)), hwnd
    except Exception:
        return None, None, None


def ventanas_abiertas():
    """Ventanas normales abiertas, una por programa: [{exe, nombre, hwnd, titulo}]."""
    if sys.platform != "win32":
        return []
    import ctypes
    from ctypes import wintypes
    u32 = ctypes.windll.user32
    dwm = ctypes.windll.dwmapi
    encontradas = {}

    def cada(hwnd, _):
        try:
            if not u32.IsWindowVisible(hwnd) or u32.GetWindow(hwnd, 4):  # GW_OWNER
                return True
            if u32.GetWindowLongW(hwnd, -20) & 0x80:  # WS_EX_TOOLWINDOW
                return True
            oculta = ctypes.c_int(0)
            dwm.DwmGetWindowAttribute(hwnd, 14, ctypes.byref(oculta), 4)  # DWMWA_CLOAKED
            if oculta.value:
                return True
            titulo = _titulo(hwnd)
            if not titulo:
                return True
            pid, ruta = _ruta_de(hwnd)
            exe = os.path.basename(ruta).lower() if ruta else ""
            if not exe or exe in PROPIOS or pid == os.getpid():
                return True
            r = wintypes.RECT()
            u32.GetWindowRect(hwnd, ctypes.byref(r))
            area = max(0, r.right - r.left) * max(0, r.bottom - r.top)
            if exe not in encontradas or area > encontradas[exe]["area"]:
                encontradas[exe] = {"exe": exe, "nombre": nombre_para(exe, ruta, titulo) or exe,
                                    "hwnd": int(hwnd), "titulo": titulo, "area": area}
        except Exception:
            pass
        return True

    Proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    u32.EnumWindows(Proc(cada), None)
    lista = sorted(encontradas.values(), key=lambda v: v["nombre"].lower())
    for v in lista:
        v.pop("area", None)
    return lista


def ventana_de(exe):
    """hwnd de la ventana principal de un programa, o None si no esta abierto."""
    exe = (exe or "").lower()
    for v in ventanas_abiertas():
        if v["exe"] == exe:
            return v["hwnd"]
    return None


def ventana_viva(hwnd):
    try:
        import ctypes
        return bool(hwnd) and bool(ctypes.windll.user32.IsWindow(ctypes.c_void_p(hwnd)))
    except Exception:
        return False


class Rastreador:
    """Recuerda el ultimo juego/app (que no sea GrabaClip) que estuvo en primer plano,
    y aparte el ultimo "juego" (excluyendo navegadores, Discord, el escritorio...)."""

    def __init__(self):
        self.ultimo = None
        self.juego = None  # {"exe", "nombre", "hwnd"}
        threading.Thread(target=self._bucle, daemon=True).start()

    def _bucle(self):
        while True:
            self.actual()
            time.sleep(1)

    def actual(self):
        """Lo que esta en primer plano ahora; si es GrabaClip, lo ultimo que hubo antes."""
        exe, nombre, hwnd = en_primer_plano()
        if nombre:
            self.ultimo = nombre
            if exe and exe not in NO_JUEGO and hwnd:
                self.juego = {"exe": exe, "nombre": nombre, "hwnd": int(hwnd)}
            return nombre
        return self.ultimo or SIN_NOMBRE

    def juego_actual(self):
        """El ultimo juego que tuvo el foco, si su ventana sigue abierta."""
        if self.juego and ventana_viva(self.juego["hwnd"]):
            return self.juego
        return None
