"""Contexto del álbum ANCLADO en una fuente verificable (los modelos locales inventan datos musicales con seguridad).

1. Busca el artículo del disco en Wikipedia (es, después en) y confirma que la página ES del disco: título igual (sin
   aclaración entre paréntesis), no es desambiguación, y el extracto nombra al artista y dice que es un álbum/disco.
2. El modelo local RESUME ese extracto en 2-3 frases con la consigna de usar solo hechos del texto.
3. Se valida el resumen: cada número y cada nombre propio tiene que estar en el extracto. Si falla, se muestran las
   primeras oraciones del extracto tal cual. Nunca se muestra un resumen dudoso.
4. Sin artículo confiable: una línea con datos de MusicBrainz (año, sello, país, géneros), sin prosa.
Caché por mbid en <dataDir>/recs/albumctx.json (el contexto de un disco no cambia). Wikipedia: 1 consulta/s.
"""
import json
import re
import threading
import time
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

UA = "ShedStemStudio/0.0.1 (prototipo local)"
_lock = threading.Lock()
_last = [0.0]
_cache = {}
ALBUM_WORDS = {"es": ("álbum", "album", "disco", "lp", "ep"), "en": ("album", "lp", "ep", "record")}
STOP_CAPS = {"el", "la", "los", "las", "un", "una", "es", "fue", "en", "con", "de", "del", "y", "este", "esta", "se", "su", "sus",
             "the", "it", "its", "a", "an", "in", "on", "and", "this", "is", "was", "por", "para", "al", "lo", "como", "también",
             "además", "allí", "ahí", "luego", "después", "durante", "tras", "según", "incluye", "contiene", "presenta", "cuenta"}


def norm(t):
    t = unicodedata.normalize("NFD", str(t).lower())
    return re.sub(r"[^a-z0-9]+", " ", "".join(c for c in t if not unicodedata.combining(c))).strip()


def title_key(t):
    t = re.sub(r"\s*\([^)]*\)\s*$", "", str(t))  # "Idle Moments (álbum)" -> "Idle Moments"
    return re.sub(r"^(the|a|an|el|la|los|las) ", "", norm(t))


def _get(url):
    with _lock:
        wait = _last[0] + 2.0 - time.time()  # Wikimedia limita a clientes anónimos: 1 consulta cada 2 s
        if wait > 0:
            time.sleep(wait)
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=15) as r:
                return json.load(r)
        finally:
            _last[0] = time.time()


def _api(lang, **params):
    params.update(format="json", formatversion="2")
    return _get(f"https://{lang}.wikipedia.org/w/api.php?{urllib.parse.urlencode(params)}")


def is_album_page(page, artist, album, lang):
    """Reglas puras para aceptar una página como la del disco."""
    if not page or page.get("missing") or (page.get("pageprops") or {}).get("disambiguation") is not None:
        return False
    ext = page.get("extract") or ""
    if title_key(page.get("title", "")) != title_key(album) or len(ext) < 60:
        return False
    first = norm(ext[:600])
    main_artist = norm(re.split(r"\s+(?:&|and|y|with|feat\.?)\s+", artist)[0])
    return main_artist in first and any(w in first.split() for w in ALBUM_WORDS[lang])


def find_article(artist, album, errors=None):
    """{lang, title, extract, url} o None. Anota en `errors` si alguna consulta falló (entonces no se cachea el "no hay")."""
    errors = errors if errors is not None else []
    for lang in ("es", "en"):
        try:
            hits = _api(lang, action="query", list="search", srsearch=f'"{album}" {artist}', srlimit=5)["query"]["search"]
        except Exception:
            errors.append(lang)
            continue
        titles = [h["title"] for h in hits if title_key(h["title"]) == title_key(album)][:2]
        if not titles:
            continue
        try:
            pages = _api(lang, action="query", prop="extracts|pageprops", exintro=1, explaintext=1, redirects=1,
                         ppprop="disambiguation", titles="|".join(titles))["query"]["pages"]
        except Exception:
            errors.append(lang)
            continue
        for p in pages:
            if is_album_page(p, artist, album, lang):
                ext = re.sub(r"\s+", " ", p["extract"]).strip()
                return {"lang": lang, "title": p["title"], "extract": ext[:2500],
                        "url": f"https://{lang}.wikipedia.org/wiki/{urllib.parse.quote(p['title'].replace(' ', '_'))}"}
    return None


def sentences(text, n=2, limit=360):
    parts = re.split(r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÑ¿¡\"“])", text.strip())
    out = ""
    for s in parts[:n]:
        if out and len(out) + len(s) > limit:
            break
        out = (out + " " + s).strip()
    return out[:limit].rstrip() + ("…" if len(out) > limit else "")


NUM_WORDS = {"uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9,
             "diez": 10, "once": 11, "doce": 12, "quince": 15, "veinte": 20, "treinta": 30, "cuarenta": 40, "cincuenta": 50,
             "cien": 100, "mil": 1000, "millon": 10 ** 6, "millones": 10 ** 6, "one": 1, "two": 2, "three": 3, "four": 4,
             "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "twelve": 12, "twenty": 20, "hundred": 100,
             "thousand": 1000, "million": 10 ** 6, "millions": 10 ** 6, "primer": 1, "primero": 1, "segundo": 2, "tercer": 3,
             "tercero": 3, "cuarto": 4, "quinto": 5, "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5}
EQUIV = {1: ("one", "first", "debut", "uno", "una", "primer", "primero"), 2: ("two", "second", "dos", "segundo"),
         3: ("three", "third", "tres", "tercer", "tercero"), 4: ("four", "fourth", "cuatro", "cuarto"), 5: ("five", "fifth", "cinco", "quinto")}


def unsupported(summary, source):
    """Números (en cifras o en palabras) y nombres propios del resumen que NO están en la fuente (vacía = válido)."""
    src = norm(source)
    src_words = set(src.split())
    src_nums = set(re.findall(r"\d+", source))
    bad = [n for n in re.findall(r"\d+", summary) if n not in src_nums]
    for w in norm(summary).split():
        if w in NUM_WORDS and w not in ("una", "uno", "primer", "primero") and w not in src_words:
            v = NUM_WORDS[w]
            same = {k for k, x in NUM_WORDS.items() if x == v} | set(EQUIV.get(v, ()))
            if str(v) not in src_nums and not (same & src_words):
                bad.append(w)
    for sent in re.split(r"(?<=[.!?:;])\s+", summary):
        words = [w.rstrip(".") for w in re.findall(r"[A-ZÁÉÍÓÚÑÜ][\wÁÉÍÓÚÑÜáéíóúñü'’.-]*", sent)]
        first = re.match(r"\W*([\wÁÉÍÓÚÑÜáéíóúñü'’.-]+)", sent)
        for w in words:
            # La primera palabra de la oración va con mayúscula igual ("Grabado en…"): no se exige, salvo que sea parte
            # de un nombre de varias palabras (la siguiente sí se exige, así que el nombre se valida igual).
            if first and w == first.group(1):
                continue
            key = norm(w)
            if key and key not in STOP_CAPS and f" {key} " not in f" {src} ":
                bad.append(w)
    return bad


def summarize(ask, extract):
    """ask(system, user) -> texto. Devuelve (texto, resumido: bool)."""
    system = ("Resumís en español rioplatense neutro, en 2 o 3 frases cortas, el texto que te pasan sobre un disco: cuándo y "
              "cómo se hizo, qué lugar ocupa, por qué se lo menciona. Usá SOLO hechos que estén en el texto; no agregues nombres, "
              "fechas, cifras ni opiniones que no estén ahí. Sin adjetivos de elogio. Respondé solo JSON {\"resumen\": \"...\"}.")
    try:
        out = json.loads(ask(system, extract[:1800])).get("resumen", "")
    except Exception:
        out = ""
    out = re.sub(r"\s+", " ", str(out)).strip()
    if 40 <= len(out) <= 480 and not unsupported(out, extract):
        return out, True
    return sentences(extract), False


def mb_line(mb_get, mbid, year, genres):
    """Respaldo sin prosa: "1963 · Blue Note · US · jazz, hard bop"."""
    label = country = ""
    try:
        rg = mb_get(f"https://musicbrainz.org/ws/2/release-group/{mbid}?inc=releases&fmt=json")
        rels = sorted((r for r in rg.get("releases", []) if r.get("date")), key=lambda r: r["date"])
        if rels:
            country = rels[0].get("country") or ""
            rel = mb_get(f"https://musicbrainz.org/ws/2/release/{rels[0]['id']}?inc=labels&fmt=json")
            label = next((li["label"]["name"] for li in rel.get("label-info", []) if li.get("label")), "")
    except Exception:
        pass
    return " · ".join(str(x) for x in (year, label, country, ", ".join(genres[:3])) if x)


def _file(data_dir):
    return Path(data_dir) / "recs" / "albumctx.json"


_ext_cache = {}


def _ext_file(data_dir):
    return Path(data_dir) / "recs" / "albumext.json"


def extract(mbid, artist, album, data_dir, fetch=True, chars=1200):
    """Primeros `chars` caracteres del artículo de Wikipedia del disco (evidencia para el clasificador), con caché en disco.
    None si no hay artículo. Si Wikipedia no respondió no se recuerda el "no hay". Con fetch=False solo mira la caché."""
    if not _ext_cache:
        try:
            _ext_cache.update(json.loads(_ext_file(data_dir).read_text()))
        except (OSError, ValueError):
            pass
    if mbid in _ext_cache:
        return _ext_cache[mbid] or None
    if not fetch:
        return None
    errors = []
    art = find_article(artist, album, errors)
    if not art and errors:
        return None
    _ext_cache[mbid] = art["extract"][:chars] if art else ""
    try:
        f = _ext_file(data_dir)
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(_ext_cache, ensure_ascii=False))
    except OSError:
        pass
    return _ext_cache[mbid] or None


def cached(mbid, data_dir):
    """Contexto ya guardado de un disco (sin consultar nada); None si todavía no se pidió."""
    if not _cache:
        try:
            _cache.update(json.loads(_file(data_dir).read_text()))
        except (OSError, ValueError):
            pass
    return _cache.get(mbid)


def get(mbid, artist, album, year, genres, ask, mb_get, data_dir):
    """{text, source: 'wikipedia'|'musicbrainz', url, lang, summarized} (con caché por mbid)."""
    if not _cache:
        try:
            _cache.update(json.loads(_file(data_dir).read_text()))
        except (OSError, ValueError):
            pass
    if mbid in _cache:
        return _cache[mbid]
    errors = []
    art = find_article(artist, album, errors)
    if art:
        text, summarized = summarize(ask, art["extract"])
        out = {"text": text, "source": "wikipedia", "url": art["url"], "lang": art["lang"], "summarized": summarized}
    else:
        out = {"text": mb_line(mb_get, mbid, year, genres), "source": "musicbrainz",
               "url": f"https://musicbrainz.org/release-group/{mbid}", "lang": "", "summarized": False}
    if not art and errors:
        return out  # Wikipedia no respondió: se muestra el respaldo pero se vuelve a intentar la próxima vez
    _cache[mbid] = out
    try:
        f = _file(data_dir)
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(_cache, ensure_ascii=False))
    except OSError:
        pass
    return out
