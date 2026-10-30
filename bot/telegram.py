"""Helpers de la Bot API de Telegram (v0.1: solo lo que F0/F1 necesita)."""

from __future__ import annotations

import logging
from functools import lru_cache

import requests

from . import config

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def api_base() -> str:
    return (config.BOT_API_BASE or "https://api.telegram.org").rstrip("/") + f"/bot{config.TELEGRAM_TOKEN}"


def api_call(method: str, **params: object) -> dict:
    """POST estándar a la Bot API; lanza si `ok=false`."""
    response = requests.post(f"{api_base()}/{method}", json=params, timeout=30)
    response.raise_for_status()
    payload = response.json()
    if not payload.get("ok"):
        raise RuntimeError(f"Telegram {method} falló: {payload.get('description')}")
    return payload["result"]


def file_path(file_id: str) -> str:
    """`getFile` → ruta relativa para descargar bytes del media."""
    return api_call("getFile", file_id=file_id)["file_path"]


def get_file_path(file_id: str) -> tuple[str, str] | None:
    """(ruta, extensión) o None si el archivo se pasa de los límites del API."""
    info = api_call("getFile", file_id=file_id)
    path = info.get("file_path") or ""
    if not path:
        return None
    if info.get("file_size", 0) > 20 * 1024 * 1024 and not config.BOT_API_BASE:
        logger.warning("Archivo de %d B excede el límite del Bot API estándar", info["file_size"])
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else "bin"
    return path, ext


def file_base_url() -> str:
    base = config.BOT_API_BASE or "https://api.telegram.org"
    return f"{base.rstrip('/')}/file/bot{config.TELEGRAM_TOKEN}"


def download_bytes(file_id: str) -> bytes:
    """Descarga los bytes del media (máster tal cual llegan a Telegram)."""
    path = file_path(file_id)
    response = requests.get(f"{file_base_url()}/{path}", timeout=60)
    response.raise_for_status()
    return response.content


def send_message(chat_id: int, text: str, **params: object) -> dict:
    return api_call("sendMessage", chat_id=chat_id, text=text, **params)
