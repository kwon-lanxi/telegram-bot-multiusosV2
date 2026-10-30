"""Tests del ASR Groq (lógica plana, sin Modal ni red real)."""

import pytest

from bot import asr as asr_mod


class FakeResp:
    def __init__(self, status=200, payload=None, text=""):
        self.status_code = status
        self._payload = payload or {}
        self.text = text or ""

    def json(self):
        return self._payload


@pytest.fixture
def ctx(monkeypatch):
    almacen = {}

    class FakeR2:
        def put_bytes(self, k, data, content_type="application/octet-stream"):
            almacen[k] = data
            return k

        def get_bytes(self, k):
            return almacen[k]

    acuses = []
    monkeypatch.setattr(asr_mod, "r2", FakeR2())
    monkeypatch.setattr(asr_mod.telegram, "send_message",
                        lambda chat_id, text, **kw: acuses.append((chat_id, text)) or {})
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    return almacen, acuses


def test_groq_ok_escribe_nota_y_acusa(ctx, monkeypatch):
    almacen, acuses = ctx
    almacen["inbox/audio/2026-10-30_00-00-00--voz.ogg"] = b"OGGDATA"
    monkeypatch.setattr(
        asr_mod.requests, "post",
        lambda *a, **k: FakeResp(200, {"text": "hola mundo", "language": "spanish"}),
    )
    nota = asr_mod._run_transcription(
        "inbox/audio/2026-10-30_00-00-00--voz.ogg", 1, 7,
        "2026-10-30_00-00-00", "2026-10-30T00:00:00.0000000Z")
    assert nota == "inbox/audio/2026-10-30_00-00-00--voz.md"
    contenido = almacen[nota].decode()
    assert "hola mundo" in contenido and "spanish" in contenido
    assert "telegram_msg_id: 7" in contenido
    assert "![[2026-10-30_00-00-00--voz.ogg]]" in contenido
    assert acuses and "Transcripción lista" in acuses[0][1]


def test_groq_401_lanza_sin_escribir_nota(ctx, monkeypatch):
    almacen, acuses = ctx
    almacen["inbox/audio/2026-10-30_00-00-00--voz.ogg"] = b"OGGDATA"
    monkeypatch.setattr(
        asr_mod.requests, "post",
        lambda *a, **k: FakeResp(401, text="invalid api key"),
    )
    with pytest.raises(RuntimeError, match="Groq 401"):
        asr_mod._run_transcription(
            "inbox/audio/2026-10-30_00-00-00--voz.ogg", 1, 7,
            "2026-10-30_00-00-00", "2026-10-30T00:00:00.0000000Z")
    assert not [k for k in almacen if k.endswith(".md")]
    assert not acuses
