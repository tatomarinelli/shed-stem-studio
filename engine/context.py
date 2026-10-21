"""El momento de la recomendación: se calcula en código (nunca lo adivina el modelo). Opt-in desde el perfil."""
from datetime import datetime

import osenv

WEEKDAYS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
WMO = [({0}, "despejado"), ({1}, "mayormente despejado"), ({2}, "parcialmente nublado"), ({3}, "nublado"),
       ({45, 48}, "con niebla"), ({51, 53, 55, 56, 57}, "con llovizna"), ({61, 63, 65, 66, 67}, "con lluvia"),
       ({71, 73, 75, 77, 85, 86}, "con nieve"), ({80, 81, 82}, "con chubascos"), ({95, 96, 99}, "con tormenta")]


def daypart(hour):
    if 5 <= hour < 12:
        return "mañana"
    if 12 <= hour < 15:
        return "mediodía"
    if 15 <= hour < 20:
        return "tarde"
    if 20 <= hour < 24:
        return "noche"
    return "madrugada"


def season(date, south=True):
    md = (date.month, date.day)
    if md >= (12, 21) or md < (3, 21):
        s = "verano"
    elif md < (6, 21):
        s = "otoño"
    elif md < (9, 23):
        s = "invierno"
    else:
        s = "primavera"
    flip = {"verano": "invierno", "invierno": "verano", "otoño": "primavera", "primavera": "otoño"}
    return s if south else flip[s]


def weather_label(code):
    for codes, label in WMO:
        if code in codes:
            return label
    return ""


def build(profile, now_ts, weather=None):
    """Devuelve None si el usuario no activó nada. `weather` = {temp, code} ya obtenido por el motor."""
    if not profile.get("useTime") and not (profile.get("useWeather") and profile.get("geo")):
        return None
    geo = profile.get("geo") or {}
    tz = osenv.tzinfo(geo.get("timezone"))
    now = datetime.fromtimestamp(now_ts, tz) if tz else datetime.fromtimestamp(now_ts).astimezone()
    ctx = {}
    if profile.get("useTime"):
        ctx.update(weekday=WEEKDAYS[now.weekday()], daypart=daypart(now.hour), weekend=now.weekday() >= 5)
    if profile.get("useWeather") and geo:
        ctx.update(city=geo.get("name", ""), season=season(now.date(), south=geo.get("latitude", -1) < 0))
        if weather:
            ctx.update(temp=round(weather["temp"]), sky=weather_label(weather["code"]))
    return ctx


def describe(ctx):
    if not ctx:
        return ""
    parts = []
    if "weekday" in ctx:
        parts.append(f"{ctx['weekday']} a la {ctx['daypart']}")
    if "city" in ctx:
        parts.append(f"{ctx['city']}, {ctx['season']}")
    if "temp" in ctx:
        parts.append(f"{ctx['temp']} °C" + (f", {ctx['sky']}" if ctx.get("sky") else ""))
    return " · ".join(parts)
