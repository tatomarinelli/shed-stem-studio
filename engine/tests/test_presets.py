"""Perfiles de sugerencia: selección por día y hora (puro, sin reloj)."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import presets as P  # noqa: E402

LUN, MAR, VIE, SAB, DOM = 0, 1, 4, 5, 6


def at(h, m=0):
    return h * 60 + m


class Select(unittest.TestCase):
    def setUp(self):
        self.d = P.validate(P.DEFAULTS)

    def name(self, wd, minute):
        p, how = P.select(self.d, wd, minute)
        return p["name"], how

    def test_weekdays(self):
        self.assertEqual(self.name(MAR, at(10)), ("Trabajo", "horario"))
        self.assertEqual(self.name(MAR, at(18)), ("Estudio", "horario"))  # el fin es exclusivo: 18:00 ya es Estudio
        self.assertEqual(self.name(SAB, at(10)), ("Estudio", "horario"))

    def test_midnight_crossing(self):
        self.assertEqual(self.name(MAR, at(1, 30)), ("Estudio", "horario"))   # lunes 18:00 -> martes 02:00
        self.assertEqual(self.name(LUN, at(1, 30)), ("Estudio", "horario"))   # domingo 18:00 -> lunes 02:00
        self.assertEqual(self.name(SAB, at(1, 30)), ("Estudio", "horario"))   # viernes 18:00 -> sábado 02:00 y sábado entero
        self.assertEqual(self.name(MAR, at(3)), ("Estudio", "defecto"))       # 3 a 9 no tiene perfil: el de por defecto

    def test_monday_early_is_default(self):
        # El rango de domingo es 00:00-24:00 (no cruza), así que lunes 1:30 no está cubierto por el fin de semana;
        # tampoco por "lun-vie 18-02" (eso cubre martes a sábado de madrugada).
        d = P.validate({"presets": [{"name": "Noche", "intent": "estudiar", "schedule": [{"days": [MAR], "start": "22:00", "end": "02:00"}]},
                                    {"name": "Base", "intent": "libre"}], "default": "base"})
        self.assertEqual(P.select(d, MAR, at(23))[0]["name"], "Noche")
        self.assertEqual(P.select(d, 2, at(1))[0]["name"], "Noche")     # miércoles 1:00 viene del martes
        self.assertEqual(P.select(d, MAR, at(1))[0]["name"], "Base")    # martes 1:00 no
        self.assertEqual(P.select(d, MAR, at(1))[1], "defecto")

    def test_overlap_more_specific_wins(self):
        d = P.validate({"presets": [
            {"name": "Semana", "intent": "concentrarme", "schedule": [{"days": [0, 1, 2, 3, 4], "start": "08:00", "end": "20:00"}]},
            {"name": "Almuerzo", "intent": "sorprenderme", "schedule": [{"days": [0, 1, 2, 3, 4], "start": "13:00", "end": "14:00"}]}]})
        self.assertEqual(P.select(d, VIE, at(13, 30))[0]["name"], "Almuerzo")
        self.assertEqual(P.select(d, VIE, at(15))[0]["name"], "Semana")
        # Mismo largo: gana el de más arriba.
        d2 = P.validate({"presets": [{"name": "A", "intent": "libre", "schedule": [{"days": [DOM], "start": "10:00", "end": "11:00"}]},
                                     {"name": "B", "intent": "libre", "schedule": [{"days": [DOM], "start": "10:00", "end": "11:00"}]}]})
        self.assertEqual(P.select(d2, DOM, at(10, 30))[0]["name"], "A")

    def test_explicit_over_beats_specificity(self):
        d = P.validate({"presets": [
            {"id": "finde", "name": "Finde", "intent": "estudiar", "schedule": [{"days": [DOM], "start": "00:00", "end": "24:00"}], "over": ["siesta"]},
            {"id": "siesta", "name": "Siesta", "intent": "libre", "schedule": [{"days": [DOM], "start": "14:00", "end": "19:00"}]}]})
        self.assertEqual(P.select(d, DOM, at(15))[0]["name"], "Finde")
        d["presets"][0]["over"] = []
        self.assertEqual(P.select(d, DOM, at(15))[0]["name"], "Siesta")
        d["presets"][0]["over"], d["presets"][1]["over"] = ["siesta"], ["finde"]  # ciclo: vuelve a la regla normal
        self.assertEqual(P.select(d, DOM, at(15))[0]["name"], "Siesta")

    def test_none_matches_uses_default(self):
        d = P.validate({"presets": [{"name": "X", "intent": "libre", "schedule": []}, {"name": "Y", "intent": "estudiar"}], "default": "y"})
        self.assertEqual(P.select(d, LUN, at(12)), (d["presets"][1], "defecto"))


class Validate(unittest.TestCase):
    def test_rejects_bad(self):
        for bad in ({"presets": []}, {"presets": [{"name": "", "intent": "libre"}]}, {"presets": [{"name": "a", "intent": "dormir"}]},
                    {"presets": [{"name": "a", "intent": "libre", "schedule": [{"days": [1], "start": "9", "end": "10:00"}]}]},
                    {"presets": [{"name": "a", "intent": "libre", "schedule": [{"days": [], "start": "09:00", "end": "10:00"}]}]},
                    {"presets": [{"name": "a", "intent": "libre", "schedule": [{"days": [1], "start": "09:00", "end": "09:00"}]}]}):
            with self.assertRaises(P.PresetError):
                P.validate(bad)

    def test_ids_and_roundtrip(self):
        d = P.validate({"presets": [{"name": "Mi Perfil!", "intent": "libre"}, {"id": "mi-perfil", "name": "Otro", "intent": "libre"}]})
        self.assertEqual([p["id"] for p in d["presets"]], ["mi-perfil", "otro"])
        with tempfile.TemporaryDirectory() as t:
            path = os.path.join(t, "presets.json")
            P.save(path, d)
            self.assertEqual(P.load(path), d)
            self.assertEqual(oct(os.stat(path).st_mode & 0o777), "0o600")
        self.assertEqual(P.load("/nonexistent")["default"], "estudio")


if __name__ == "__main__":
    unittest.main()
