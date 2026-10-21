"""Ajustes del usuario: dónde viven los datos, los modelos y la música. Se guardan en ~/.config/stemshed/settings.json."""
import json
import os
import osenv
import urllib.parse
from pathlib import Path

CONFIG_DIR = osenv.config_dir()
FILE = CONFIG_DIR / "settings.json"
FORBIDDEN = osenv.FORBIDDEN
DEFAULTS = {
    "dataDir": os.environ.get("STEMSHED_DATA", osenv.default_root("stemshed")),
    "ollamaModelsDir": "",            # vacío = <dataDir>/models/ollama
    "separationModelsDir": os.environ.get("STEMSHED_SEP_MODELS", ""),   # vacío = <separationEnvDir>/models
    "separationEnvDir": os.environ.get("STEMS_ENV", osenv.default_root("tidal-stems")),
    "musicFolders": [os.environ["STEMSHED_DEFAULT_MUSIC"]] if os.environ.get("STEMSHED_DEFAULT_MUSIC") else [],
    "llmUrl": os.environ.get("STEMSHED_OLLAMA", "http://127.0.0.1:11500"),
    "audioSources": ["local", "tidal"],   # orden de preferencia para escuchar y separar
    "llmModel": "",                   # vacío = el primero instalado
    "recsAuto": True,                 # el motor genera solo el "Disco de hoy" cuando toca
    "recsCadenceHours": 24,           # 24 = uno por día (cambia con la fecha); otro valor = cada N horas
    "setup": {"done": False, "skipped": []},   # asistente de primer inicio: si ya se cerró y qué pasos se saltaron
    "recsHalfLifeDays": 180,          # vida media de los gustos en la memoria
}
CADENCES = (6, 12, 24, 48, 72, 168)


class SettingsError(Exception):
    pass


def load():
    data = dict(DEFAULTS)
    try:
        data.update(json.loads(FILE.read_text()))
    except (OSError, ValueError):
        pass
    return data


def effective(data=None):
    data = data or load()
    out = dict(data)
    out["ollamaModelsDir"] = data["ollamaModelsDir"] or str(Path(data["dataDir"]) / "models" / "ollama")
    out["separationModelsDir"] = data["separationModelsDir"] or str(Path(data["separationEnvDir"]) / "models")
    return out


def _abs_dir(value, label):
    if not isinstance(value, str) or not value.strip():
        raise SettingsError(f"{label}: falta la ruta.")
    p = Path(os.path.normpath(value.strip()))
    if not osenv.is_absolute(str(p)):
        raise SettingsError(f"{label}: la ruta tiene que ser absoluta ({'por ejemplo D:\\Musica' if osenv.WINDOWS else 'empezar con /'}).")
    if osenv.is_forbidden(p, FORBIDDEN):
        raise SettingsError(f"{label}: no se pueden usar carpetas del sistema ({p}).")
    return p


def _writable_dir(value, label):
    p = _abs_dir(value, label)
    try:
        p.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise SettingsError(f"{label}: no se pudo crear la carpeta ({e.strerror}).")
    if not os.access(p, os.W_OK):
        raise SettingsError(f"{label}: no hay permiso de escritura en {p}.")
    return str(p)


def validate(patch):
    """Valida cada campo recibido y devuelve solo los ya normalizados. Lanza SettingsError con un mensaje para el usuario."""
    out = {}
    if "dataDir" in patch:
        out["dataDir"] = _writable_dir(patch["dataDir"], "Carpeta de datos")
    if "ollamaModelsDir" in patch:
        out["ollamaModelsDir"] = _writable_dir(patch["ollamaModelsDir"], "Carpeta de modelos de recomendación") if patch["ollamaModelsDir"] else ""
    if "separationModelsDir" in patch:
        out["separationModelsDir"] = _writable_dir(patch["separationModelsDir"], "Carpeta de modelos de separación") if patch["separationModelsDir"] else ""
    if "separationEnvDir" in patch:
        p = _abs_dir(patch["separationEnvDir"], "Entorno de separación")
        if not osenv.env_bin(p, "audio-separator").exists():
            raise SettingsError(f"Entorno de separación: no encontré {osenv.env_rel('audio-separator')} en {p}.")
        out["separationEnvDir"] = str(p)
    if "musicFolders" in patch:
        if not isinstance(patch["musicFolders"], list) or len(patch["musicFolders"]) > 20:
            raise SettingsError("Carpetas de música: lista inválida.")
        folders = []
        for f in patch["musicFolders"]:
            p = _abs_dir(f, "Carpeta de música")
            if not p.is_dir():
                raise SettingsError(f"Carpeta de música: {p} no existe.")
            if not os.access(p, os.R_OK):
                raise SettingsError(f"Carpeta de música: no hay permiso de lectura en {p}.")
            if str(p) not in folders:
                folders.append(str(p))
        out["musicFolders"] = folders
    if "audioSources" in patch:
        a = patch["audioSources"]
        if not isinstance(a, list) or len(set(a)) != len(a) or any(x not in ("local", "tidal") for x in a):
            raise SettingsError("Fuentes de audio: lista inválida.")
        out["audioSources"] = a
    if "llmModel" in patch:
        m = str(patch["llmModel"]).strip()
        if len(m) > 100 or any(c in m for c in " \n\t/\\"):
            raise SettingsError("Modelo de recomendaciones: nombre inválido.")
        out["llmModel"] = m
    if "recsAuto" in patch:
        if not isinstance(patch["recsAuto"], bool):
            raise SettingsError("Disco de hoy automático: valor inválido.")
        out["recsAuto"] = patch["recsAuto"]
    if "recsCadenceHours" in patch:
        if patch["recsCadenceHours"] not in CADENCES:
            raise SettingsError("Cada cuánto: opción inválida.")
        out["recsCadenceHours"] = int(patch["recsCadenceHours"])
    if "recsHalfLifeDays" in patch:
        v = patch["recsHalfLifeDays"]
        if not isinstance(v, (int, float)) or isinstance(v, bool) or not 14 <= v <= 1825:
            raise SettingsError("Vida media de los gustos: entre 14 y 1825 días.")
        out["recsHalfLifeDays"] = int(v)
    if "setup" in patch:
        v = patch["setup"]
        if not isinstance(v, dict) or not isinstance(v.get("done", False), bool) or not isinstance(v.get("skipped", []), list):
            raise SettingsError("Configuración inicial: valor inválido.")
        steps = ("equipo", "carpetas", "separacion", "musica", "modelo", "perfil")
        if any(x not in steps for x in v.get("skipped", [])):
            raise SettingsError("Configuración inicial: paso desconocido.")
        out["setup"] = {"done": v.get("done", False), "skipped": sorted(set(v.get("skipped", [])))}
    if "llmUrl" in patch:
        u = urllib.parse.urlparse(str(patch["llmUrl"]).strip())
        if u.scheme not in ("http", "https") or u.hostname not in ("127.0.0.1", "localhost", "::1"):
            raise SettingsError("Servidor de modelos: tiene que ser una dirección de esta computadora (http://127.0.0.1:puerto).")
        out["llmUrl"] = f"{u.scheme}://{u.netloc}"
    return out


def save(patch):
    clean = validate(patch)
    data = load()
    data.update(clean)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    osenv.secure(CONFIG_DIR, 0o700)
    FILE.write_text(json.dumps(data, indent=1))
    osenv.secure(FILE, 0o600)
    return data


def _drives():
    """Windows: las unidades como raíces del selector de carpetas."""
    import shutil
    dirs = []
    for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        root = letter + ":\\"
        if os.path.exists(root):
            dirs.append(root)
    free = shutil.disk_usage(dirs[0]).free if dirs else 0
    return {"path": "", "parent": None, "dirs": dirs, "freeGB": round(free / 1e9, 1), "drives": True}


def list_dirs(path):
    """Subcarpetas de `path` para el selector de carpetas (solo directorios, sin ocultas)."""
    if osenv.WINDOWS and path in (None, "", "/"):
        return _drives()
    p = Path(os.path.normpath(path or "/"))
    if not osenv.is_absolute(str(p)) or (not osenv.WINDOWS and str(p).startswith(("/proc", "/sys", "/dev"))):
        raise SettingsError("Ruta no válida.")
    if not p.is_dir():
        raise SettingsError(f"{p} no es una carpeta.")
    try:
        names = sorted((e.name for e in os.scandir(p) if e.is_dir(follow_symlinks=False) and not e.name.startswith(".")), key=str.lower)
    except PermissionError:
        raise SettingsError(f"No hay permiso para leer {p}.")
    import shutil
    free = shutil.disk_usage(p).free
    return {"path": str(p), "parent": str(p.parent) if p != p.parent else None, "dirs": names[:500], "freeGB": round(free / 1e9, 1)}
