"""F0 — webhook de Telegram en Modal (CPU 0.25 core).

M1: valida firma + allowlist, instancia F1 fire-and-forget y responde 200 YA.
"""

from __future__ import annotations

import json
import logging
import os

import modal
from fastapi import HTTPException, Request

from .app import app
from . import worker

image = (modal.Image.debian_slim(python_version="3.12")
         .pip_install("fastapi[standard]", "boto3", "python-dotenv", "requests"))
secrets = [modal.Secret.from_name("telegram-creds"),
           modal.Secret.from_name("telegram-webhook-secret")]

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)


@app.function(
    image=image,
    secrets=secrets,
    cpu=0.25,
    memory=256,
    enable_memory_snapshot=True,
    scaledown_window=5,
)
@modal.fastapi_endpoint(method="POST")
async def telegram_update(request: Request) -> dict:
    """Recibe un update, valida, responde 200 YA (<1 s, regla R1)."""
    # 1) firma secreta de Telegram — sin header válido → 403
    secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")
    if not secret or request.headers.get("x-telegram-bot-api-secret-token", "") != secret:
        raise HTTPException(status_code=403, detail="firma inválida")

    try:
        update = json.loads(await request.body())
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="body no es JSON") from None

    # 2) allowlist: solo tu user_id (PLAN §6.2)
    msg = update.get("message") or update.get("edited_message") or {}
    user_id = msg.get("from", {}).get("id")
    if user_id is None:
        raise HTTPException(status_code=400, detail="update sin usuario")
    owner_ids = {int(x.strip()) for x in os.environ.get("OWNER_IDS", "").split(",") if x.strip()}
    if user_id not in owner_ids:
        logger.warning("Update de usuario ajeno %s → 403", user_id)
        raise HTTPException(status_code=403, detail="usuario no permitido")

    # Encoche fire-and-forget: F1 baja el media y escribe la nota; ya respondimos.
    await worker.process.spawn.aio(update)
    return {"ok": True}
