"""models.chat: el cuerpo que se manda al servidor y la conexión cortable (cancelar). Sin red."""
import io
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import models  # noqa: E402

REPLY = {"message": {"content": "{\"a\": 1}"}, "prompt_eval_count": 7, "eval_count": 3}


class Resp(io.BytesIO):
    closed_by = None

    def close(self):
        Resp.closed_by = "close"
        super().close()


class Chat(unittest.TestCase):
    def setUp(self):
        self.sent = {}
        p = mock.patch.object(models, "PROVIDER", "ollama")
        p.start()
        self.addCleanup(p.stop)

    def fake(self, path, body=None, timeout=3):
        self.sent.update(path=path, body=body)
        return Resp(json.dumps(REPLY).encode())

    def test_thinking_is_turned_off_so_reasoning_models_return_json(self):
        """Medido: qwen3:8b con razonamiento dejó el contenido vacío y las 8 corridas fallaron con JSONDecodeError."""
        with mock.patch.object(models, "_ollama", self.fake):
            out = models.chat("qwen3:8b", "sys", "user", {"type": "object"}, 0.2, 40)
        self.assertIs(self.sent["body"]["think"], False)
        self.assertEqual(self.sent["body"]["format"], {"type": "object"})
        self.assertEqual(out, ("{\"a\": 1}", 7, 3))

    def test_connection_is_registered_while_reading_and_released_after(self):
        holder = []
        seen = []

        class Spy(Resp):
            def read(self, *a):
                seen.append(list(holder))
                return super().read(*a)

        with mock.patch.object(models, "_ollama", lambda *a, **k: Spy(json.dumps(REPLY).encode())):
            models.chat("m", "s", "u", {"type": "object"}, 0.2, 10, holder=holder)
        self.assertEqual(len(seen[0]), 1)  # mientras lee, otro hilo puede cortarla
        self.assertEqual(holder, [])       # al terminar, ya no está

    def test_closing_the_connection_aborts_the_read(self):
        holder = []

        class Cut(Resp):
            def read(self, *a):
                for r in list(holder):
                    r.close()  # lo que hace recs.cancel()
                return super().read(*a)

        with mock.patch.object(models, "_ollama", lambda *a, **k: Cut(json.dumps(REPLY).encode())):
            with self.assertRaises(ValueError):  # leer de una conexión cerrada
                models.chat("m", "s", "u", {"type": "object"}, 0.2, 10, holder=holder)
        self.assertEqual(holder, [])


if __name__ == "__main__":
    unittest.main()
