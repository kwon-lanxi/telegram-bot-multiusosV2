"""Tests del dispatch M1 con mocks: no red, no R2 real, no Telegram real."""

import pytest

from bot import worker as wk


class FakeR2:
    def __init__(self):
        self.objects: dict[str, bytes] = {}

    def put_bytes(self, key, data, content_type="application/octet-stream"):
        self.objects[key] = data
        return key

    def get_bytes(self, key):
        return self.objects[key]

    def exists(self, key):
        return key in self.objects

    def list_prefix(self, prefix, limit=100):
        return sorted(k for k in self.objects if k.startswith(prefix))

    def delete(self, key):
        self.objects.pop(key, None)


@pytest.fixture
def fake_r2(monkeypatch):
    fake = FakeR2()
    monkeypatch.setattr(wk, "r2", fake)
    return fake


@pytest.fixture
def acuses(monkeypatch):
    grabados = []
    monkeypatch.setattr(wk.telegram, "send_message",
                        lambda chat_id, text, **kw: grabados.append((chat_id, text)) or {})
    return grabados


def test_texto_se_guarda_y_acusa(fake_r2, acuses):
    msg = {"chat": {"id": 1}, "message_id": 10, "text": " idea para el beat de la escala "}
    result = wk.route_update(msg)
    assert result == "nota_texto"
    (ruta,) = [k for k in fake_r2.objects if k.startswith("inbox/notas/")]
    assert ruta.endswith("--idea-para-el-beat-de-la.md")  # slug máx 6 palabras
    contenido = fake_r2.objects[ruta].decode()
    assert "created: 20" in contenido and "telegram_msg_id: 10" in contenido
    assert acuses[0][1].startswith("Guardado ✓")


def test_url_se_marcada_link(fake_r2, acuses):
    msg = {"chat": {"id": 1}, "message_id": 11, "text": "mira https://ejemplo.com/pepe"}
    assert wk.route_update(msg) == "link"
    assert acuses[0][1].startswith("URL guardada ✓")


def test_comando_status_cuenta(fake_r2, acuses):
    from bot import config
    fake_r2.put_bytes(config.INBOX_PREFIX + "notas/x.md", b"hola")
    fake_r2.put_bytes(config.INBOX_PREFIX + "notas/y.md", b"hola")
    msg = {"chat": {"id": 1}, "message_id": 12, "text": "/status"}
    assert wk.route_update(msg) == "status"
    assert "Inbox: 2" in acuses[0][1]


def test_comando_help(fake_r2, acuses):
    msg = {"chat": {"id": 1}, "message_id": 13, "text": "/help"}
    assert wk.route_update(msg) == "help"
    assert "/help" in acuses[0][1]


def test_audio_guarda_master_y_encola_asr(fake_r2, acuses, monkeypatch):
    monkeypatch.setattr(wk.telegram, "get_file_path", lambda fid: ("p/file.ogg", "ogg"))
    monkeypatch.setattr(wk.telegram, "download_bytes", lambda fid: b"OGGDATA")
    encolados = []
    monkeypatch.setattr(wk.asr.transcribe, "spawn",
                        lambda *a: encolados.append(a) or None)
    msg = {"chat": {"id": 1}, "message_id": 14, "voice": {"file_id": "f", "duration": 60}}
    assert wk.route_update(msg) == "audio"
    masters = [k for k in fake_r2.objects if k.startswith("inbox/audio/")]
    assert len(masters) == 1 and masters[0].endswith("--voz.ogg")
    assert fake_r2.objects[masters[0]] == b"OGGDATA"
    assert not [k for k in fake_r2.objects if k.endswith(".md")]
    assert len(encolados) == 1 and encolados[0][0] == masters[0]
    assert encolados[0][1] == 1 and encolados[0][2] == 14
    assert "transcribiendo" in acuses[0][1]


def test_foto_guarda_solo_master(fake_r2, acuses, monkeypatch):
    monkeypatch.setattr(wk.telegram, "get_file_path", lambda fid: ("p/file.jpg", "jpg"))
    monkeypatch.setattr(wk.telegram, "download_bytes", lambda fid: b"JPGDATA")
    msg = {"chat": {"id": 1}, "message_id": 15,
           "photo": [{"file_id": "a"}, {"file_id": "f"}]}
    assert wk.route_update(msg) == "foto"
    masters = [k for k in fake_r2.objects if k.startswith("inbox/fotos/")]
    assert len(masters) == 1 and masters[0].endswith("--foto.jpg")
    assert not [k for k in fake_r2.objects if k.endswith(".md")]
    assert "Foto guardada" in acuses[0][1]


def test_foto_ocr_encola_y_no_crea_nota(fake_r2, acuses, monkeypatch):
    monkeypatch.setattr(wk.telegram, "get_file_path", lambda fid: ("p/file.jpg", "jpg"))
    monkeypatch.setattr(wk.telegram, "download_bytes", lambda fid: b"JPGDATA")
    encolados = []
    monkeypatch.setattr(wk.ocr.transcribe_image, "spawn",
                        lambda *a: encolados.append(a) or None)
    msg = {"chat": {"id": 1}, "message_id": 16,
           "photo": [{"file_id": "f"}], "caption": "/ocr lee esto"}
    assert wk.route_update(msg) == "foto_ocr"
    assert [k for k in fake_r2.objects if k.startswith("inbox/fotos/")]
    assert not [k for k in fake_r2.objects if k.endswith(".md")]
    assert len(encolados) == 1 and encolados[0][0].endswith("--foto.jpg")
    assert encolados[0][-1] == "lee esto"
    assert "extrayendo texto" in acuses[0][1]


def test_doc_guarda_master(fake_r2, acuses, monkeypatch):
    monkeypatch.setattr(wk.telegram, "get_file_path", lambda fid: ("p/file.pdf", "pdf"))
    monkeypatch.setattr(wk.telegram, "download_bytes", lambda fid: b"PDFDATA")
    msg = {"chat": {"id": 1}, "message_id": 17,
           "document": {"file_id": "d", "file_name": "informe.pdf"}}
    assert wk.route_update(msg) == "doc"
    masters = [k for k in fake_r2.objects if k.startswith("inbox/docs/")]
    assert len(masters) == 1 and masters[0].endswith("--doc.pdf")
