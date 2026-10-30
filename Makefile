# Bot archivista — comandos de desarrollo (PLAN.md §10)

.PHONY: sync smoke test deploy-webhook status

sync:            ## instala dependencias con uv
	uv sync

smoke:           ## prueba write/read/delete contra bucket-prueba
	python -m bot.smoke

test:            ## pytest local (r2 client con moto mock)
	uv run pytest -q

deploy-webhook:  ## despliega F0 a Modal y devuelve la URL
	uv run modal deploy bot/webhook.py

status:          ## lista el inbox en R2
	uv run python -c "from bot import r2, config; [print(k) for k in r2.list_prefix(config.INBOX_PREFIX, 60)]"
