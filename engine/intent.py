"""Lo que el usuario pide en texto libre, convertido en restricciones que se pueden VERIFICAR con datos: país de origen del artista y si busca lo fundamental.

"Discos de Argentina que tengo que haber escuchado" no es un género: es (1) un país de origen, que MusicBrainz sabe de cada artista (`country` ISO y `area`), y (2) la intención
de "clásicos / imprescindibles". Antes solo viajaba como texto en el prompt y nadie verificaba nada (salió Toto). Funciones puras, sin red.
"""
import re
import unicodedata

# ISO 3166-1 -> (nombre en español, formas con las que se lo nombra: país y gentilicios), todo sin tildes y en minúsculas.
COUNTRIES = {
    "AR": ("Argentina", ("argentina", "argentino", "argentina", "argentinos", "argentinas", "rioplatense", "rioplatenses")),
    "UY": ("Uruguay", ("uruguay", "uruguayo", "uruguaya", "uruguayos", "uruguayas")),
    "CL": ("Chile", ("chile", "chileno", "chilena", "chilenos", "chilenas")),
    "BR": ("Brasil", ("brasil", "brasileno", "brasilena", "brasilero", "brasilera", "brasilenos", "brasileros")),
    "MX": ("México", ("mexico", "mexicano", "mexicana", "mexicanos", "mexicanas")),
    "CO": ("Colombia", ("colombia", "colombiano", "colombiana", "colombianos", "colombianas")),
    "PE": ("Perú", ("peru", "peruano", "peruana", "peruanos", "peruanas")),
    "VE": ("Venezuela", ("venezuela", "venezolano", "venezolana", "venezolanos")),
    "BO": ("Bolivia", ("bolivia", "boliviano", "boliviana", "bolivianos")),
    "PY": ("Paraguay", ("paraguay", "paraguayo", "paraguaya", "paraguayos")),
    "EC": ("Ecuador", ("ecuador", "ecuatoriano", "ecuatoriana", "ecuatorianos")),
    "CU": ("Cuba", ("cuba", "cubano", "cubana", "cubanos", "cubanas")),
    "ES": ("España", ("espana", "espanol", "espanola", "espanoles", "espanolas")),
    "PT": ("Portugal", ("portugal", "portugues", "portuguesa", "portugueses")),
    "US": ("Estados Unidos", ("estados unidos", "eeuu", "ee uu", "estadounidense", "estadounidenses", "norteamericano", "norteamericana")),
    "GB": ("Reino Unido", ("reino unido", "inglaterra", "britanico", "britanica", "britanicos", "uk")),
    "IE": ("Irlanda", ("irlanda", "irlandes", "irlandesa", "irlandeses")),
    "FR": ("Francia", ("francia", "frances", "francesa", "franceses")),
    "DE": ("Alemania", ("alemania", "aleman", "alemana", "alemanes")),
    "IT": ("Italia", ("italia", "italiano", "italiana", "italianos")),
    "SE": ("Suecia", ("suecia", "sueco", "sueca", "suecos")),
    "JP": ("Japón", ("japon", "japones", "japonesa", "japoneses")),
    "JM": ("Jamaica", ("jamaica", "jamaiquino", "jamaiquina", "jamaiquinos")),
    "NG": ("Nigeria", ("nigeria", "nigeriano", "nigeriana", "nigerianos")),
    "ZA": ("Sudáfrica", ("sudafrica", "sudafricano", "sudafricana", "sudafricanos")),
    "CA": ("Canadá", ("canada", "canadiense", "canadienses")),
    "AU": ("Australia", ("australia", "australiano", "australiana", "australianos")),
    "CU2": ("", ()),
}
COUNTRIES.pop("CU2")

# Gentilicios que también son un idioma: "música en francés" habla del idioma, no del origen del artista.
LANGUAGE = {"ES", "PT", "FR", "DE", "IT", "JP"}

# "tengo que haber escuchado", "imprescindibles"...: busca lo fundamental, no lo reciente ni lo oscuro.
CANON_PHRASES = ("tengo que haber escuchado", "tendria que haber escuchado", "deberia haber escuchado", "debo haber escuchado", "tengo que conocer", "tendria que conocer",
                 "imprescindible", "imprescindibles", "esencial", "esenciales", "fundamental", "fundamentales", "clasico", "clasicos", "historico", "historicos",
                 "no me pueden faltar", "no pueden faltar", "los mejores", "lo mejor de", "canon", "obligatorio", "obligatorios", "referentes", "referente")


def _norm(text):
    t = unicodedata.normalize("NFD", str(text).lower())
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", "".join(c for c in t if not unicodedata.combining(c)))).strip()


def countries(text):
    """Códigos ISO de los países nombrados en el pedido ("discos de Argentina", "rock uruguayo"), en orden de aparición y sin repetir."""
    t = " " + _norm(text) + " "
    found = []
    for code, (name, forms) in COUNTRIES.items():
        for f in forms:
            m = re.search(r"(?<![a-z0-9])" + re.escape(f) + r"(?![a-z0-9])", t)
            if m and code in LANGUAGE and f != _norm(name) and t[:m.start()].rstrip().endswith(" en"):
                continue  # "en francés": idioma
            if m:
                found.append((m.start(), code))
                break
    return [c for _, c in sorted(found)]


def canon(text):
    """¿Pide lo fundamental / imprescindible / clásico?"""
    t = " " + _norm(text) + " "
    return any(" " + p + " " in t for p in CANON_PHRASES)


def country_name(code):
    return COUNTRIES.get(code, (code,))[0]


def judge_origin(wanted, artist):
    """Veredicto de origen con los datos de MusicBrainz del artista ({country: ISO, area: nombre, beginArea: nombre}).
    match: su país o su área de origen es el pedido. off: tiene origen y es otro. unknown: MusicBrainz no lo sabe. Devuelve {status, why}."""
    if not wanted:
        return {"status": "match", "why": ""}
    want_names = {_norm(country_name(c)) for c in wanted}
    country = (artist.get("country") or "").upper()
    areas = [_norm(a) for a in (artist.get("area"), artist.get("beginArea")) if a]
    names = ", ".join(country_name(c) for c in wanted)
    if country in wanted or any(a in want_names for a in areas):
        return {"status": "match", "why": f"Es de {names} según MusicBrainz."}
    if country or areas:
        have = country_name(country) if country in COUNTRIES else (artist.get("area") or country)
        return {"status": "off", "why": f"No es de {names}: MusicBrainz lo ubica en {have}."}
    return {"status": "unknown", "why": f"MusicBrainz no dice de dónde es el artista: no se puede comprobar que sea de {names}."}
