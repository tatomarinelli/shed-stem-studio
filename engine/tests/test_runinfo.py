"""Variables con las que corre una búsqueda (lo que se mostró en la pantalla Agentes): estructura corta, sin el texto del prompt. Puro, sin red."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import runinfo as RI  # noqa: E402

PROF = {"instrument": "guitarra", "level": "avanzado", "improve": ["modos", "oido"], "loves": ["jazz"], "avoids": ["smooth jazz"], "discovery": "algo",
        "listening": "discos", "ownArtists": ["Mi Banda"]}
W = {"artists": [{"name": f"A{i}", "w": 3.04 - i} for i in range(9)], "genres": [{"name": "jazz", "w": 4.0}], "decades": [{"name": "1960s", "w": 1.0}]}
LABELS = {"modos": "modos", "oido": "oído"}
ENGINE = {"model": "m", "reviewer": None}


def run(**kw):
    base = dict(kind="request", request={}, prof=PROF, preset={"name": "Trabajo", "how": "horario"}, pdata={"intent": "concentrarme", "instrumental": True, "favor": ["x"]},
                mode="concentrarme", alpha=0.65, plan={"kind": "para_vos", "label": "Para vos", "useInstrument": True, "useGoals": True, "useTaste": True, "requestWeight": 0.0, "why": []}, ctx_text=None, weights=W, focus_labels=LABELS, favorites=120, reactions=7, excluded=130, shown_recently=4,
                avoid=["smooth jazz"], own_artists=["Mi Banda"], half_life_days=180.0, engine=ENGINE)
    base.update(kw)
    return RI.describe(**base)


class Describe(unittest.TestCase):
    def test_request_genre_strict_type_and_where_the_mode_came_from(self):
        r = run(request={"genres": ["dub"], "strict": True, "genresDetected": True, "type": "live"}, mode="concentrarme")["request"]
        self.assertEqual((r["genres"], r["strict"], r["genresDetected"], r["type"]), (["dub"], True, True, "live"))
        self.assertEqual((r["mode"], r["modeFrom"]), ("concentrarme", "perfil"))  # el modo sale del perfil activo, no lo pidió
        r = run(request={"mode": "estudiar"}, mode="estudiar")["request"]
        self.assertEqual(r["modeFrom"], "pedido")
        self.assertIsNone(run(request={}, mode=None)["request"]["mode"])
        self.assertIsNone(run(request={"prompt": "hola"})["request"]["strict"])  # sin género no hay "estricto"

    def test_written_era_is_shown_in_the_request_even_without_the_planner(self):
        r = run(request={"prompt": "dub de los 70", "era": {"from": 1970, "to": 1979, "source": "reglas", "strict": True}})["request"]
        self.assertEqual(r["era"], {"from": 1970, "to": 1979, "source": "reglas", "strict": True})
        self.assertIsNone(run(request={"prompt": "dub"})["request"]["era"])

    def test_free_text_is_cut_and_a_seed_is_summarized(self):
        r = run(request={"prompt": "x" * 200, "seed": {"artist": "Miles Davis", "album": "Kind of Blue"}})["request"]
        self.assertTrue(r["hasText"])
        self.assertEqual(len(r["text"]), RI.SHORT + 1)
        self.assertEqual(r["seed"], "Miles Davis - Kind of Blue")
        self.assertFalse(run(request={})["request"]["hasText"])

    def test_profile_focus_only_when_studying_or_without_a_mode(self):
        p = run(mode="estudiar")["profile"]
        self.assertEqual((p["focus"], p["focusSkipped"]), (["modos", "oído"], False))
        p = run(mode="concentrarme")["profile"]
        self.assertEqual((p["focus"], p["focusSkipped"]), ([], True))  # lo que quiere mejorar no se usa en otro modo: se dice
        self.assertEqual(run(mode=None)["profile"]["focus"], ["modos", "oído"])
        p = run()["profile"]
        self.assertEqual((p["instrument"], p["level"], p["discovery"], p["ownArtists"]), ("guitarra", "avanzado", "algo", ["Mi Banda"]))

    def test_preset_discovery_overrides_the_profile_one(self):
        self.assertEqual(run(pdata={"intent": "libre", "discovery": "mucho"})["profile"]["discovery"], "mucho")

    def test_scoring_weights_explain_how_much_taste_vs_request_counts(self):
        s = run(alpha=0.65)["scoring"]
        self.assertEqual((s["tastePct"], s["genreWeightPct"], s["textWeightPct"]), (65, None, None))
        self.assertEqual(run(request={"genres": ["dub"]})["scoring"]["genreWeightPct"], 75)
        self.assertEqual(run(request={"prompt": "algo"})["scoring"]["textWeightPct"], 65)
        self.assertIsNone(run(request={"genres": ["dub"], "prompt": "algo"})["scoring"]["textWeightPct"])  # con género manda el género

    def test_taste_is_trimmed_and_rounded_and_exclusions_are_counts(self):
        t = run()["taste"]
        self.assertEqual(len(t["artists"]), 6)
        self.assertEqual(t["artists"][0], {"name": "A0", "w": 3.0})
        self.assertEqual((t["favorites"], t["reactions"], t["halfLifeDays"]), (120, 7, 180))
        self.assertEqual(run()["exclusions"], {"known": 130, "shownRecently": 4})

    def test_context_and_engine_pass_through_and_no_prompt_text_is_included(self):
        r = run(ctx_text="jueves por la tarde, nublado", engine={"model": "gemma3:4b", "reviewer": "same"})
        self.assertEqual((r["context"], r["engine"]["model"]), ("jueves por la tarde, nublado", "gemma3:4b"))
        self.assertIsNone(run()["context"])
        self.assertNotIn("Eres", str(r))  # nada del prompt: solo variables

    def test_unfilled_profile_is_flagged(self):
        r = run(prof={"improve": [], "loves": [], "discovery": "algo", "listening": "ambos"})
        self.assertFalse(r["profile"]["filled"])

    def test_planner_view_is_off_by_default_and_never_presents_the_brief_as_fact(self):
        self.assertEqual(run()["planner"], {"enabled": False})
        req = {"prompt": "x", "era": {"from": 1970, "to": 1979, "source": "modelo", "strict": True},
               "plan": {"mood": "tranquilo", "instrumental": True, "language": "ingles", "refs": ["Spinetta"], "genres": ["jazz"], "brief": "Discos suaves."}}
        v = run(request=req, planner={"enabled": True, "model": "m", "ran": True, "ok": True, "seconds": 1.5, "added": ["época 1970-1979"], "dropped": ["x", "y"]})["planner"]
        self.assertEqual((v["enabled"], v["ok"], v["model"], v["dropped"]), (True, True, "m", 2))
        self.assertEqual(v["era"], {"from": 1970, "to": 1979, "source": "modelo", "strict": True})
        self.assertEqual((v["mood"], v["instrumental"], v["language"], v["refs"], v["brief"]), ("tranquilo", True, "inglés", ["Spinetta"], "Discos suaves."))  # etiquetas de una tabla fija
        v = run(request={"prompt": "x"}, planner={"enabled": True, "model": "m", "ran": True, "ok": False})["planner"]
        self.assertEqual((v["ok"], v["era"], v["brief"], v["mood"]), (False, None, None, None))  # falló: no hay nada que mostrar como entendido


if __name__ == "__main__":
    unittest.main()
