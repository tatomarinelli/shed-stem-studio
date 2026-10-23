"""Barrera de género: decide, con datos de MusicBrainz, si un disco pertenece al género que pidió el usuario.

Funciones puras (sin red). El modelo local propone discos; esto es lo que impide que un disco de otro género llegue al
resultado, y cada decisión lleva el motivo armado con los géneros reales (nunca texto inventado).

Estados: match (es del género), weak (cercano: comparte raíz o es un género vecino), off (tiene géneros y no coinciden),
unknown (MusicBrainz no tiene géneros ni del disco ni del artista: no se puede comprobar).
"""
import re
import unicodedata

MATCH, WEAK = 0.9, 0.5   # puntaje mínimo para "match" y para "weak"

# Español / variantes -> como lo escribe MusicBrainz (todo en minúsculas y sin tildes).
ALIASES = {
    "electronica": "electronic", "musica electronica": "electronic", "clasica": "classical", "musica clasica": "classical",
    "jazz modal": "modal jazz", "jazz latino": "latin jazz", "jazz fusion": "jazz fusion", "fusion": "jazz fusion",
    "reggae roots": "roots reggae", "rock progresivo": "progressive rock", "rock psicodelico": "psychedelic rock",
    "rock alternativo": "alternative rock", "folklore": "folk", "musica folk": "folk", "bossa": "bossa nova",
    "drum and bass": "drum n bass", "dnb": "drum n bass", "hip hop": "hip-hop", "hiphop": "hip-hop", "rap": "hip-hop",
    "r&b": "rnb", "r and b": "rnb", "afro": "afrobeat", "organic house": "organic house", "tech house": "tech house",
    "post rock": "post-rock", "postrock": "post-rock", "lofi": "lo-fi", "lo fi": "lo-fi", "ambiente": "ambient",
    "blues rock": "blues rock", "cumbia": "cumbia", "tango": "tango", "salsa": "salsa", "candombe": "candombe",
}

# Hijo -> géneros "padre" de los que cuelga. Una coincidencia por el padre es "cercana", no exacta.
PARENTS = {
    "dub": {"reggae"}, "roots reggae": {"reggae"}, "dancehall": {"reggae"}, "ska": {"reggae"}, "dub techno": {"dub", "techno"},
    "modal jazz": {"jazz"}, "hard bop": {"jazz", "bebop"}, "bebop": {"jazz"}, "cool jazz": {"jazz"}, "soul jazz": {"jazz"},
    "latin jazz": {"jazz"}, "jazz fusion": {"jazz", "fusion"}, "free jazz": {"jazz"}, "post-bop": {"jazz"}, "smooth jazz": {"jazz"},
    "bossa nova": {"latin jazz", "brazilian"}, "progressive rock": {"rock"}, "psychedelic rock": {"rock"}, "post-rock": {"rock"},
    "hard rock": {"rock"}, "indie rock": {"rock"}, "alternative rock": {"rock"}, "punk rock": {"punk", "rock"},
    "deep house": {"house"}, "tech house": {"house", "techno"}, "organic house": {"house"}, "progressive house": {"house"},
    "melodic techno": {"techno"}, "minimal techno": {"techno"}, "ambient techno": {"techno", "ambient"},
    "drum n bass": {"electronic"}, "trip hop": {"electronic", "hip-hop"}, "idm": {"electronic"}, "downtempo": {"electronic"},
}

# Vocabulario base (autocompletado y detección en el pedido escrito). Se complementa con lo que ya conoce la app.
GENRES = sorted(set(ALIASES.values()) | set(PARENTS) | {p for ps in PARENTS.values() for p in ps} | {
    "jazz", "rock", "pop", "folk", "blues", "soul", "funk", "disco", "house", "techno", "trance", "ambient", "electronic",
    "classical", "reggae", "hip-hop", "metal", "punk", "country", "latin", "samba", "cumbia", "tango", "afrobeat", "gospel",
    "r&b", "indie", "shoegaze", "dream pop", "noise", "experimental", "krautrock", "new wave", "synth-pop", "lo-fi", "grunge",
    "heavy metal", "death metal", "black metal", "doom metal", "math rock", "emo", "swing", "big band", "gypsy jazz", "bolero",
    "flamenco", "fado", "highlife", "dubstep", "garage", "breakbeat", "jungle", "uk garage", "neo soul", "acid jazz", "trap"})


def norm(text):
    t = unicodedata.normalize("NFD", str(text).lower().replace("&", " and ").replace("’", "'"))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\- ]+", " ", "".join(c for c in t if not unicodedata.combining(c)))).strip()


def canon(genre):
    """Forma canónica de un género (alias en español, variantes de escritura)."""
    g = norm(genre)
    g = ALIASES.get(g, g)
    return "rnb" if g in ("r and b", "rnb") else g


def _tokens(g):
    return set(re.split(r"[ \-]+", g)) - {""}


def relation(want, have, soft=0.0):
    """(0-1, vía) de cuánto el género `have` del disco satisface el género pedido `want`. `soft` = similitud por embeddings
    (0-1): solo suma una pista suave, nunca alcanza para "match" por sí sola (los embeddings confunden géneros lejanos)."""
    w, h = canon(want), canon(have)
    if not w or not h:
        return 0.0, ""
    if w == h:
        return 1.0, "igual"
    tw, th = _tokens(w), _tokens(h)
    if tw and tw <= th:                      # pedido "dub", disco "dub techno": el disco es una variante del pedido
        return 0.9, "variante"
    if w in PARENTS.get(h, ()):              # pedido "reggae", disco "dub": el disco es un subgénero
        return 0.9, "subgénero"
    if h in PARENTS.get(w, ()):              # pedido "dub", disco "reggae": el disco es de la familia, no del estilo
        return 0.5, "familia"
    if th and th <= tw:                      # pedido "roots reggae", disco "reggae"
        return 0.5, "familia"
    if PARENTS.get(w, set()) & PARENTS.get(h, set()):  # hermanos (dub y dancehall)
        return 0.4, "vecino"
    return min(0.45, 0.45 * soft), "similar" if soft else ""


TOP = 3          # el género pedido tiene que estar entre los más votados para ser "match"; más abajo es un rasgo secundario
FAR_CAP = 0.6    # y vale como mucho "cercano"


def _best(wants, haves, vecs, sim):
    best = (0.0, None)
    for w in wants:
        for rank, h in enumerate(haves):
            s = sim(w, h, vecs) if sim and vecs and w in vecs and h in vecs else 0.0
            v, via = relation(w, h, s)
            if rank >= TOP and v > FAR_CAP:  # MusicBrainz ordena de más a menos votado: "ambient" en 5.º lugar de un disco de post-rock no lo hace ambient
                v, via = FAR_CAP, via + " (secundario)"
            if v > best[0]:
                best = (v, {"want": w, "have": h, "v": round(v, 2), "via": via})
    return best


def judge(wants, disc_genres, artist_genres=(), vecs=None, sim=None):
    """Veredicto de la barrera para un disco. wants: géneros pedidos (cualquiera sirve). disc_genres: de MusicBrainz, de más a
    menos votado. artist_genres: respaldo cuando el disco no tiene. sim(want, have, vecs) -> 0-1 por embeddings (opcional).
    Devuelve {status, score, matched, source, why}."""
    wants = [w for w in (canon(x) for x in wants) if w]
    if not wants:
        return {"status": "match", "score": 1.0, "matched": None, "source": None, "why": ""}
    for source, haves in (("disco", disc_genres), ("artista", artist_genres)):
        haves = [h for h in haves if h]
        if not haves:
            continue
        score, m = _best(wants, haves, vecs, sim)
        status = "match" if score >= MATCH else "weak" if score >= WEAK else "off"
        if status != "off" or source == "artista" or not artist_genres:
            return {"status": status, "score": round(score, 2), "matched": m, "source": source,
                    "why": _why(status, wants, haves, m, source)}
        # El disco tiene géneros que no coinciden pero hay géneros del artista: si ellos sí coinciden es solo "cercano".
        a_score, am = _best(wants, [h for h in artist_genres if h], vecs, sim)
        if a_score >= MATCH:
            return {"status": "weak", "score": round(min(a_score, 0.6), 2), "matched": am, "source": "artista",
                    "why": f"El disco no trae su género, pero el artista sí ({am['have']})."}
        return {"status": "off", "score": round(score, 2), "matched": m, "source": source, "why": _why("off", wants, haves, m, source)}
    return {"status": "unknown", "score": 0.0, "matched": None, "source": None,
            "why": "MusicBrainz no tiene géneros de este disco ni de su artista: no se puede comprobar."}


def _why(status, wants, haves, m, source):
    where = "del disco" if source == "disco" else "del artista"
    have = ", ".join(haves[:3])
    want = ", ".join(wants[:2])
    if status == "match":
        return f"Pediste {want}: coincide con {m['have']} (géneros {where}: {have})."
    if status == "weak":
        return f"Cercano a {want}: {m['have']} es de la misma familia (géneros {where}: {have})."
    return f"No es {want}: MusicBrainz lo clasifica como {have}."


AMBIGUOUS = {"disco"}  # "un disco de jazz": en español es el álbum, no el género (el género se pide como "disco music")


def detect(text, extra=()):
    """Géneros nombrados en un pedido escrito ("algo de dub y reggae" -> ["dub", "reggae"]). Prueba frases de 3, 2 y 1 palabras."""
    words = norm(text).split()
    vocab = ({canon(g) for g in GENRES} | {canon(g) for g in extra} | set(ALIASES)) - AMBIGUOUS
    found, i = [], 0
    while i < len(words):
        for n in (3, 2, 1):
            phrase = " ".join(words[i:i + n])
            if len(words[i:i + n]) == n and phrase in vocab and (n > 1 or len(phrase) > 2):
                c = canon(phrase)
                if c not in found:
                    found.append(c)
                i += n
                break
        else:
            i += 1
    return found
