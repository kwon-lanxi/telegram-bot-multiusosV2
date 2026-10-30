"""F1 — worker del dispatch (CPU 1 core).

M1/M2 (PLAN.md §5.1):
  nota_texto → inbox/notas/YYYY-MM-DD_HH-MM-SS--{slug}.md + acuse "Guardado ✓"
  link       → nota con URL cruda + acuse "URL guardada ✓ (descarga en v1)"
  foto       → SOLO máster byte a byte, sin nota (salvo caption /ocr explícito)
  audio/voz  → SOLO máster byte a byte (transcripción en M3 crea la nota)
  doc        → SOLO máster byte a byte (procesamiento en v1)
  /status    → últimos 3 items + contador del inbox
  /help      → capacidades v0.1
  /ocr       → explica uso (foto con caption /ocr)

Rutas planas (`route_update`/`process_*`) sin modal para poder testear con moto/monkeypatch;
`@app.function process()` solo encola y delega.
"""

from __future__ import annotations

import logging
import os
import re

import modal

from . import asr, config, ocr, r2, telegram
from .app import app
from .formats import filename_ts, iso_7digits, nota_texto, now_utc

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)


def _acuse(chat_id: int, text: str) -> None:
    try:
        telegram.send_message(chat_id, text)
    except Exception:  # noqa: BLE001 — el acuse no debe tumbar el flujo
        logger.exception("acuse falló")


# --- rutas planas -------------------------------------------------------------


def process_text(msg: dict) -> str:
    chat_id = msg["chat"]["id"]
    text = (msg.get("text") or "").strip()
    if not text:
        _acuse(chat_id, "⚠️ Mensaje sin texto; no guardo nada aún.")
        return "empty"

    url = bool(re.search(r"https?://|www\.|t\.me/", text, re.I))
    ruta, contenido = nota_texto(moment=now_utc(), body=text, msg_id=msg["message_id"])
    r2.put_bytes(ruta, contenido.encode("utf-8"), content_type="text/markdown")
    _acuse(chat_id, ("URL guardada ✓ (descarga en v1)" if url else "Guardado ✓") + f"\n`{ruta}`")
    return "link" if url else "nota_texto"


def _content_type(ext: str) -> str:
    return {
        "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
        "webp": "image/webp", "heic": "image/heic",
        "ogg": "audio/ogg", "oga": "audio/ogg", "mp3": "audio/mpeg",
        "m4a": "audio/mp4", "wav": "audio/wav", "opus": "audio/opus",
        "pdf": "application/pdf",
    }.get(ext.lower(), "application/octet-stream")


def process_media(msg: dict) -> str:
    chat_id = msg["chat"]["id"]
    momento = now_utc()
    ts = filename_ts(momento)

    if msg.get("photo"):
        file_ref = msg["photo"][-1]  # la última resolución es la mejor
        info = telegram.get_file_path(file_ref["file_id"])
        ext = (info[1] if info else "jpg")
        if ext == "bin":
            ext = "jpg"
        master_key = f"{config.INBOX_PREFIX}fotos/{ts}--foto.{ext}"
        r2.put_bytes(master_key, telegram.download_bytes(file_ref["file_id"]),
                      content_type=_content_type(ext))
        # Solo con /ocr explícito en el caption se extrae el texto (F2-OCR).
        caption = (msg.get("caption") or "").strip()
        if caption.lower().startswith("/ocr"):
            resto = caption[4:].strip()
            try:
                ocr.transcribe_image.spawn(master_key, chat_id, msg["message_id"],
                                           ts, iso_7digits(momento), resto)
                _acuse(chat_id, f"Foto guardada ✓, extrayendo texto…\n`{master_key}`")
            except Exception:  # noqa: BLE001 — el máster ya quedó
                logger.exception("encolar OCR falló")
                _acuse(chat_id, f"Foto guardada ✓ (OCR pendiente)\n`{master_key}`")
            return "foto_ocr"
        _acuse(chat_id, f"Foto guardada ✓\n`{master_key}`")
        return "foto"

    if msg.get("voice") or msg.get("audio"):
        file_ref = msg.get("voice") or msg.get("audio")
        info = telegram.get_file_path(file_ref["file_id"])
        ext = (info[1] if info else "ogg")
        if ext == "bin":
            ext = "ogg"
        master_key = f"{config.INBOX_PREFIX}audio/{ts}--voz.{ext}"
        try:
            data = telegram.download_bytes(file_ref["file_id"])
        except Exception:  # noqa: BLE001 — no perder el update sin acuse claro
            logger.exception("descarga de audio falló")
            _acuse(chat_id, "⚠️ No pude bajar el audio de Telegram. Reenvíalo.")
            return "audio_error"
        r2.put_bytes(master_key, data, content_type=_content_type(ext))
        try:
            asr.transcribe.spawn(master_key, chat_id, msg["message_id"],
                                 ts, iso_7digits(momento))
            _acuse(chat_id, f"🎙️ Audio guardado ✓, transcribiendo…\n`{master_key}`")
        except Exception:  # noqa: BLE001 — el máster ya quedó; avisar reintento
            logger.exception("encolar transcripción falló")
            _acuse(chat_id, f"🎙️ Audio guardado ✓ (transcripción pendiente)\n`{master_key}`")
        return "audio"

    if msg.get("document"):
        file_ref = msg["document"]
        info = telegram.get_file_path(file_ref["file_id"])
        ext = (info[1] if info else "bin")
        nombre = file_ref.get("file_name", "")
        if "." in nombre:
            ext = nombre.rsplit(".", 1)[-1].lower()
        master_key = f"{config.INBOX_PREFIX}docs/{ts}--doc.{ext}"
        try:
            data = telegram.download_bytes(file_ref["file_id"])
        except Exception:  # noqa: BLE001
            logger.exception("descarga de documento falló")
            _acuse(chat_id, "⚠️ No pude bajar el documento de Telegram. Reenvíalo.")
            return "doc_error"
        r2.put_bytes(master_key, data, content_type=_content_type(ext))
        _acuse(chat_id, f"📄 Documento guardado ✓\n`{master_key}`")
        return "doc"

    return "sin_ruta"


def process_command(msg: dict, texto: str) -> str:
    chat_id = msg["chat"]["id"]

    if texto.startswith("/status"):
        keys = r2.list_prefix(config.INBOX_PREFIX, limit=1000)
        notas = [k for k in keys if k.endswith(".md")]
        ultimas = "\n".join(f"- `{k}`" for k in notas[-3:]) or "- (inbox vacío)"
        _acuse(chat_id, f"📥 Inbox: {len(notas)} nota(s).\n{ultimas}")
        return "status"

    if texto.startswith("/ocr"):
        _acuse(chat_id,
               "Para OCR: manda la foto con `/ocr` en el caption.\n"
               "Sin `/ocr` la foto se guarda sola, sin nota.")
        return "ocr_help"

    if texto.startswith("/help"):
        _acuse(chat_id,
               "Archivista v0.1 — todo entra a la incubadora `inbox/`:\n"
               "• Texto → nota `inbox/notas/`\n"
               "• URL en el texto → guardada cruda (descarga en v1)\n"
               "• Foto → solo máster `inbox/fotos/` (nota solo con `/ocr` en caption)\n"
               "• Audio/voz → máster + transcripción automática a su `--voz.md`\n"
               "• Doc → solo máster `inbox/docs/`\n"
               "• /status · /help · /ocr")
        return "help"

    comando = texto.split()[0]
    _acuse(chat_id, f"Comando `{comando}` no existe hoy. `/help` para ver lo disponible.")
    return "desconocido"


def route_update(msg: dict) -> str:
    texto = (msg.get("text") or "").strip()
    if texto.startswith("/"):
        return process_command(msg, texto)
    if msg.get("photo") or msg.get("voice") or msg.get("audio") or msg.get("document"):
        return process_media(msg)
    return process_text(msg)


# --- envoltura Modal (deploy) -------------------------------------------------


@app.function(
    image=(modal.Image.debian_slim(python_version="3.12")
           .pip_install("boto3", "python-dotenv", "requests")),
    secrets=[modal.Secret.from_name("r2-creds"),
             modal.Secret.from_name("telegram-creds")],
    cpu=1.0,
    memory=512,
    enable_memory_snapshot=True,
    scaledown_window=10,
)
def process(update: dict) -> str:
    msg = update.get("message") or {}
    if not msg:
        return "sin mensaje"
    return route_update(msg)
