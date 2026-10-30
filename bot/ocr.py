"""F2-OCR — extracción de texto de fotos vía Groq vision (sin GPU).

Decisión 2026-10-30: los modelos OCR locales del Volume (`Xiaomi-OCR-0`,
`GLM-OCR`) quedan diferidos igual que el ASR local — no hay cuota L4.
Ruta primaria: Groq chat-completions con modelo multimodal (imagen por
base64 data-URL, límite 20 MB; las fotos de Telegram llegan de ~KB a
pocos MB). Cadena de modelos con fallback: si el primero no existe o fue
dado de baja, se intenta el siguiente y se registra cuál funcionó.

`transcribe()` mantiene la firma de la familia F2: baja el máster de R2,
extrae el texto, escribe la nota `...--foto.md` (mismo `ts` del máster)
y manda el acuse. La captura nunca espera al OCR (regla R1).
"""

from __future__ import annotations

import base64
import logging
import os

import modal
import requests

from . import config, r2, telegram
from .app import app
from .formats import frontmatter

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
# Ordenados por preferencia; el runtime usa el primero que acepte el request.
OCR_MODELS = (
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "meta-llama/llama-4-maverick-17b-128e-instruct",
)
OCR_PROMPT = (
    "Transcribe todo el texto visible en la imagen de forma fiel y literal, "
    "manteniendo el orden de lectura. No describas la imagen, no añadas "
    "comentarios ni formato extra: solo el texto. Separa secciones con "
    "saltos de línea. Si no hay texto legible, responde exactamente: "
    "(sin texto detectable)"
)
OCR_MAX_TOKENS = 2048

_MIME = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
         "webp": "image/webp"}

ocr_image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("boto3", "python-dotenv", "requests")
)


def _groq_ocr(data: bytes, mime: str) -> tuple[str, str]:
    """POST a chat-completions con fallback de modelo → (texto, modelo_usado)."""
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY ausente (secret groq-creds no inyectado)")
    b64 = base64.b64encode(data).decode("ascii")
    ultimo_error = "sin intentos"
    for model in OCR_MODELS:
        resp = requests.post(
            GROQ_CHAT_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "temperature": 0,
                "max_completion_tokens": OCR_MAX_TOKENS,
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": OCR_PROMPT},
                        {"type": "image_url",
                         "image_url": {"url": f"data:{mime};base64,{b64}"}},
                    ],
                }],
            },
            timeout=300,
        )
        if resp.status_code == 200:
            texto = (resp.json()["choices"][0]["message"]["content"] or "").strip()
            logger.info("OCR ok con %s (%d chars)", model, len(texto))
            return texto, model
        body = resp.text[:200]
        logger.warning("OCR %s → %s: %s", model, resp.status_code, body)
        ultimo_error = f"{model}: {resp.status_code} {body}"
        if resp.status_code not in (400, 404):
            break  # error no recuperable (auth, límite, red) → no reintentar modelos
    raise RuntimeError(f"Groq OCR falló: {ultimo_error}")


def _run_ocr(master_key: str, chat_id: int, msg_id: int,
             ts_name: str, created_iso: str, caption: str = "") -> str:
    """Lógica plana (testeable sin Modal): extrae texto y escribe `--foto.md`."""
    ext = master_key.rsplit(".", 1)[-1].lower() if "." in master_key else "jpg"
    mime = _MIME.get(ext, "image/jpeg")
    data = r2.get_bytes(master_key)
    if len(data) > 20 * 1024 * 1024:
        raise RuntimeError(f"foto de {len(data)} B excede el límite Groq (20 MB)")
    texto, modelo = _groq_ocr(data, mime)
    logger.info("OCR %s: %d chars con %s", master_key, len(texto), modelo)

    carpeta = master_key.rsplit("/", 1)[0]
    note_key = f"{carpeta}/{ts_name}--foto.md"
    embed = master_key.rsplit("/", 1)[-1]
    cuerpo = texto if texto else "_(sin texto detectable)_"
    extra = f"\n\n## Caption\n\n{caption}\n" if caption else ""
    contenido = (
        frontmatter(
            created=created_iso,
            titulo=f"foto {ts_name}",
            tipo_captura="foto",
            ruta=note_key,
            telegram_msg_id=msg_id,
        )
        + f"\n\n![[{embed}]]\n\n## Texto extraído (OCR)\n\n"
        + f"_Modelo: {modelo}_\n\n{cuerpo}\n{extra}"
    )
    r2.put_bytes(note_key, contenido.encode("utf-8"), content_type="text/markdown")

    try:
        preview = (texto[:200] + "…") if len(texto) > 200 else texto
        telegram.send_message(
            chat_id,
            f"🔍 OCR listo ✓\n`{note_key}`\n\n{preview or '_(vacío)_'}",
        )
    except Exception:  # noqa: BLE001 — la nota ya quedó, el acuse no la tumba
        logger.exception("acuse de OCR falló")
    return note_key


@app.function(
    image=ocr_image,
    secrets=[modal.Secret.from_name("r2-creds"),
             modal.Secret.from_name("telegram-creds"),
             modal.Secret.from_name("groq-creds")],
    cpu=0.5,
    memory=512,
    timeout=300,
    retries=1,
    scaledown_window=10,
)
def transcribe_image(master_key: str, chat_id: int, msg_id: int,
                     ts_name: str, created_iso: str, caption: str = "") -> str:
    """Extrae el texto de un máster de `inbox/fotos/` y escribe su `--foto.md`."""
    return _run_ocr(master_key, chat_id, msg_id, ts_name, created_iso, caption)
