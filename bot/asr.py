"""F2 — ASR vía Groq Whisper (sin GPU).

Decisión 2026-10-30 (reemplaza el F2 L4/Qwen3-ASR): sin cuota de GPU L4
disponible, el ASR local (Qwen3-ASR-1.7B, pesos ya en el Volume
`models-telegram-bot/asr/`) queda diferido hasta que haya L4. Ruta
primaria: Groq `whisper-large-v3-turbo` — $0.04/hora de audio, ~216x
tiempo real, multilingüe incl. español, endpoint OpenAI-compatible.
Límite free tier: 25 MB por archivo (una nota de voz ogg ≈ 1 MB/min,
sobra de sobra). `whisper.cpp` local queda como plan B solo si algún
día se exige privacidad total sin nube: más lento en CPU y sin ganancia
de calidad para este uso.

`transcribe()` mantiene la firma que F1 ya usa: baja el máster de R2,
transcribe, escribe la nota principal `...--voz.md` (mismo `ts` del
máster) y manda el acuse. La captura nunca espera al ASR (regla R1).
"""

from __future__ import annotations

import logging
import os
import subprocess

import modal
import requests

from . import config, r2, telegram
from .app import app
from .formats import frontmatter

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

GROQ_API_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
GROQ_MODELS_URL = "https://api.groq.com/openai/v1/models"
GROQ_MODEL = "whisper-large-v3-turbo"  # mejor precio/rendimiento multilingüe
GROQ_MAX_BYTES = 24 * 1024 * 1024  # margen bajo el límite free tier (25 MB)

asr_image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("ffmpeg")
    .pip_install("boto3", "python-dotenv", "requests")
)


def _maybe_compress(data: bytes) -> tuple[bytes, str]:
    """Si el máster supera el límite de Groq, bajar a FLAC 16 kHz mono."""
    if len(data) <= GROQ_MAX_BYTES:
        return data, "orig"
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error",
         "-i", "pipe:0", "-ar", "16000", "-ac", "1", "-map", "0:a",
         "-c:a", "flac", "pipe:1"],
        input=data, capture_output=True, timeout=300,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg falló: {proc.stderr.decode()[-300:]}")
    if len(proc.stdout) > GROQ_MAX_BYTES:
        raise RuntimeError(f"audio aún de {len(proc.stdout)} B tras comprimir; excede a Groq")
    return proc.stdout, "flac"


def _groq_transcribe(data: bytes, filename: str) -> tuple[str, str]:
    """POST a Groq → (texto, idioma_detectado). Lanza RuntimeError si falla."""
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY ausente (secret groq-creds no inyectado)")
    data, kind = _maybe_compress(data)
    base = filename.rsplit(".", 1)[0]
    if kind == "flac":
        filename = base + ".flac"
    elif filename.lower().endswith(".oga"):
        # Telegram manda voice notes .oga (= contenedor ogg/opus); Groq no
        # lista esa extensión pero sí ogg/opus → renombrar es seguro.
        filename = base + ".ogg"
    ctype = "audio/flac" if kind == "flac" else "application/octet-stream"
    logger.info("Groq ASR: %s (%d B, %s)", filename, len(data), kind)
    resp = requests.post(
        GROQ_API_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        files={"file": (filename, data, ctype)},
        data={"model": GROQ_MODEL, "response_format": "verbose_json",
              "temperature": "0"},
        timeout=300,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Groq {resp.status_code}: {resp.text[:300]}")
    payload = resp.json()
    texto = (payload.get("text") or "").strip()
    idioma = payload.get("language") or "desconocido"
    return texto, idioma


def _run_transcription(master_key: str, chat_id: int, msg_id: int,
                       ts_name: str, created_iso: str) -> str:
    """Lógica plana (testeable sin Modal): transcribe y escribe `--voz.md`."""
    data = r2.get_bytes(master_key)
    texto, idioma = _groq_transcribe(data, master_key.rsplit("/", 1)[-1])
    logger.info("ASR %s: %d chars, idioma=%s", master_key, len(texto), idioma)

    carpeta = master_key.rsplit("/", 1)[0]
    note_key = f"{carpeta}/{ts_name}--voz.md"
    embed = master_key.rsplit("/", 1)[-1]
    cuerpo_trans = texto if texto else "_(sin habla detectable)_"
    contenido = (
        frontmatter(
            created=created_iso,
            titulo=f"voz {ts_name}",
            tipo_captura="audio",
            ruta=note_key,
            telegram_msg_id=msg_id,
        )
        + f"\n\n![[{embed}]]\n\n## Transcripción (fiel)\n\n"
        + f"_Idioma detectado: {idioma}_\n\n{cuerpo_trans}\n"
    )
    r2.put_bytes(note_key, contenido.encode("utf-8"), content_type="text/markdown")

    try:
        preview = (texto[:200] + "…") if len(texto) > 200 else texto
        telegram.send_message(
            chat_id,
            f"📝 Transcripción lista ✓ ({idioma})\n`{note_key}`\n\n{preview or '_(vacía)_'}",
        )
    except Exception:  # noqa: BLE001 — la nota ya quedó, el acuse no la tumba
        logger.exception("acuse de transcripción falló")
    return note_key


@app.function(
    image=asr_image,
    secrets=[modal.Secret.from_name("r2-creds"),
             modal.Secret.from_name("telegram-creds"),
             modal.Secret.from_name("groq-creds")],
    cpu=0.5,
    memory=512,
    timeout=300,
    retries=1,
    scaledown_window=10,
)
def transcribe(master_key: str, chat_id: int, msg_id: int,
               ts_name: str, created_iso: str) -> str:
    """Transcribe un máster de `inbox/audio/` y escribe su `--voz.md`.

    `ts_name`/`created_iso` son los del instante de captura (F1) para que
    la nota comparta timestamp con el máster.
    """
    return _run_transcription(master_key, chat_id, msg_id, ts_name, created_iso)


@app.function(
    image=asr_image,  # mismo que transcribe: el módulo importa requests arriba
    secrets=[modal.Secret.from_name("groq-creds")],
    cpu=0.25,
    timeout=60,
)
def check() -> dict:
    """Valida la GROQ_API_KEY contra la API (sin gastar transcripción)."""
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        return {"ok": False, "error": "GROQ_API_KEY ausente"}
    resp = requests.get(
        GROQ_MODELS_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=30,
    )
    if resp.status_code != 200:
        return {"ok": False, "error": f"Groq {resp.status_code}: {resp.text[:200]}"}
    modelos = [m.get("id") for m in resp.json().get("data", [])]
    resultado = {"ok": GROQ_MODEL in modelos, "asr_model": GROQ_MODEL,
                 "asr_disponible": GROQ_MODEL in modelos,
                 "modelos_vistos": len(modelos)}
    print(f"GROQ_CHECK {resultado}", flush=True)
    return resultado
