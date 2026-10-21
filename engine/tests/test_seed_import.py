"""Importador de la semilla con datos SINTÉTICOS (los datos reales viven solo en ~/.config/stemshed)."""
import os
import sys
import unittest
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import presets as P  # noqa: E402
import profile as PR  # noqa: E402
import seed_import as S  # noqa: E402

SEED = {
    "cuestionario": {"instrumento": "bajo", "nivel": "intermedio, lee poco", "mejorar": ["Teoría", "oído", "repertorio de x"],
                     "estilosQueAma": ["estilo a", "estilo b"], "estilosQueEvita": [], "artistasImprescindibles": ["Artista X", "Banda propia"], "miBanda": ["Banda propia"],
                     "musicaNueva": "algo", "comoEscucha": "discos enteros; a veces saca un tema de oído", "ritmoDeEstudio": "diario",
                     "contexto": {"horarioYDia": True, "ubicacionYClima": False, "ciudad": "Ciudad Z", "lat": 1.0, "lon": 2.0}},
    "memoriaNatural": {"quienSoy": "alguien", "gustosConEvidencia": ["g1"], "jazzPrimerasSenales": ["j1"], "noSabemos": ["n1"]},
    "eventosIniciales": [{"ts": "2026-01-02T10:00:00", "tipo": "album", "artista": "A", "titulo": "B", "accion": "guardó"},
                         {"ts": "2026-01-02T10:00:10", "tipo": "album", "artista": "A", "titulo": "B", "accion": "me encantó"},
                         {"ts": "2026-01-03T10:00:00", "tipo": "album", "artista": "C", "titulo": "D", "accion": "guardó"}],
    "perfiles": [
        {"nombre": "Noches", "intencion": "estudiar", "prioridad": 2, "novedad": "algo",
         "horario": [{"dias": ["lun", "mar", "mie", "jue", "vie"], "desde": "19:30", "hasta": "23:59"}, {"dias": ["sab", "dom"], "desde": "10:00", "hasta": "23:59"}]},
        {"nombre": "Oficina", "intencion": "concentrarme", "prioridad": 3, "novedad": "poco", "favorecer": ["instrumental o casi"],
         "horario": [{"dias": ["lun", "mar", "mie", "jue", "vie"], "desde": "09:00", "hasta": "18:00"}]},
        {"nombre": "Mañanas", "intencion": "estudiar", "prioridad": 2, "horario": [{"dias": ["sab", "dom"], "desde": "08:00", "hasta": "13:00"}]},
        {"nombre": "Siesta", "intencion": "libre", "prioridad": 1, "horario": [{"dias": ["dom"], "desde": "14:00", "hasta": "19:00"}]},
        {"nombre": "Manual", "intencion": "sorprenderme", "prioridad": 1, "horario": []},
        {"nombre": "Base", "intencion": "sorprenderme", "prioridad": 0, "horario": [], "porQue": "Perfil por defecto cuando no coincide nada."},
    ],
}


class Mapping(unittest.TestCase):
    def test_profile(self):
        patch, coords = S.map_profile(SEED)
        clean = PR.validate(patch)
        self.assertEqual(clean["improve"], ["teoria", "oido", "repertorio"])
        self.assertEqual(clean["essentials"], ["Artista X"])  # la banda propia nunca entra
        self.assertEqual(clean["listening"], "discos")
        self.assertIn("Nivel: intermedio", clean["notes"])
        self.assertEqual(coords, {"latitude": 1.0, "longitude": 2.0})

    def test_events(self):
        ev = sorted(S.map_events(SEED))
        self.assertEqual([(a, b, r) for _, a, b, r in ev], [("A", "B", "loved"), ("C", "D", "loved")])
        self.assertEqual(ev[0][0], datetime(2026, 1, 2, 10, 0, 10).timestamp())

    def test_presets_and_selection(self):
        m = S.map_presets(SEED)
        d = P.validate({"presets": m["presets"]})
        d["default"] = d["presets"][m["defaultIndex"]]["id"]
        self.assertEqual(d["default"], "base")
        self.assertEqual(d["presets"][1]["discovery"], "nada")   # "poco" -> nada
        self.assertTrue(d["presets"][1]["instrumental"])
        name = lambda wd, h, mi=0: P.select(d, wd, h * 60 + mi)[0]["name"]
        self.assertEqual(name(0, 10), "Oficina")       # lunes 10:00
        self.assertEqual(name(1, 21), "Noches")        # martes 21:00
        self.assertEqual(name(6, 15), "Siesta")        # domingo 15:00: el rango más corto gana aunque Noches tenga más prioridad
        self.assertEqual(name(5, 9), "Mañanas")        # sábado 9:00
        self.assertEqual(P.select(d, 2, 18 * 60 + 30), (d["presets"][5], "defecto"))  # miércoles 18:30: ninguno


if __name__ == "__main__":
    unittest.main()
