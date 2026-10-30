"""App compartida — F0 (webhook) y F1 (worker) en la MISMA App de Modal.

Modal no permite encocher (spawn) un Core Function de otra App desde un
web-endpoint: el Function object no se hidrata y lanza ExecutionError en
cada request (crash looping visto el 2026-10-29). One App, dos funciones.
"""

import modal

app = modal.App("tg-bot")
