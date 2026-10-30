"""Crea los Modal Secrets v0.1 desde el .env local, sin imprimir valores.

Crea (o recrea con --force):
  r2-creds                 R2_ENDPOINT, R2_BUCKET, R2_ACCESS_KEY, R2_SECRET_KEY
  telegram-creds           TELEGRAM_TOKEN, OWNER_IDS, ARCHIVE_CHAT_ID, TZ_NAME
  telegram-webhook-secret  TELEGRAM_WEBHOOK_SECRET (generado aleatorio la 1ª vez,
                           persistido en .env local para usos futuros de setWebhook)
  groq-creds               GROQ_API_KEY (ASR whisper-large-v3-turbo, M3)

Uso:  uv run python scripts/create_modal_secrets.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from dotenv import dotenv_values

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"

GRUPOS: dict[str, list[str]] = {
    "r2-creds": ["R2_ENDPOINT", "R2_BUCKET", "R2_ACCESS_KEY", "R2_SECRET_KEY"],
    "telegram-creds": ["TELEGRAM_TOKEN", "OWNER_IDS", "ARCHIVE_CHAT_ID", "TZ_NAME"],
    "telegram-webhook-secret": ["TELEGRAM_WEBHOOK_SECRET"],
    "groq-creds": ["GROQ_API_KEY"],
}


def main() -> int:
    values = {k: (v or "") for k, v in dotenv_values(ENV_FILE).items()}

    # Generar el webhook secret si aún no existe, y fijarlo en .env (local).
    if not values.get("TELEGRAM_WEBHOOK_SECRET"):
        nuevo = __import__("secrets").token_hex(32)
        texto = ENV_FILE.read_text(encoding="utf-8")
        if not texto.endswith("\n"):
            texto += "\n"
        texto += f"TELEGRAM_WEBHOOK_SECRET={nuevo}\n"
        ENV_FILE.write_text(texto, encoding="utf-8")
        values["TELEGRAM_WEBHOOK_SECRET"] = nuevo
        print("  + TELEGRAM_WEBHOOK_SECRET generado y guardado en .env (valor oculto)")

    exito = 0
    for nombre, claves in GRUPOS.items():
        pares: dict[str, str] = {}
        for clave in claves:
            valor = values.get(clave, "").strip()
            if valor:
                pares[clave] = valor
        if not pares:
            print(f"  [OMITIDO] secret {nombre}: sin variables disponibles en .env")
            exito = 1
            continue
        args = ["uv", "run", "modal", "secret", "create", nombre, "--force"]
        for clave, valor in pares.items():
            args.append(f"{clave}={valor}")
        resultado = subprocess.run(args, capture_output=True, text=True)
        nombres = ", ".join(pares)
        if resultado.returncode == 0:
            print(f"  [OK] modal secret {nombre} ({nombres}) creado")
        else:
            salida = (resultado.stderr or resultado.stdout).strip().splitlines()
            print(f"  [FALLO] modal secret {nombre} falló: {salida[-1] if salida else 'sin salida'}")
            exito = 1
    return exito


if __name__ == "__main__":
    sys.exit(main())
