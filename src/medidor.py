"""Medidor de impacto: cuánto usan GrabaClip y sus ayudantes (FFmpeg, audiocap) de la PC.

Todo con APIs de Windows por ctypes, sin programas extra:
- CPU, memoria y escritura a disco de cada proceso (GetProcessTimes, GetProcessMemoryInfo,
  GetProcessIoCounters), sumando el proceso de GrabaClip y todos sus hijos.
- Uso del codificador de video de la GPU con el contador de rendimiento
  "\\GPU Engine(*engtype_VideoEncode)\\Utilization Percentage" (el mismo que muestra el
  Administrador de tareas), filtrando por los PID de GrabaClip.
Cada llamada a medir() compara con la anterior, así que la primera devuelve casi todo en 0.
"""
import ctypes
import os
import time
from ctypes import wintypes

k32 = ctypes.windll.kernel32
psapi = ctypes.windll.psapi

TH32CS_SNAPPROCESS = 0x2
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
PDH_FMT_DOUBLE = 0x200
PDH_MORE_DATA = 0x800007D2


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD),
                ("szExeFile", ctypes.c_wchar * 260)]


class PROCESS_MEMORY_COUNTERS_EX(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
                ("PrivateUsage", ctypes.c_size_t)]


class IO_COUNTERS(ctypes.Structure):
    _fields_ = [(n, ctypes.c_ulonglong) for n in ("ReadOperationCount", "WriteOperationCount",
                                                    "OtherOperationCount", "ReadTransferCount",
                                                    "WriteTransferCount", "OtherTransferCount")]


class PDH_VALOR(ctypes.Structure):
    _fields_ = [("CStatus", wintypes.DWORD), ("doubleValue", ctypes.c_double)]


class PDH_ITEM(ctypes.Structure):
    _fields_ = [("szName", ctypes.c_wchar_p), ("FmtValue", PDH_VALOR)]


k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
k32.OpenProcess.restype = wintypes.HANDLE


def _arbol(raiz):
    """PID de GrabaClip y de todos sus descendientes."""
    hijos = {}
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if not snap or snap == wintypes.HANDLE(-1).value:
        return {raiz}
    try:
        e = PROCESSENTRY32W()
        e.dwSize = ctypes.sizeof(e)
        ok = k32.Process32FirstW(snap, ctypes.byref(e))
        while ok:
            hijos.setdefault(e.th32ParentProcessID, []).append(e.th32ProcessID)
            ok = k32.Process32NextW(snap, ctypes.byref(e))
    finally:
        k32.CloseHandle(snap)
    todos, pendientes = {raiz}, [raiz]
    while pendientes:
        for h in hijos.get(pendientes.pop(), []):
            if h not in todos and h != 0:
                todos.add(h)
                pendientes.append(h)
    return todos


def _datos(pid):
    """(segundos de CPU, bytes de memoria privada, bytes escritos) de un proceso."""
    h = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return None
    try:
        c, s, kern, user = (wintypes.FILETIME() for _ in range(4))
        cpu = 0.0
        if k32.GetProcessTimes(h, ctypes.byref(c), ctypes.byref(s), ctypes.byref(kern), ctypes.byref(user)):
            cpu = sum(((t.dwHighDateTime << 32) | t.dwLowDateTime) for t in (kern, user)) / 1e7
        mem = PROCESS_MEMORY_COUNTERS_EX()
        mem.cb = ctypes.sizeof(mem)
        ram = mem.PrivateUsage if psapi.GetProcessMemoryInfo(h, ctypes.byref(mem), mem.cb) else 0
        io = IO_COUNTERS()
        escrito = io.WriteTransferCount if k32.GetProcessIoCounters(h, ctypes.byref(io)) else 0
        return cpu, ram, escrito
    finally:
        k32.CloseHandle(h)


class _ContadorGPU:
    def __init__(self):
        self.pdh = ctypes.windll.pdh
        self.q = wintypes.HANDLE()
        self.c = wintypes.HANDLE()
        if self.pdh.PdhOpenQueryW(None, 0, ctypes.byref(self.q)) != 0:
            raise OSError("PdhOpenQuery")
        ruta = "\\GPU Engine(*engtype_VideoEncode)\\Utilization Percentage"
        if self.pdh.PdhAddEnglishCounterW(self.q, ruta, 0, ctypes.byref(self.c)) != 0:
            raise OSError("PdhAddEnglishCounter")
        self.pdh.PdhCollectQueryData(self.q)

    def leer(self, pids):
        """Suma del uso del codificador de video de esos procesos (en %)."""
        if self.pdh.PdhCollectQueryData(self.q) != 0:
            return None
        tam, n = wintypes.DWORD(0), wintypes.DWORD(0)
        r = self.pdh.PdhGetFormattedCounterArrayW(self.c, PDH_FMT_DOUBLE, ctypes.byref(tam), ctypes.byref(n), None)
        if r & 0xFFFFFFFF != PDH_MORE_DATA or not tam.value:
            return 0.0  # no hay ningún motor de codificación en uso
        buf = ctypes.create_string_buffer(tam.value)
        if self.pdh.PdhGetFormattedCounterArrayW(self.c, PDH_FMT_DOUBLE, ctypes.byref(tam), ctypes.byref(n), buf) != 0:
            return None
        items = ctypes.cast(buf, ctypes.POINTER(PDH_ITEM))
        total = 0.0
        for i in range(n.value):
            nombre = items[i].szName or ""
            try:  # "pid_1234_luid_0x..._engtype_VideoEncode"
                pid = int(nombre.split("_")[1])
            except (IndexError, ValueError):
                continue
            if pid in pids and items[i].FmtValue.CStatus in (0, 1):
                total += items[i].FmtValue.doubleValue
        return min(100.0, total)


class Medidor:
    def __init__(self):
        self._pid = os.getpid()
        self._antes = None  # (momento, {pid: (cpu, escrito)})
        self._ncpu = os.cpu_count() or 1
        try:
            self._gpu = _ContadorGPU()
        except Exception:
            self._gpu = None

    def medir(self):
        ahora = time.monotonic()
        pids = _arbol(self._pid)
        actuales, ram = {}, 0
        for pid in pids:
            d = _datos(pid)
            if d:
                actuales[pid] = (d[0], d[2])
                ram += d[1]
        cpu = disco = 0.0
        if self._antes:
            t0, previos = self._antes
            dt = max(0.2, ahora - t0)
            for pid, (c, w) in actuales.items():
                c0, w0 = previos.get(pid, (c, w))
                cpu += max(0.0, c - c0)
                disco += max(0, w - w0)
            cpu = cpu / dt / self._ncpu * 100
            disco = disco / dt / 1048576
        self._antes = (ahora, actuales)
        gpu = None
        if self._gpu:
            try:
                gpu = self._gpu.leer(pids)
            except Exception:
                gpu = None
        return {"cpu": round(cpu, 1), "ram_mb": round(ram / 1048576), "disco_mb_s": round(disco, 1),
                "gpu_enc": None if gpu is None else round(gpu, 1), "procesos": len(actuales)}
