# Bot de Telegram multiusos — Archivista de vida

Bot personal de Telegram orientado a **capturar, organizar y recuperar memoria**. La bóveda de Obsidian, almacenada en Cloudflare R2, será el archivo persistente; Modal ejecutará el webhook y los trabajos de procesamiento bajo demanda.

> **Estado:** diseño y decisiones en curso. Este repositorio contiene actualmente documentación; el bot todavía no está implementado.

## Documento de diseño

La arquitectura propuesta, el registro de decisiones, los modelos, los flujos por plataforma y el roadmap están en [BOT.md](BOT.md). Ese documento es la especificación viva del proyecto; actualizarlo conforme se tomen decisiones o se construyan features.

## Qué se está diseñando

- Captura de enlaces de YouTube, TikTok e Instagram: notas a partir de subtítulos o ASR, archivo opcional de video en R2 y modo de envío al grupo privado de Telegram.
- Archivo de publicaciones de X/Twitter y Pinterest, además de páginas web, Substack y Wikipedia.
- Captura de audio con transcripción obligatoria y clasificación de intención antes de decidir si se guarda una nota.
- OCR de imágenes/documentos, TTS y búsqueda multimodal como capacidades previstas.
- Soporte de procesamiento en coreano, inglés y español, conservando el idioma original y la procedencia de los datos.

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
- **Audio:** transcribir, clasificar la intención y guardar automáticamente sólo los casos clasificados como nota. Las rutas de recordatorio y mandado requieren features/reglas adicionales.

Los marcadores son prefijos reales delante de la URL; las llaves usadas en ejemplos de `BOT.md` sólo indican un marcador de posición.

## Seguridad y privacidad

- No guardar tokens, claves API ni cookies en el repositorio. Se prevé gestionarlos como secretos de Modal.
- El uso de un ASR o clasificador alojado externamente puede enviar audio o transcripciones fuera de Modal; la ruta externa deberá ser explícita y configurable.
- Los contenidos extraídos de enlaces, OCR y transcripciones se tratan como datos no confiables, no como instrucciones internas del bot.
- Respetar permisos de acceso y las condiciones de las plataformas fuente.

## Estado y siguientes pasos

El roadmap detallado está al final de [BOT.md](BOT.md). La primera etapa de implementación prevista es un webhook mínimo, el parser de comandos, un worker en CPU y el flujo de captura de videos con escritura de notas en R2. Aún faltan configuración de Modal, credenciales, definición de schemas, código y pruebas.
