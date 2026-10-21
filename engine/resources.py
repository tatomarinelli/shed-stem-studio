"""Monitor de recursos en tiempo real: CPU, RAM, placa de video, discos y procesos de la app.

Un muestreador en un hilo que solo corre mientras alguien lo pide (cada pedido a /engine/resources cuenta como una
suscripción; sin pedidos durante IDLE_SEC se apaga solo y cierra el nvidia-smi persistente). Guarda los últimos
5 minutos a 1 muestra por segundo. Solo librería estándar.

Estructura por plataforma: cada una implementa la misma interfaz chica (cpu_times, cores, memory, processes).
  - Linux: /proc y /sys. Implementado y probado.
  - Windows: ctypes (GetSystemTimes, GlobalMemoryStatusEx). SIN VERIFICAR EN WINDOWS: solo probado con simulaciones.
  - Otra plataforma: todo en null, nunca una excepción.
Una falla de una fuente no tumba a las demás: cada una va en su try y deja null.
"""
import csv
import ctypes
import glob
import io
import os
import shutil
import subprocess
import sys
import threading
import time
from collections import deque
from pathlib import Path

INTERVAL = 1.0        # segundos entre muestras
HISTORY_SEC = 300     # 5 minutos
IDLE_SEC = 10         # sin pedidos durante este tiempo, el muestreador se apaga
PROC_EVERY = 2        # procesos y memoria de video por proceso: cada N muestras (2 s)
DISK_EVERY = 10       # discos: cada N muestras
SMI_RETRY = 30        # si nvidia-smi murió, se reintenta cada tanto mientras haya suscriptores
SMI_FIELDS = "index,name,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw"
MIB = 1024 * 1024


def _num(text):
    """Texto de nvidia-smi -> número, o None ("[N/A]", "[Not Supported]", vacío)."""
    try:
        return float(str(text).strip())
    except (TypeError, ValueError):
        return None


def parse_gpu_csv(text):
    """Salida de `nvidia-smi --query-gpu=<SMI_FIELDS> --format=csv,noheader,nounits` -> lista de placas (memoria en bytes)."""
    out = []
    for row in csv.reader(io.StringIO(text), skipinitialspace=True):
        if len(row) < 7:
            continue
        idx = _num(row[0])
        if idx is None:
            continue
        mem_used, mem_total = _num(row[3]), _num(row[4])
        out.append({"index": int(idx), "name": row[1].strip(), "vendor": "nvidia", "utilPercent": _num(row[2]),
                    "memUsedBytes": None if mem_used is None else int(mem_used * MIB),
                    "memTotalBytes": None if mem_total is None else int(mem_total * MIB),
                    "tempC": _num(row[5]), "powerW": _num(row[6])})
    return out


def parse_compute_apps(text):
    """Salida de `--query-compute-apps=pid,used_memory --format=csv,noheader,nounits` -> {pid: bytes (o None)}."""
    out = {}
    for row in csv.reader(io.StringIO(text), skipinitialspace=True):
        if len(row) < 2 or _num(row[0]) is None:
            continue
        mem = _num(row[1])
        out[int(_num(row[0]))] = None if mem is None else int(mem * MIB)
    return out


def find_smi():
    path = shutil.which("nvidia-smi")
    if path:
        return path
    if sys.platform == "win32":
        for cand in (os.path.expandvars(r"%SystemRoot%\System32\nvidia-smi.exe"),
                     os.path.expandvars(r"%ProgramFiles%\NVIDIA Corporation\NVSMI\nvidia-smi.exe")):
            if os.path.isfile(cand):
                return cand
    return None


class SmiStream:
    """Un único nvidia-smi persistente (-lms 1000) y un hilo que lee sus líneas. close() lo termina y espera."""

    def __init__(self, cmd, stale_sec=5.0, clock=time.time):
        self.cmd, self.stale, self.clock = cmd, stale_sec, clock
        self.proc = None
        self.rows = {}   # índice -> (instante, placa)
        self.lock = threading.Lock()
        self.last_start = 0.0

    def alive(self):
        return self.proc is not None and self.proc.poll() is None

    def start(self):
        self.last_start = self.clock()
        try:
            self.proc = subprocess.Popen(self.cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except (OSError, ValueError):
            self.proc = None
            return False
        threading.Thread(target=self._read, args=(self.proc,), daemon=True).start()
        return True

    def _read(self, proc):
        try:
            for line in proc.stdout:
                for gpu in parse_gpu_csv(line):
                    with self.lock:
                        self.rows[gpu["index"]] = (self.clock(), gpu)
        except (OSError, ValueError):
            pass

    def latest(self):
        now = self.clock()
        with self.lock:
            return [g for _, (t, g) in sorted(self.rows.items()) if now - t <= self.stale]

    def close(self):
        proc, self.proc = self.proc, None
        if proc is None:
            return
        try:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(3)
        except OSError:
            pass
        try:
            proc.stdout.close()
        except OSError:
            pass
        with self.lock:
            self.rows.clear()


def compute_apps_once(smi, timeout=3):
    """Memoria de video por proceso (una consulta suelta, a baja frecuencia). {} si no se puede."""
    try:
        r = subprocess.run([smi, "--query-compute-apps=pid,used_memory", "--format=csv,noheader,nounits"],
                           capture_output=True, text=True, timeout=timeout, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return parse_compute_apps(r.stdout) if r.returncode == 0 else {}
    except (OSError, subprocess.SubprocessError, ValueError):
        return {}


# ---------------------------------------------------------------------------------------------- AMD (sysfs, Linux)

def _read(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read().strip()


def amd_gpus(drm_root="/sys/class/drm"):
    """Placas AMD por sysfs: gpu_busy_percent, mem_info_vram_used/total (y temperatura/potencia si hay hwmon).
    SIN VERIFICAR EN HARDWARE AMD REAL: probado solo con una carpeta falsa."""
    out = []
    for dev in sorted(glob.glob(os.path.join(drm_root, "card[0-9]*", "device"))):
        card = dev.split(os.sep)[-2]
        if "-" in card:
            continue
        try:
            busy = int(_read(os.path.join(dev, "gpu_busy_percent")))
        except (OSError, ValueError):
            continue  # sin gpu_busy_percent no es una placa que podamos medir (o no es AMD)
        used = total = temp = power = None
        try:
            used, total = int(_read(os.path.join(dev, "mem_info_vram_used"))), int(_read(os.path.join(dev, "mem_info_vram_total")))
        except (OSError, ValueError):
            pass
        try:
            hw = sorted(glob.glob(os.path.join(dev, "hwmon", "hwmon*")))[0]
            temp = int(_read(os.path.join(hw, "temp1_input"))) / 1000
            for name in ("power1_average", "power1_input"):
                if os.path.exists(os.path.join(hw, name)):
                    power = int(_read(os.path.join(hw, name))) / 1e6
                    break
        except (OSError, ValueError, IndexError):
            pass
        try:
            name = _read(os.path.join(dev, "product_name")) or f"Placa AMD ({card})"
        except OSError:
            name = f"Placa AMD ({card})"
        out.append({"index": len(out), "name": name, "vendor": "amd", "utilPercent": float(busy), "memUsedBytes": used,
                    "memTotalBytes": total, "tempC": temp, "powerW": power, "unverified": True})
    return out


# ------------------------------------------------------------------------------------------------------ plataformas

class LinuxPlatform:
    """Lee /proc. `root` es inyectable para las pruebas (una carpeta con archivos /proc falsos)."""
    name = "linux"

    def __init__(self, root="/proc", clk_tck=None):
        self.root = root
        try:
            self.clk = clk_tck or os.sysconf("SC_CLK_TCK")
        except (AttributeError, ValueError, OSError):
            self.clk = 100

    def _p(self, *parts):
        return os.path.join(self.root, *parts)

    def cpu_times(self):
        """(ocupado, total) acumulados, en ticks. Los porcentajes salen de las diferencias entre dos lecturas."""
        with open(self._p("stat")) as f:
            parts = f.readline().split()
        v = [int(x) for x in parts[1:9]]  # user nice system idle iowait irq softirq steal (guest ya está en user)
        total = sum(v)
        idle = v[3] + v[4]
        return total - idle, total

    def cores(self):
        n = 0
        with open(self._p("stat")) as f:
            for line in f:
                if line.startswith("cpu") and line[3:4].isdigit():
                    n += 1
        return n or os.cpu_count()

    def memory(self):
        info = {}
        with open(self._p("meminfo")) as f:
            for line in f:
                k, _, rest = line.partition(":")
                info[k] = int(rest.split()[0]) * 1024
        total = info["MemTotal"]
        avail = info.get("MemAvailable", info.get("MemFree", 0))
        return {"totalBytes": total, "availableBytes": avail, "usedBytes": total - avail}

    def _stat(self, pid):
        with open(self._p(str(pid), "stat")) as f:
            raw = f.read()
        rest = raw[raw.rindex(")") + 2:].split()  # tras "pid (comm) "; el nombre puede tener espacios y paréntesis
        # rest[0]=estado, rest[1]=ppid, rest[11]=utime, rest[12]=stime, rest[19]=starttime
        return {"ppid": int(rest[1]), "ticks": int(rest[11]) + int(rest[12]), "start": int(rest[19])}

    def _status(self, pid):
        name, rss = "", None
        with open(self._p(str(pid), "status")) as f:
            for line in f:
                if line.startswith("Name:"):
                    name = line.split(None, 1)[1].strip()
                elif line.startswith("VmRSS:"):
                    rss = int(line.split()[1]) * 1024
        return name, rss

    def _cmdline(self, pid):
        try:
            with open(self._p(str(pid), "cmdline"), "rb") as f:
                return f.read().replace(b"\0", b" ").decode("utf-8", "replace").strip()
        except OSError:
            return ""

    def processes(self):
        """Todos los procesos: {pid: {ppid, ticks, start, name, rss, cmd}}. Los que desaparecen a mitad se saltean."""
        out = {}
        try:
            names = os.listdir(self.root)
        except OSError:
            return out
        for n in names:
            if not n.isdigit():
                continue
            try:
                st = self._stat(n)
            except (OSError, ValueError, IndexError):
                continue
            out[int(n)] = st
        return out

    def describe(self, pid):
        """Nombre, memoria residente y línea de comandos de un proceso (se pide solo para los que importan)."""
        try:
            name, rss = self._status(pid)
        except (OSError, ValueError):
            name, rss = "", None
        return {"name": name, "rss": rss, "cmd": self._cmdline(pid)}


class _FileTime(ctypes.Structure):
    _fields_ = [("dwLowDateTime", ctypes.c_uint32), ("dwHighDateTime", ctypes.c_uint32)]


class _MemStatus(ctypes.Structure):
    _fields_ = [("dwLength", ctypes.c_uint32), ("dwMemoryLoad", ctypes.c_uint32), ("ullTotalPhys", ctypes.c_uint64),
                ("ullAvailPhys", ctypes.c_uint64), ("ullTotalPageFile", ctypes.c_uint64), ("ullAvailPageFile", ctypes.c_uint64),
                ("ullTotalVirtual", ctypes.c_uint64), ("ullAvailVirtual", ctypes.c_uint64), ("ullAvailExtendedVirtual", ctypes.c_uint64)]


class WindowsPlatform:
    """SIN VERIFICAR EN WINDOWS: escrito contra la documentación de la API y probado solo con un kernel32 simulado.
    Procesos de la app: todavía no (queda para cuando se pueda probar en Windows); cpu y ram sí."""
    name = "windows"

    def __init__(self, kernel32=None):
        if kernel32 is None:
            windll = getattr(ctypes, "windll", None)  # no existe fuera de Windows: nunca se toca al importar
            kernel32 = getattr(windll, "kernel32", None)
        self.k32 = kernel32

    @staticmethod
    def _ft(ft):
        return (ft.dwHighDateTime << 32) | ft.dwLowDateTime

    def cpu_times(self):
        idle, kernel, user = _FileTime(), _FileTime(), _FileTime()
        if not self.k32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)):
            raise OSError("GetSystemTimes falló")
        i, k, u = self._ft(idle), self._ft(kernel), self._ft(user)
        total = k + u  # el tiempo de kernel incluye el ocioso
        return total - i, total

    def cores(self):
        return os.cpu_count()

    def memory(self):
        ms = _MemStatus()
        ms.dwLength = ctypes.sizeof(_MemStatus)
        if not self.k32.GlobalMemoryStatusEx(ctypes.byref(ms)):
            raise OSError("GlobalMemoryStatusEx falló")
        return {"totalBytes": ms.ullTotalPhys, "availableBytes": ms.ullAvailPhys, "usedBytes": ms.ullTotalPhys - ms.ullAvailPhys}

    def processes(self):
        return {}

    def describe(self, pid):
        return {"name": "", "rss": None, "cmd": ""}


class NullPlatform:
    """Plataforma sin soporte: todo null."""
    name = "otra"

    def cpu_times(self):
        raise OSError("sin soporte")

    cores = memory = cpu_times

    def processes(self):
        return {}

    def describe(self, pid):
        return {"name": "", "rss": None, "cmd": ""}


def detect_platform():
    if sys.platform.startswith("linux"):
        return LinuxPlatform()
    if sys.platform == "win32":
        return WindowsPlatform()
    return NullPlatform()


# ----------------------------------------------------------------------------------------------------- muestreador

def role_of(cmd, name, pid, own_pid):
    """Qué es un proceso, por su línea de comandos."""
    c = (cmd or name or "").lower()
    if pid == own_pid:
        return "Motor"
    if "audio-separator" in c or "audio_separator" in c:
        return "Separación"
    if "analyze" in c:
        return "Análisis"
    if "ollama" in c:
        return "Ollama"
    if "ffmpeg" in c:
        return "ffmpeg"
    return name or "Proceso"


class Sampler:
    def __init__(self, platform=None, paths_fn=None, jobs_fn=None, smi_path="auto", drm_root="/sys/class/drm",
                 interval=INTERVAL, idle_sec=IDLE_SEC, history_sec=HISTORY_SEC, clock=time.time, own_pid=None,
                 apps_fn=None, smi_cmd=None):
        self.platform = platform or detect_platform()
        self.paths_fn, self.jobs_fn = paths_fn or (lambda: {}), jobs_fn or (lambda: [])
        self.smi = find_smi() if smi_path == "auto" else smi_path
        self.drm_root, self.interval, self.idle_sec, self.clock = drm_root, interval, idle_sec, clock
        self.own_pid = own_pid or os.getpid()
        self.apps_fn = apps_fn  # inyectable: () -> {pid: bytes}; por defecto una consulta a nvidia-smi
        self.stream = SmiStream(smi_cmd or ([self.smi, f"--query-gpu={SMI_FIELDS}", "--format=csv,noheader,nounits", "-lms", str(int(interval * 1000))] if self.smi else None), clock=clock)
        self.hist = deque(maxlen=max(2, int(history_sec / interval)))
        self.lock = threading.RLock()
        self._thread = None
        self._stop = threading.Event()
        self._last_req = 0.0
        self._ticks = 0
        self._cpu_prev = None
        self._proc_prev = {}     # (pid, starttime) -> (ticks, instante)
        self._last = {"cpu": None, "ram": None, "gpus": [], "disks": [], "processes": [], "gpuApps": [], "errors": []}
        self._apps = {}
        self._errors = set()

    # -- suscripciones
    def touch(self):
        """Un pedido = un interesado. Arranca el hilo si no estaba y renueva el plazo de apagado."""
        with self.lock:
            self._last_req = self.clock()
            if self._thread is None or not self._thread.is_alive():
                self._stop.clear()
                self._prime()
                self._thread = threading.Thread(target=self._run, name="resources", daemon=True)
                self._thread.start()

    def running(self):
        return self._thread is not None and self._thread.is_alive()

    def stop(self):
        self._stop.set()
        t = self._thread
        if t is not None and t is not threading.current_thread():
            t.join(5)
        self._shutdown_sources()

    def _shutdown_sources(self):
        self.stream.close()
        self._cpu_prev, self._proc_prev = None, {}
        with self.lock:  # al volver a arrancar no se muestran valores viejos como si fueran de ahora
            self._last = {"cpu": None, "ram": None, "gpus": [], "disks": [], "processes": [], "errors": []}

    def _prime(self):
        self._ticks = 0
        try:
            self._cpu_prev = self.platform.cpu_times()
        except Exception:
            self._cpu_prev = None

    def _run(self):
        next_t = self.clock()
        while not self._stop.is_set():
            with self.lock:
                if self.clock() - self._last_req > self.idle_sec:
                    break
            self.tick()
            next_t += self.interval
            self._stop.wait(max(0.0, min(self.interval, next_t - self.clock())))
            if next_t < self.clock() - 5:
                next_t = self.clock()
        with self.lock:  # cierra todo y se da de baja bajo el candado: un pedido que llegue ahora arranca un hilo nuevo
            self._shutdown_sources()
            if self._thread is threading.current_thread():
                self._thread = None

    # -- una muestra
    def _guard(self, name, fn, default=None):
        try:
            value = fn()
            self._errors.discard(name)
            return value
        except Exception:
            self._errors.add(name)
            return default

    def tick(self):
        now = self.clock()
        self._ticks += 1
        cpu = self._guard("cpu", self._cpu)
        ram = self._guard("ram", self._ram)
        gpus = self._guard("gpu", self._gpus, [])
        last = self._last
        if self._ticks == 1 or self._ticks % PROC_EVERY == 0:
            self._guard("processes", lambda: self._procs(now, gpus))
        if self._ticks == 1 or self._ticks % DISK_EVERY == 0:
            last["disks"] = self._guard("disks", self._disks, last["disks"])
        g0 = gpus[0] if gpus else None
        with self.lock:
            last.update(cpu=cpu, ram=ram, gpus=gpus, errors=sorted(self._errors))
            self.hist.append((int(now * 1000), None if cpu is None else cpu["percent"], None if ram is None else ram["percent"],
                              None if g0 is None else g0["utilPercent"], None if g0 is None else g0["memUsedBytes"]))

    def _cpu(self):
        cur = self.platform.cpu_times()
        prev, self._cpu_prev = self._cpu_prev, cur
        cores = self._guard("cores", self.platform.cores)
        if prev is None or cur[1] <= prev[1]:
            return {"percent": None, "cores": cores}
        return {"percent": round(max(0.0, min(100.0, 100.0 * (cur[0] - prev[0]) / (cur[1] - prev[1]))), 1), "cores": cores}

    def _ram(self):
        m = self.platform.memory()
        m["percent"] = round(100.0 * m["usedBytes"] / m["totalBytes"], 1) if m["totalBytes"] else None
        return m

    def _gpus(self):
        if self.smi or self.stream.cmd:
            if not self.stream.alive() and self.clock() - self.stream.last_start >= (SMI_RETRY if self.stream.last_start else 0):
                self.stream.close()
                self.stream.start()
            gpus = self.stream.latest()
            if gpus:
                return gpus
        if sys.platform.startswith("linux"):
            return amd_gpus(self.drm_root)
        return []

    def _procs(self, now, gpus):
        if gpus and any(g["vendor"] == "nvidia" for g in gpus):
            self._apps = (self.apps_fn() if self.apps_fn else compute_apps_once(self.smi)) if (self.apps_fn or self.smi) else {}
        else:
            self._apps = {}
        table = self.platform.processes()
        children = {}
        for pid, st in table.items():
            children.setdefault(st["ppid"], []).append(pid)
        mine, stack = {self.own_pid}, [self.own_pid]
        while stack:
            for c in children.get(stack.pop(), []):
                if c not in mine:
                    mine.add(c)
                    stack.append(c)
        rows, seen = [], {}
        for pid in sorted(mine | set(self._apps)):
            st = table.get(pid)
            if st is None:
                continue  # un pid de la placa que no vemos acá (otro espacio de procesos, p. ej. Docker): no se puede describir
            d = self.platform.describe(pid)
            if "nvidia-smi" in (d["name"] or "").lower():
                continue  # nuestras propias consultas no cuentan
            key = (pid, st["start"])  # con el inicio del proceso, un pid reutilizado no da basura
            prev = self._proc_prev.get(key)
            cpu = None
            if prev and now > prev[1]:
                cpu = round(max(0.0, (st["ticks"] - prev[0]) / self.platform.clk / (now - prev[1]) * 100), 1)  # 100 % = un núcleo
            seen[key] = (st["ticks"], now)
            inside = pid in mine
            gpu_mem = self._apps.get(pid)
            rows.append({"pid": pid, "role": role_of(d["cmd"], d["name"], pid, self.own_pid), "name": d["name"], "inApp": inside,
                         "cpuPercent": cpu, "rssBytes": d["rss"], "gpuMemBytes": gpu_mem if pid in self._apps else None})
        self._proc_prev = seen
        # Los hijos del motor van siempre; los ajenos solo si usan la placa (p. ej. un Ollama de systemd o una separación a mano).
        with self.lock:
            self._last["processes"] = rows

    def _disks(self):
        out, devs = [], {}
        for key, p in (self.paths_fn() or {}).items():
            path = Path(p)
            while not path.exists() and path != path.parent:
                path = path.parent
            dev = os.stat(path).st_dev
            if dev in devs:
                devs[dev]["keys"].append(key)
                continue
            u = shutil.disk_usage(path)
            devs[dev] = {"path": str(path), "keys": [key], "totalBytes": u.total, "freeBytes": u.free,
                         "usedPercent": round(100.0 * (u.total - u.free) / u.total, 1) if u.total else None}
            out.append(devs[dev])
        return out

    # -- lectura
    def snapshot(self, since=None, subscribe=True):
        """Lo que devuelve GET /engine/resources. No lanza nunca. Pedirlo cuenta como una suscripción (subscribe=False: solo leer)."""
        if subscribe:
            self.touch()
        try:
            jobs = self.jobs_fn()
        except Exception:
            jobs = []
        with self.lock:
            rows = [r for r in self.hist if since is None or r[0] > since]
            last = dict(self._last)
            hist = {"t": [r[0] for r in rows], "cpu": [r[1] for r in rows], "ram": [r[2] for r in rows],
                    "gpuUtil": [r[3] for r in rows], "gpuMem": [r[4] for r in rows]}
        return {"now": int(self.clock() * 1000), "intervalMs": int(self.interval * 1000), "platform": self.platform.name,
                "cpu": last["cpu"], "ram": last["ram"], "gpus": last["gpus"], "disks": last["disks"],
                "processes": last["processes"], "jobs": jobs, "errors": last["errors"], "history": hist}


SAMPLER = Sampler()


def configure(paths_fn=None, jobs_fn=None):
    """El motor le pasa de dónde sacar las carpetas y los trabajos (así este módulo no depende del resto)."""
    SAMPLER.paths_fn = paths_fn or SAMPLER.paths_fn
    SAMPLER.jobs_fn = jobs_fn or SAMPLER.jobs_fn
