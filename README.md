# Bot de Telegram multiusos — Archivista de vida

Bot personal de Telegram orientado a **capturar, organizar y recuperar memoria**. La bóveda de Obsidian, almacenada en Cloudflare R2, será el archivo persistente; Modal ejecutará el webhook y los trabajos de procesamiento bajo demanda.

> **Estado:** diseño y decisiones en curso. Este repositorio contiene actualmente documentación; el bot todavía no está implementado.

## Documento de diseño

El plan de construcción (arquitectura v0.1, integraciones e hitos M0–M5) está en [PLAN.md](PLAN.md).

La arquitectura propuesta, el registro de decisiones, los modelos, los flujos por plataforma y el roadmap están en [BOT.md](BOT.md). Ese documento es la especificación viva del proyecto; actualizarlo conforme se tomen decisiones o se construyan features.

Los flujos de trabajo por intención, las puertas de decisión y el diseño del flujo de recuperación están en [FLUJOS.md](FLUJOS.md).

## Qué se está diseñando

- Captura de enlaces de YouTube, TikTok e Instagram: notas a partir de subtítulos o ASR, archivo opcional de video en R2 y modo de envío al grupo privado de Telegram.
- Archivo de publicaciones de X/Twitter y Pinterest, además de páginas web, Substack y Wikipedia.
- Captura de audio con transcripción obligatoria y clasificación de intención antes de decidir el destino. La retención del archivo se decide por modo: se conservan el resumen diario hablado y los tarareos, y se descarta el audio de un dictado.
- Ocho familias de nota (diario, estudio, semilla, referencia, reflexión, registro, artefacto y log), cada una con su plantilla y su consulta característica; sólo el diario y los registros tienen cadencia.
- OCR de imágenes/documentos, TTS y búsqueda multimodal como capacidades previstas.
- Soporte de procesamiento en coreano, inglés y español, conservando el idioma original y la procedencia de los datos.
- Series de hábitos derivadas del resumen diario (una línea por día, con la fuente marcada como dicha, medida o inferida) y espejo de listas de tareas hacia una app externa, sin duplicar el estado.
- Acceso a las notas mediante capas de modelo: reglas y búsqueda literal primero, modelos pequeños locales para clasificar y extraer, y un modelo mayor sólo para redactar y responder preguntas sobre la bóveda.

## Arquitectura prevista

1. **Telegram webhook en Modal (CPU):** valida y encola actualizaciones para responder rápidamente.
2. **Workers CPU:** extracción de contenido, coordinación, acceso a R2 y llamadas a APIs.
3. **Workers GPU L4:** inferencia local para tareas como ASR, OCR, embeddings y TTS, según el flujo.
4. **R2:** fuente de verdad para notas Obsidian y medios que el usuario decida archivar.
5. **Índice de búsqueda:** componente auxiliar; no sustituye a R2 como archivo de notas y medios.

La documentación distingue proveedores de decisión (Jev/TypeSafe o Liquid d1), transcripción (Qwen3-ASR local y Groq como alternativa opcional) y generación de notas mediante un endpoint compatible con OpenAI SDK. Los proveedores concretos y varias decisiones de implementación siguen pendientes.

## Primeros flujos de captura

- **URL de video sola:** crear una nota; preferir subtítulos disponibles y recurrir a ASR si no hay subtítulos.
- **`!URL` de video:** crear nota y archivar también el video en R2.
- **`!!URL` de video:** enviar solo el video al grupo privado de Telegram, sin nota ni copia a R2.
- **Audio:** transcribir y clasificar la intención; sólo las notas se archivan como nota. Los recordatorios siguen el flujo Jev → LLM → QStash + Google Calendar y generan un log estructurado en Obsidian, sin guardar el audio.

Los marcadores son prefijos reales delante de la URL; las llaves usadas en ejemplos de `BOT.md` sólo indican un marcador de posición.

## Seguridad y privacidad

- No guardar tokens, claves API ni cookies en el repositorio. Se prevé gestionarlos como secretos de Modal.
- El uso de un ASR o clasificador alojado externamente puede enviar audio o transcripciones fuera de Modal; la ruta externa deberá ser explícita y configurable.
- Los contenidos extraídos de enlaces, OCR y transcripciones se tratan como datos no confiables, no como instrucciones internas del bot.
- Respetar permisos de acceso y las condiciones de las plataformas fuente.

## Estado y siguientes pasos

El roadmap detallado está al final de [BOT.md](BOT.md); el plan de construcción, en [PLAN.md](PLAN.md).

**M0 — LISTO (2026-10-29).** Repo andamiado, smoke R2 local+remoto, Modal Secrets creados.

**M1/M2-media — LISTO (2026-10-30).** Webhook F0 + worker F1 desplegados en Modal (app `tg-bot`, F0: cpu 0.25 / mem 256 / SDW 5; F1: cpu 1.0 / mem 512 / SDW 10): texto/link → `inbox/notas/` con frontmatter completo; foto → **solo máster** `inbox/fotos/` (nota solo con `/ocr` en el caption); voz/audio → máster `inbox/audio/`; doc → máster `inbox/docs/`; `/status`, `/help`, `/ocr`. Webhook registrada en Telegram con `secret_token`; 403×2 y e2e verificados, sin crash-loop.

**M3 — LISTO (2026-10-30).** ASR vía Groq `whisper-large-v3-turbo` (F2 CPU, secret `groq-creds`): voz → `--voz.md` con transcripción fiel + idioma detectado, probado con nota de voz real en español. Qwen3-ASR local diferido hasta tener cuota L4.

**OCR — LISTO (2026-10-30).** F2-OCR vía Groq vision (CPU, mismo `groq-creds`): foto con `/ocr` en el caption → `--foto.md` con texto extraído; sin `/ocr` la foto queda solo como máster. Modelos locales diferidos hasta L4. Sigue **M4** (titler).

Los recordatorios con QStash y Calendar están diseñados, pero aún faltan OAuth, secretos, schemas, código y pruebas.
