"""Configuración del bot.

Reglas del repo (PLAN.md §4.2): ninguna clave real vive en el repo. Local =>
se lee el `.env` de la raíz SOLO para tests/smoke en tu máquina; en Modal el
mismo juego de variables llega vía Modal Secrets (r2-creds, telegram-creds,
telegram-webhook-secret).
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Carga el .env de la raíz del proyecto si existe (local). No-op en Modal,
# donde las variables ya vienen de los Secrets.
_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
if _ENV_PATH.exists():
    load_dotenv(_ENV_PATH, override=False)


def _int_list(raw: str) -> list[int]:
    """`"12345"` o `"12345, 67890"` -> [12345, 67890]. Ignora vacíos."""
    return [int(part.strip()) for part in raw.split(",") if part.strip()]


# --- Telegram ---------------------------------------------------------------
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
OWNER_IDS = _int_list(os.environ.get("OWNER_IDS", ""))
ARCHIVE_CHAT_ID = int(os.environ.get("ARCHIVE_CHAT_ID", "0") or 0)
# Solo con Bot API local; None => api.telegram.org estándar (límite getFile ~20 MB).
BOT_API_BASE = os.environ.get("BOT_API_BASE") or None

# --- Cloudflare R2 ----------------------------------------------------------
R2_ENDPOINT = os.environ.get("R2_ENDPOINT", "")
R2_BUCKET = os.environ.get("R2_BUCKET", "bucket-prueba")
R2_ACCESS_KEY = os.environ.get("R2_ACCESS_KEY")
R2_SECRET_KEY = os.environ.get("R2_SECRET_KEY")

# Prefijos del bucket (PLAN.md §2). Los tratar arbitrarios quedan para v1;
# v0.1 solo escribe bajo inbox/.
INBOX_PREFIX = "inbox/"

# --- Comportamiento ---------------------------------------------------------
TZ_NAME = os.environ.get("TZ_NAME", "UTC")
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")


def missing_credentials() -> list[str]:
    """Nombres de variables requeridas que faltan (para fail-fast con mensajes claros)."""
    faltantes: list[str] = []
    if not TELEGRAM_TOKEN:
        faltantes.append("TELEGRAM_TOKEN")
    if not OWNER_IDS:
        faltantes.append("OWNER_IDS")
    if not R2_ENDPOINT:
        faltantes.append("R2_ENDPOINT")
    if not R2_ACCESS_KEY:
        faltantes.append("R2_ACCESS_KEY")
    if not R2_SECRET_KEY:
        faltantes.append("R2_SECRET_KEY")
    return faltantes
