import unittest
from unittest import mock

import firstrun
import settings


def base(**over):
    cfg = {"musicFolders": [], "setup": {"done": False, "skipped": []}, **settings.DEFAULTS, **over}
    cfg.setdefault("setup", {"done": False, "skipped": []})
    return cfg


class Patches:
    def __init__(self, env=False, model=False, folders=(), tidal=False, chat=None, profile=False, setup=None, tracks=None):
        s = base(musicFolders=list(folders))
        if setup is not None:
            s["setup"] = setup
        self.ps = [mock.patch.object(firstrun.settings, "load", return_value=s),
                   mock.patch.object(firstrun.envsetup, "present", return_value=env),
                   mock.patch.object(firstrun.stems, "sep_model_present", return_value=model),
                   mock.patch.object(firstrun.tidal_source, "status", return_value={"connected": tidal}),
                   mock.patch.object(firstrun, "_chat_models", return_value=chat),
                   mock.patch.dict(firstrun.library._state, {"tracks": tracks if tracks is not None else ({"a": 1} if folders else {}), "scanning": False}),
                   mock.patch.object(firstrun.recs.profile_mod, "filled", return_value=profile),
                   mock.patch.object(firstrun.recs, "load_profile", return_value={})]

    def __enter__(self):
        for p in self.ps:
            p.start()

    def __exit__(self, *a):
        for p in self.ps:
            p.stop()


def states(st):
    return {x["id"]: x["state"] for x in st["steps"]}


class FirstRun(unittest.TestCase):
    def test_empty_install_shows_wizard(self):
        with Patches():
            st = firstrun.status()
        self.assertTrue(st["show"])
        self.assertFalse(st["complete"])
        self.assertEqual(states(st)["separacion"], "pending")
        self.assertEqual(st["missing"], ["separacion", "musica", "modelo", "perfil"])

    def test_everything_ready_never_shows(self):
        with Patches(env=True, model=True, tidal=True, chat=[{"name": "mistral-nemo"}], profile=True):
            st = firstrun.status()
        self.assertTrue(st["complete"])
        self.assertFalse(st["show"])
        self.assertFalse(st["notice"])

    def test_partial_steps(self):
        with Patches(env=True, model=False, folders=["/music"], chat=[], profile=False):
            s = states(firstrun.status())
        self.assertEqual((s["separacion"], s["musica"], s["modelo"], s["perfil"]), ("pending", "done", "pending", "pending"))

    def test_skipped_step_and_closed_wizard_gives_notice(self):
        with Patches(setup={"done": True, "skipped": ["modelo"]}, env=True, model=True, folders=["/m"], profile=True, chat=[]):
            st = firstrun.status()
        self.assertEqual(states(st)["modelo"], "skipped")
        self.assertFalse(st["show"])
        self.assertTrue(st["notice"])

    def test_model_server_down_is_pending(self):
        with Patches(chat=None):
            st = firstrun.status()
        modelo = next(x for x in st["steps"] if x["id"] == "modelo")
        self.assertEqual(modelo["state"], "pending")
        self.assertFalse(modelo["detail"]["serverUp"])

    def test_embedding_model_does_not_count(self):
        tags = [{"name": "nomic-embed-text:latest"}, {"name": "mistral-nemo:latest"}]
        with mock.patch.object(firstrun.models, "ollama_tags", return_value=tags):
            self.assertEqual([m["name"] for m in firstrun._chat_models()], ["mistral-nemo:latest"])

    def test_settings_validation_of_setup(self):
        self.assertEqual(settings.validate({"setup": {"done": True, "skipped": ["modelo", "modelo"]}})["setup"], {"done": True, "skipped": ["modelo"]})
        for bad in ({"done": "si"}, {"skipped": ["otro"]}, {"skipped": "x"}, "x"):
            with self.assertRaises(settings.SettingsError):
                settings.validate({"setup": bad})



class EmptyFolder(unittest.TestCase):
    def test_empty_music_folder_does_not_count(self):
        with Patches(folders=["/music"], tracks={}):
            self.assertEqual(states(firstrun.status())["musica"], "pending")

    def test_folder_with_tracks_counts(self):
        with Patches(folders=["/music"], tracks={"L1": {}}):
            self.assertEqual(states(firstrun.status())["musica"], "done")

    def test_scanning_folder_counts_to_avoid_flash(self):
        with Patches(folders=["/music"], tracks={}):
            with mock.patch.dict(firstrun.library._state, {"scanning": True}):
                self.assertEqual(states(firstrun.status())["musica"], "done")


if __name__ == "__main__":
    unittest.main()
