"""Tests del OCR Groq vision (lógica plana, sin Modal ni red real)."""

import pytest

from bot import ocr as ocr_mod


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
    monkeypatch.setattr(ocr_mod, "r2", FakeR2())
    monkeypatch.setattr(ocr_mod.telegram, "send_message",
                        lambda chat_id, text, **kw: acuses.append((chat_id, text)) or {})
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    return almacen, acuses


def _ok(texto):
    return FakeResp(200, {"choices": [{"message": {"content": texto}}]})


def test_ocr_ok_escribe_nota_y_acusa(ctx, monkeypatch):
    almacen, acuses = ctx
    almacen["inbox/fotos/2026-10-30_00-00-00--foto.jpg"] = b"JPGDATA"
    monkeypatch.setattr(ocr_mod.requests, "post", lambda *a, **k: _ok("Lista:\n- pan\n- leche"))
    nota = ocr_mod._run_ocr(
        "inbox/fotos/2026-10-30_00-00-00--foto.jpg", 1, 9,
        "2026-10-30_00-00-00", "2026-10-30T00:00:00.0000000Z", "")
    assert nota == "inbox/fotos/2026-10-30_00-00-00--foto.md"
    contenido = almacen[nota].decode()
    assert "- pan" in contenido and "scout" in contenido
    assert "telegram_msg_id: 9" in contenido
    assert "![[2026-10-30_00-00-00--foto.jpg]]" in contenido
    assert acuses and "OCR listo" in acuses[0][1]


def test_ocr_fallback_al_segundo_modelo(ctx, monkeypatch):
    almacen, acuses = ctx
    almacen["inbox/fotos/2026-10-30_00-00-00--foto.jpg"] = b"JPGDATA"
    llamadas = []

    def postar(url, headers=None, json=None, timeout=None):
        llamadas.append(json["model"])
        if len(llamadas) == 1:
            return FakeResp(404, text='{"error": {"code": "model_not_found"}}')
        return _ok("texto recuperado")

    monkeypatch.setattr(ocr_mod.requests, "post", postar)
    nota = ocr_mod._run_ocr(
        "inbox/fotos/2026-10-30_00-00-00--foto.jpg", 1, 9,
        "2026-10-30_00-00-00", "2026-10-30T00:00:00.0000000Z", "")
    assert len(llamadas) == 2
    assert "maverick" in llamadas[1] and "texto recuperado" in almacen[nota].decode()


def test_ocr_todo_falla_sin_nota(ctx, monkeypatch):
    almacen, acuses = ctx
    almacen["inbox/fotos/2026-10-30_00-00-00--foto.jpg"] = b"JPGDATA"
    monkeypatch.setattr(ocr_mod.requests, "post",
                        lambda *a, **k: FakeResp(401, text="invalid api key"))
    with pytest.raises(RuntimeError, match="Groq OCR falló"):
        ocr_mod._run_ocr(
            "inbox/fotos/2026-10-30_00-00-00--foto.jpg", 1, 9,
            "2026-10-30_00-00-00", "2026-10-30T00:00:00.0000000Z", "")
    assert not [k for k in almacen if k.endswith(".md")]
    assert not acuses
