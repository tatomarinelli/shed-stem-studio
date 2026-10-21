"""Open-Meteo (gratis, sin clave). Solo se llama si el usuario activó el clima y escribió su ciudad.
Lo único que sale es el nombre de la ciudad (geocoding) o sus coordenadas (clima): nunca gustos ni música."""
import json
import threading
import time
import urllib.parse
import urllib.request

UA = "ShedStemStudio/0.0.1 (prototipo local)"
TTL = 30 * 60
_cache = {}
_lock = threading.Lock()


class WeatherError(ValueError):
    pass


def _get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=10) as r:
        return json.load(r)


def geocode(city):
    q = urllib.parse.urlencode({"name": city, "count": 1, "language": "es", "format": "json"})
    try:
        res = _get(f"https://geocoding-api.open-meteo.com/v1/search?{q}").get("results")
    except Exception:
        raise WeatherError("No pude buscar esa ciudad (¿sin conexión?).")
    if not res:
        raise WeatherError(f"No encontré la ciudad «{city}».")
    r = res[0]
    return {"name": r.get("name", city), "country": r.get("country", ""), "latitude": round(r["latitude"], 3),
            "longitude": round(r["longitude"], 3), "timezone": r.get("timezone", "")}


def current(lat, lon, now=None):
    """{temp, code} o None si no hay conexión. Caché de 30 minutos por coordenadas."""
    now = now or time.time()
    key = (round(lat, 2), round(lon, 2))
    with _lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < TTL:
            return hit[1]
    q = urllib.parse.urlencode({"latitude": lat, "longitude": lon, "current": "temperature_2m,weather_code"})
    try:
        c = _get(f"https://api.open-meteo.com/v1/forecast?{q}")["current"]
        value = {"temp": float(c["temperature_2m"]), "code": int(c["weather_code"])}
    except Exception:
        return None
    with _lock:
        _cache[key] = (now, value)
    return value
