import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import tidal_source as ts


class Link:
    def __init__(self, n, expires_in=300.0):
        self.user_code, self.verification_uri, self.verification_uri_complete = f"C{n}", "link.tidal.com", f"link.tidal.com/C{n}"
        self.expires_in, self.interval, self.device_code = expires_in, 0.01, f"d{n}"


class FakeSession:
    """Simula tidalapi.Session: cada instancia pide un código nuevo; `authorized` decide qué códigos se autorizan."""
    made = []
    authorized = set()
    expires_in = 300.0

    def __init__(self):
        FakeSession.made.append(self)
        self.n = len(FakeSession.made)
        self.checks = 0

    def get_link_login(self):
        self.link = Link(self.n, FakeSession.expires_in)
        return self.link

    def _check_link_login(self, link, until_expiry=True):
        self.checks += 1
        time.sleep(0.005)
        if link.user_code in FakeSession.authorized:
            return {"access_token": "x"}
        raise TimeoutError("pendiente")

    def process_auth_token(self, result, is_pkce_token=True):
        return True

    def check_login(self):
        return True

    def save_session_to_file(self, path):
        Path(path).write_text("{}")


def wait_for(cond, timeout=3):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.01)
    return False


class LoginTests(unittest.TestCase):
    def setUp(self):
        FakeSession.made, FakeSession.authorized, FakeSession.expires_in = [], set(), 300.0
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.addCleanup(ts.login_cancel)
        fake_mod = mock.Mock(Session=FakeSession)
        for p in (mock.patch.dict("sys.modules", {"tidalapi": fake_mod}),
                  mock.patch.object(ts, "CONFIG_DIR", Path(tmp.name)),
                  mock.patch.object(ts, "TIDAL_SESSION", Path(tmp.name) / "tidal-session.json")):
            p.start()
            self.addCleanup(p.stop)
        ts.login_cancel()
        ts._session = None

    def test_devuelve_codigo_url_completa_y_vencimiento(self):
        r = ts.login_start()
        self.assertEqual(r["state"], "pending")
        self.assertEqual(r["code"], "C1")
        self.assertEqual(r["url"], "https://link.tidal.com/C1")
        self.assertAlmostEqual(r["expiresIn"], 300, delta=2)
        self.assertAlmostEqual(r["expiresAt"], time.time() + 300, delta=2)

    def test_pedir_dos_veces_reusa_el_mismo_intento(self):
        a, b = ts.login_start(), ts.login_start()
        self.assertEqual(a["code"], b["code"])
        self.assertEqual(len(FakeSession.made), 1)
        self.assertEqual(ts.login_status()["code"], "C1")

    def test_renovar_cancela_el_anterior_y_status_muestra_el_nuevo(self):
        ts.login_start()
        old = FakeSession.made[0]
        r = ts.login_start(renew=True)
        self.assertEqual(r["code"], "C2")
        self.assertEqual(ts.login_status()["code"], "C2")
        self.assertEqual(r["attempt"], 2)
        time.sleep(0.2)
        n = old.checks
        time.sleep(0.2)
        self.assertEqual(old.checks, n, "el hilo viejo siguió sondeando")

    def test_hilo_viejo_no_pisa_el_estado_nuevo(self):
        ts.login_start()
        old_attempt = ts._attempt
        r = ts.login_start(renew=True)
        ts._finish(old_attempt, state="expired", message="viejo")
        self.assertEqual(ts.login_status()["state"], "pending")
        self.assertEqual(ts.login_status()["code"], r["code"])

    def test_si_queda_poco_pide_codigo_nuevo(self):
        FakeSession.expires_in = 5.0
        ts.login_start()
        FakeSession.expires_in = 300.0
        self.assertEqual(ts.login_start()["code"], "C2")

    def test_vence_y_queda_expired(self):
        FakeSession.expires_in = 0.1
        ts.login_start()
        self.assertTrue(wait_for(lambda: ts.login_status()["state"] == "expired"))
        self.assertIn("venció", ts.login_status()["message"])
        self.assertNotIn("code", ts.login_status())

    def test_autorizado_guarda_sesion_y_queda_done(self):
        r = ts.login_start()
        FakeSession.authorized.add(r["code"])
        self.assertTrue(wait_for(lambda: ts.login_status()["state"] == "done"))
        self.assertTrue(ts.TIDAL_SESSION.exists())

    def test_cancelar_vuelve_a_idle_y_corta_el_hilo(self):
        ts.login_start()
        s = FakeSession.made[0]
        self.assertEqual(ts.login_cancel()["state"], "idle")
        time.sleep(0.2)
        n = s.checks
        time.sleep(0.2)
        self.assertEqual(s.checks, n)

    def test_status_expone_el_login_pendiente_para_retomarlo(self):
        r = ts.login_start()
        with mock.patch.object(ts, "_get_session", side_effect=ts.SourceError("no_session", "x")):
            st = ts.status()
        self.assertFalse(st["connected"])
        self.assertEqual(st["login"]["code"], r["code"])

    def test_pedidos_concurrentes_hacen_un_solo_intento(self):
        out = []
        hilos = [threading.Thread(target=lambda: out.append(ts.login_start())) for _ in range(6)]
        for t in hilos:
            t.start()
        for t in hilos:
            t.join()
        self.assertEqual(len(FakeSession.made), 1)
        self.assertEqual({o["code"] for o in out}, {"C1"})


if __name__ == "__main__":
    unittest.main()
