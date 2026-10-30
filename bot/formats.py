"""Generador de notas Markdown + frontmatter (PLAN.md §5.2).

Regla dura: el número de la fecha va DOS veces — en el nombre del archivo
(`YYYY-MM-DD_HH-MM-SS--{slug}.md`) y en el frontmatter (`created:`
formato exacto del usuario: `2026-10-08T23:39:00.0000000Z`, UTC, 7 dígitos
fraccionarios). Ambos derivan del MISMO instante UTC para que el tro no diverja.
"""

from __future__ import annotations

import datetime as dt
import re
import unicodedata

from . import config

FRONTMATTER_FIELDS = (
    "created",
    "titulo",
    "tipo_captura",
    "canal",
    "telegram_msg_id",
    "estado_vital",
    "ruta",
    "traza",
)


def now_utc() -> dt.datetime:
    """Instante actual en UTC (timezone-aware)."""
    return dt.datetime.now(dt.timezone.utc)


def iso_7digits(moment: dt.datetime) -> str:
    """`YYYY-MM-DDTHH:MM:SS.0000000Z` — 7 dígitos fraccionarios, como pidió el usuario.

    `%f` produce 6 dígitos; se les concatena un `0` fijo = 7.
    """
    return moment.strftime("%Y-%m-%dT%H:%M:%S.%f") + "0Z"


def filename_ts(moment: dt.datetime) -> str:
    """`YYYY-MM-DD_HH-MM-SS` para el nombre del archivo (ya es UTC => orden cronológico)."""
    return moment.strftime("%Y-%m-%d_%H-%M-%S")


def slugify(title: str, max_words: int = 8) -> str:
    """Título → slug ASCII lowercase para nombre de archivo."""
    text = unicodedata.normalize("NFKD", title)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text)
    text = text.strip("-").lower()
    words = text.split("-")
    return "-".join(words[:max_words]) if words else "nota"


def frontmatter(
        *,
        created: str,
        titulo: str,
        tipo_captura: str,
        ruta: str,
        telegram_msg_id: int = 0,
        estado_vital: str = "incubadora",
        traza: list[str] | None = None,
        canal: str = "telegram",
) -> str:
    """YAML mínimo común a todas las capturas (PLAN.md §5.2)."""
    traza = traza or ["W1"]
    lines = [
        "---",
        f"created: {created}",
        f"titulo: {titulo}",
        f"tipo_captura: {tipo_captura}",
        f"canal: {canal}",
        f"telegram_msg_id: {telegram_msg_id}",
        f"estado_vital: {estado_vital}",
        f"ruta: {ruta}",
        f"traza: [{', '.join(traza)}]",
        "---",
    ]
    return "\n".join(lines)


def nota_texto(*, moment: dt.datetime, body: str, msg_id: int = 0) -> tuple[str, str]:
    """Nota de texto. Devuelve (key_ruta, contenido_md).

    El slug provisional son las primeras palabras del cuerpo; el titler (F7)
    lo reemplazará en M4 con rename R2 + update de `titulo:`/`ruta:`.
    """
    provisional = body.strip().splitlines()[0] if body.strip() else "nota"
    slug = slugify(provisional, max_words=6) or "nota"
    created = iso_7digits(moment)
    ruta = f"{'inbox/notas/'}{filename_ts(moment)}--{slug}.md"
    content = (
            frontmatter(
                created=created,
                titulo=provisional[:80],
                tipo_captura="texto",
                ruta=ruta,
                telegram_msg_id=msg_id,
            )
            + "\n\n"
            + body.rstrip()
            + "\n"
    )
    return ruta, content


def nota_media(
        *,
        moment: dt.datetime,
        tipo: str,  # "foto" | "audio" | "document"
        master_key: str,
        embed_name: str | None = None,
        msg_id: int = 0,
        extra_body: str = "",
) -> tuple[str, str]:
    """Nota principal de una captura con media (PLAN.md §2).

    El media va ARRIBA del cuerpo (primera línea, sintaxis Obsidian
    `![[nombre]]`) para que al abrir la nota se vea el audio/foto primero.
    Ruta del máster queda doblemente ligada: `ruta:` en frontmatter + embed por nombre.
    """
    sufijo = {"foto": "foto", "audio": "voz", "document": "doc"}[tipo]
    embed = embed_name or master_key.rsplit("/", 1)[-1]
    created = iso_7digits(moment)
    folder = {"foto": "fotos", "audio": "audio", "document": "docs"}[tipo]
    ruta = f"{config.INBOX_PREFIX}{folder}/{filename_ts(moment)}--{sufijo}.md"
    content = (
            frontmatter(
                created=created,
                titulo=embed.removesuffix(".md"),  # provisional: lo cambia el titler
                tipo_captura=tipo,
                ruta=ruta,
                telegram_msg_id=msg_id,
            )
            + "\n\n"
            + f"![[{embed}]]"
            + ("\n\n" + extra_body.rstrip() if extra_body else "")
            + "\n"
    )
    return ruta, content
