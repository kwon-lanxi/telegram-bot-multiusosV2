# 📓 BOT — Documento vivo de construcción

> Documento vivo del proyecto. Actualizado: 2026-10-26. Dividido en **Parte A (Arquitectura)** y **Parte B (Features)**.
>
> Los **flujos de trabajo e intención** (ejes de clasificación, puertas de decisión `P*`, flujos `W1`–`W9` y el flujo de recuperación) viven aparte, en [FLUJOS.md](FLUJOS.md). `B.2` es la puerta de triaje de audio de ese documento; `B.12` es su flujo `W6`.

---

# PARTE A — Arquitectura

## A.1 Qué es

Bot de Telegram **webhook** sobre **Modal** (serverless, facturación por segundo). Multiusos, pero con un propósito central: **recuperación de memoria** — archivador y documentador de mi vida. Todo lo capturado termina en la bóveda **Obsidian**, cuya fuente de verdad es un bucket **Cloudflare R2**.

- Hardware IA: **GPU L4** de Modal (24 GB VRAM, nearby Ada Lovelace: soporta **FP8/INT8 tensor cores**).
- Modelos: todos **pequeños y cuantizados** (ver A.4).
- Enrutado: webhook CPU barato → workers CPU (descarga/Gestión/LLM-API) → workers GPU L4 (ASR/OCR/TTS).

## A.2 Log de decisiones

| Fecha | Decisión | Motivo |
|---|---|---|
| 2026-10-25 | Plataforma: **Modal**, webhook (`@modal.fastapi_endpoint`), no polling | Serverless real, cold starts de ~1 s, pay-per-second, $30/mes de crédito gratis |
| 2026-10-25 | GPU: **L4** | ~$0.000222/s (≈$0.80/h); Ada con FP8/INT8 ideal para modelos cuantizados |
| 2026-10-25 | Almacenamiento: **R2** (S3 API vía `boto3`) | Sin fees de egress; ahí vive la bóveda Obsidian |
| 2026-10-25 | Separación webhook CPU / workers CPU / workers GPU | El webhook debe responder 200 en <1 s |
| 2026-10-25 | Anti-cold-start: Volume + `enter(snap=True/False)` + Memory Snapshots | Ver A.6 |
| 2026-10-25 | **OCR → baidu/Unlimited-OCR** (cuantizado) | Único de los 3 candidatos multilingüe (los otros 2: zh/en solo) |
| 2026-10-25 | **ASR → Qwen/Qwen3-ASR-1.7B con audio.cpp** (preferencia mía confirmada) | Apache-2.0, 30 idiomas (incl. ES), audio hasta 20 min, C++ rápido |
| 2026-10-25 | **Embeddings → google/embeddinggemma-2** (texto, 256d Matryoshka) | Multilingüe 100+ idiomas, truncable, GGUF disponible |
| 2026-10-25 | **TTS → Qwen/Qwen3-TTS-12Hz-1.7B-Base** (paquete oficial, no GGUF) | Clonado de voz con ref clip; GGUF comunitario NO es drop-in |
| 2026-10-25 | **MT → tencent/Hy-MT2-1.8B** GGUF OFICIAL Q4_K_M vía llama.cpp | Traducción (33 idiomas, ES); en CPU para no gastar GPU |
| 2026-10-25 | Resumición/entidades → **API LLM externa compatible con OpenAI SDK** en workers CPU | No se paga GPU propia; Structured Outputs (B.6) |
| 2026-10-26 | Clasificación de intención para audios → **Jev / TypeSafe** antes de decidir si se archiva | Choice/Score/Noul estructurados; no genera transcripciones ni notas libres |
| 2026-10-26 | ASR de audio: **Qwen3-ASR local como ruta preferida**, Groq Whisper como alternativa seleccionable | Decidir ruta por privacidad, tamaño/duración, disponibilidad y calidad; eliminar temporales tras procesar |
| 2026-10-26 | Separar interfaces de IA: **Jev/Liquid d1 para decisiones** y **API OpenAI-compatible para generación** | Liquid d1 usa integración TypeSafe; modelos LFM servidos por vLLM/SGLang pueden exponer OpenAI-compatible, pero no asumir que Liquid API alojada ofrece chat OpenAI-compatible |
| 2026-10-26 | Recordatorios: Jev filtra intención; LLM extrae campos; **QStash entrega a la hora programada** y Google Calendar crea el evento | No guardar el audio; mantener un log estructurado en Obsidian/R2; diseñar operaciones idempotentes y reconciliables |
| 2026-10-29 | **ASR: descartar audio.cpp.** Pesos BF16 (safetensors HF estándar) ya descargados en Volume `models-telegram-bot` → servir con **`qwen-asr`/Transformers** (primaria) y **vLLM** (batches, receta oficial, pin de versión) | Sin conversiones GGUF; el modelo ya corre nativo en runtime conocido; interfaz de notas fijada en PLAN.md (nombre `YYYY-MM-DD_HH-MM-SS--{titulo}` + `created:` ISO UTC 7 dígitos) |
| 2026-10-29 | **La nota es el documento principal de cada captura; el media se embebe ARRIBA** del cuerpo (audio/foto arriba); sufijos fijos `--voz.ogg` / `--foto.<ext>` ligados por `ruta:` | Obsidian-first: al abrir la nota se ve el media primero; el máster no cambia de nombre |
| 2026-10-29 | **F7 titler: título generado por GGUF pequeño en T4 (llama.cpp), diferido en lote.** Modelo lo coloca el usuario en Volume `models-telegram-bot/titler/`; rename en R2 (copy+delete) + update de `titulo:`/`ruta:` | La captura nunca espera modelos (R1); el `{titulo}` del nombre nace provisional y se reemplaza con el título generado |
| 2026-10-30 | **ASR: Groq `whisper-large-v3-turbo` como ruta primaria; Qwen3-ASR local diferido hasta tener cuota L4; `whisper.cpp` descartado como plan B salvo privacidad total** | Sin L4 pendiente, Groq ($0.04/h, ~216x realtime, ES incluido, ogg soportado) gana por costo/latencia/cero-GPU; Qwen BF16 queda en el Volume para cuando haya L4; whisper.cpp solo si se exige cero-nube |
| 2026-10-30 | **OCR: Groq vision (llama-4-scout → maverick fallback) como ruta primaria; `Xiaomi-OCR-0`/`GLM-OCR` locales diferidos hasta L4; Mistral OCR solo si Groq decepciona** | Mismo motivo que ASR (sin L4): cero secretos nuevos, CPU puro, nota `--foto.md` solo con `/ocr` en caption; fallback automático si dan de baja un modelo |

## A.3 Precio de referencia (Modal, verificado 2026-10-25)

| Recurso | Precio |
|---|---|
| T4 | $0.000164/s (≈$0.59/h) |
| **L4 (nuestra GPU)** | **$0.000222/s (≈$0.80/h)** |
| A10 | $0.000306/s |
| H100 | $0.001097/s |
| CPU (core) | ~$0.047/core-hora |
| Plan Starter | $0/mes + $30 de crédito gratis |

Con uso personal y modelos pequeños: **dominado por cold starts, no por segundos de GPU**. Ejemplo: nota de voz de 2 min en Qwen3-ASR-1.7B ≈ 2–5 s de GPU = ~$0.001.

## A.4 Stack de modelos (decidido, verificado en HF 2026-10-25)

| Capacidad | Modelo elegido | Pesos | Cuantización/Formato | Runtime | RAM/VRAM | Licencia |
|---|---|---|---|---|---|---|
| OCR | **baidu/Unlimited-OCR** (3.34B, MoE 500M activos, base DeepSeek-OCR) | 6.67 GB BF16 | **FP8** (≈3.3 GB) o GGUF Q4 comunitario (`sahilchachra/Unlimited-OCR-GGUF`) | **vLLM** (receta oficial) — Transformers como fallback | ~4–8 GB VRAM | MIT |
| ASR | **Qwen/Qwen3-ASR-1.7B** (1.7B LLM + encoder audio ~300M) | 3.9 GB BF16 | **BF16 safetensors** (formato HF, ya en Volume `models-telegram-bot/asr/Qwen3-ASR-1.7B`) | **qwen-asr / Transformers** — vLLM (receta oficial, pin de versión) para batches; audio.cpp descartado 2026-10-29 | ~4–5 GB VRAM | Apache-2.0 |
| Embeddings multimodales | **google/embeddinggemma-2** (texto, imagen, audio y video en espacio compartido de 768d) | 1.49 GB BF16 (checkpoint completo) | Objetivo de prueba: **INT8**; BF16 como baseline de calidad (L4 soporta BF16) | **Sentence Transformers** en GPU L4; cargar encoders requeridos por modalidad | Medir VRAM de los encoders activados; 24 GB disponibles | Apache-2.0 |
| TTS | **Qwen/Qwen3-TTS-12Hz-1.7B-Base** (1.93B) | 3.86 GB BF16 | BF16 (sin cuantizar) | **paquete oficial `qwen-tts`** + FlashAttention2 | ~5–6 GB VRAM | Apache-2.0 |
| Traducción | **tencent/Hy-MT2-1.8B** (2.04B; traducción pura, 33 idiomas) | 4.08 GB BF16 | **GGUF OFICIAL** Q4_K_M (**1.13 GB**) | **llama.cpp `llama-server`** en CPU | ~1.5–2 GB RAM | Apache-2.0 |

### Decisiones con razonamiento

**OCR — Unlimited-OCR** ✅
- Xiaomi-OCR-0 (0.87B) y TeleOCR (1.42B) son **solo chino/inglés** — descartados para un bot en español.
- Unlimited-OCR es MoE: 3B totales pero **500M activos por token** → inferencia rápida pese al tamaño.
- La receta oficial es Transformers/vLLM/SGLang; el GGUF es solo comunitario. En la L4 (FP8 nativo) → vLLM con `quantization=fp8` es la vía óptima; el GGUF Q4 vía llama.cpp sería plan B.
- Aceptar: primer deploy en BF16 (6.67 GB, entra holgado en 24 GB) → luego FP8.

**ASR — Qwen3-ASR-1.7B con Transformers/qwen-asr** ✅ (audio.cpp descartado 2026-10-29)
- Multilingüe **incluido español**; hasta **20 minutos de audio** por pasada (según la ficha consultada el 2026-10-25; revisar números vigentes al abrir M3).
- Los pesos BF16 safetensors (formato HF estándar) **ya están en el Volume `models-telegram-bot/asr/Qwen3-ASR-1.7B`** — se monta el Volume, sin descargar nada en runtime.
- Runtime primario **`qwen-asr`/Transformers** (ejemplo oficial `example_qwen3_asr_transformers.py`); vLLM tiene receta oficial para batches y ⚠️ requiere pin de versión (incompatibilidad documentada con 0.16.0+).
- whisper.cpp y audio.cpp quedan descartados: los pesos no son GGUF y no se generarán conversiones para un modelo que ya corre nativo en Transformers/vLLM.
- Explicación de latencia de Qwen (benchmark oficial): TTFT 102 ms a concurrency 1 (no es L4, pero indica lo ligero que es a 1.7B).

**Embeddings — embeddinggemma-2** ✅
- 768d con **truncado Matryoshka a 512/256/128** → empezar evaluando índice a **256d**; comparar recall con 768d antes de fijarlo.
- Modelo multimodal: texto, imagen, audio y video comparten el espacio vectorial; se podrán recuperar notas con queries de texto y medios relacionados.
- Embeddings en **L4** para correr imagen/audio y OCR/ASR en paralelo con la GPU, como pidió el usuario. Objetivo INT8, pero comprobar compatibilidad real del stack multimodal y calidad vs BF16: el modelo/documentación oficial usa BF16 en L4 y no se debe asumir que cualquier ruta de cuantización admite todas las modalidades. Mantener BF16 como baseline.
- Para solo texto se puede desactivar encoder de audio y reducir memoria; se habilitan los encoders necesarios por modalidad.

**TTS — Qwen3-TTS-12Hz-1.7B-Base** ✅
- **Clonado de voz**: con un clip corto de mi voz + su transcripción el bot puede hablar como yo.
- GGUF de `cstr/qwen3-tts-1.7b-base-GGUF` requiere su runtime propio (CrispASR) → **descartado**; solo despliegue oficial `qwen-tts` en L4.
- vLLM soporta este modelo solo en modo offline → no sirve para endpoint online. Función separada, arranca solo bajo demanda (feature `/leer`, lecturas de notas).

**MT — Hy-MT2-1.8B** ✅
- **GGUF cuantizado OFICIAL** de Tencent (Q4_K_M 1.13 GB) — servido con llama.cpp estándar.
- Es modelo de **traducción**, no de genérico: sirve para traducir contenido no-español (subtítulos EN, artículos) antes de generar la nota. **El resumen/estructuración sigue siendo la API LLM externa** (Hy-MT no fiable para eso).

### Memoria GPU y concurrencia
No asumir que “todos los pesos caben” equivale a poder ejecutar simultáneamente: KV caches, imágenes/audio grandes y batching también consumen VRAM. Cada función Modal con `gpu="L4"` obtiene su propio contenedor/GPU; separar modelos a funciones distintas permite paralelismo real, pero una ráfaga concurrente puede usar varias L4 y sumar coste. En v1 paralelizar las etapas que aportan latencia (p.ej. OCR de imagen + embedding de imagen, o ASR de audio + embedding de audio), medir VRAM/latencia/coste y limitar concurrencia. Cuando coste importe más que latencia, ejecutar tareas GPU por turnos en un único worker L4.

## A.5 Reparto de funciones en Modal

| # | Función | Hardware | Modelos/Jobs | Snapshots |
|---|---|---|---|---|
| F0 | `webhook` | CPU (0.25 core) | FastAPI receptor; parsea `{url`/`!{url`/`!!{url`, notas de texto, notas de voz; responde 200 | — |
| F1 | `worker` | CPU 2 core | yt-dlp, ffmpeg, R2 I/O, llamadas a F2–F6, Jev para decisiones, API LLM OpenAI-compatible para generación, QStash, Google Calendar y Telegram | CPU snapshot |
| F2 | `ASR` | **L4** | qwen-asr/Transformers + Qwen3-ASR-1.7B BF16 (Volume `models-telegram-bot`) | CPU+GPU snapshot (alpha) |
| F3 | `OCR` | **L4** | vLLM + Unlimited-OCR FP8/BF16 | CPU snapshot (+GPU v1.5) |
| F4 | `TTS` | **L4** | `qwen-tts` BF16 + FlashAttention2 | CPU snapshot |
| F5 | `embedder` | **L4** | embeddinggemma-2 texto/imagen/audio/video, salida inicial 256d; objetivo INT8 tras validar | CPU snapshot (+ GPU snapshot experimental) |
| F6 | `translator` | CPU 2 core | llama.cpp `llama-server` + Hy-MT2 Q4_K_M | CPU snapshot |
| F7 | `titler` | **T4** | llama.cpp `llama-server` + GGUF de títulos (Volume `models-telegram-bot/titler/`, modelo por colocar) | CPU snapshot — detalle en PLAN.md §4.5 |

**Pico GPU si F2+F3+F4 vivos a la vez**: ≈ 2 + 7 + 6 = ~15 GB en 3 contenedores L4 distintos → Modal los escala por separado, nunca compiten por VRAM en el mismo contenedor.

## A.6 Anti-cold-start (docs: cold-start + memory-snapshots)

Fuentes: https://modal.com/docs/guide/cold-start · https://modal.com/docs/guide/memory-snapshot

1. **Pesos en `modal.Volume`** (`/models`, pre-descargados con una función `download_models()` al desplegar). El contenedor nunca descarga pesos de la red en runtime.
   > ⚠️ Los Memory Snapshots **no aceleran** la carga desde disco (usan el mismo FS); sirven para saltarse lo demás (imports, JIT, init).
2. **Modo Cls** + `@modal.enter(snap=True)` para lo que va en el snapshot (carga del modelo a RAM CPU) y `@modal.enter(snap=False)` para lo que toca GPU (`.to("cuda")`, warm-up con 1 inferencia). El patrón por sí solo reduce_arranques ~3×, incluso sin GPU snapshots.
3. **CPU Memory Snapshots** (`enable_memory_snapshot=True`) desde v1 — estables.
4. **GPU Memory Snapshots** (`experimental_options={"enable_gpu_snapshot": True}`) — **alpha**. Especialmente prometedor para **ASR en Transformers (`qwen-asr`)** y para la fase de vLLM OCR. Riesgo conocido: al cambiar código/config los snapshots se invalidan y Modal recalcula (≈6 CPU / 2–3 por GPU) → primeras invocaciones tras redesplegar serán lentas. Es normal.
5. **`scaledown_window=300`** en F2/F3/F4: reusa contenedor entre mensajes seguidos. Coste rango: 300 s idle de L4 = $0.066 por racha. F0/F1 sin ventana larga (CPU barata), cap de 60 s.
6. **Imports en `Image.imports()`** para que las deps queden en el snapshot.
7. ⚠️ Si alguien importa torch en fase `snap=True` CPU-snapshot: `torch.cuda.is_available()` puede inicializar CUDA con 0 GPUs → re-importar torch en `enter(snap=False)` y no tocar CUDA hasta el segundo `enter` (relevante desde que ASR usa Transformers/torch, 2026-10-29).
8. **Sin `min_containers`**: uso personal esporádico; mejor frío-rápido + snapshots que pagar preparar por siempre.

---

# PARTE B — Features

## B.1 YouTube — sintaxis y flujos (v1)

Notación: `{URL}` es un marcador de posición en este documento; **no se escriben llaves literalmente**. Sintaxis real: `https://youtu.be/ID` (nota), `!https://youtu.be/ID` (nota + video a R2), `!!https://youtu.be/ID` (sólo video al grupo privado). Para videos de la misma clase, se aplica igual a TikTok e Instagram.

### B.1.1 `{url_yt}` — nota sin video

```
1. Detectar URL en el texto del mensaje.
2. yt-dlp --list-subs (ligero, no el video) → ¿hay subtítulos?
   SI  → descargar SOLO subtítulos (.vtt/.srt)  [+ traducir a es con F6 si no son ES]
          → F1: api_structured(video_meta, subtítulos) → nota (B.6)
          → subir nota a R2
   NO  → descargar SOLO audio (yt-dlp -f bestaudio, m4a) a disco efímero
          → F2: ASR.transcribe(audio) (Qwen3-ASR, hasta 20 min)
          → F1: api_structured(video_meta, transcripción) → nota (B.6)
          → subir nota a R2
          → ELIMINAR audio local (tmpfs, nunca a Volume ni a R2)
3. Responder: "📚 Nota creada → [[YYYY-MM-DD TítuloVideo]]"
```

- `--list-subs` primero es la vía barata: no gastamos GPU si ya hay CC.
- Subtítulos preferidos: **es > en**; auto-subs de YouTube cuentan si es lo único disponible (`--write-auto-subs`).
- Si el video es en otro idioma (no es/en): pasa por el traductor F6 antes de estructurar la nota.

### B.1.2 `!{url_yt}` — nota + video a R2

```
1. B.1.1 completo (nota).
2. además: yt-dlp -f "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best" --merge-output-format mp4
3. subir video a <BUCKET>/media/youtube/<video_id>_<slug>.mp4
4. la nota lleva frontmatter: media_file: [[media/youtube/...]]
5. borrar video local.
```

- Cap: abortar con aviso si el video > ~2 GB.

### B.1.3 `!!{url_yt}` — solo video al grupo privado

```
1. yt-dlp descargar video (mp4).
2. enviarlo al GRUPO PRIVADO de Telegram (reserva de vault), con caption:
     "📼 <título> — <canal> — <fecha_pub> — <duración> — id:<video_id>"
3. borrar local. **Sin nota, sin R2, sin Volume.** El grupo ES el destino final.
4. responder "📼 enviado al vault de reserva".
```

⚠️ **Restricción del Bot API**: `sendVideo`/`sendDocument` aceptan máx **50 MB** estándar (2 GB con `telegram-bot-api` self-hosted). Opciones:
- (a) v1 solo con vídeos ≤ 50 MB — rechazar el resto con aviso.  ← propuesto
- (b) self-host Bot API server en Modal → hasta 2 GB (v2).
- (c) subir con cuenta de usuario vía Telethon (vault personal, sesión humana) (v2.5).
→ **Decisión propuesta: (a) en v1, (b) en v2.** El caption lleva el `video_id` para re-localización futura.

### B.1.4 Parsing

El webhook CPU (F0) parsea un marcador opcional `!!` o `!` seguido de una URL (sin llaves literales) y encola a F1 con `modo: note | note+video | video-only`. Para URLs de video, el texto libre después de la URL se conserva como instrucción LLM ad hoc (B.8). El parser clasifica por dominio antes de aplicar reglas de plataforma.

## B.2 Audios y notas de voz — transcripción obligatoria + clasificación Jev

**Regla base:** todo audio recibido se transcribe sí o sí, aunque después no se archive como nota. La transcripción fiel queda disponible para trazabilidad.

**Qué ocurre con el archivo de audio se decide por modo, no por clase** (diseño en [FLUJOS.md](FLUJOS.md) §4.4). Los tres modos son excluyentes:

| Modo | Cuándo | Archivo | Transcripción |
|---|---|---|---|
| `audio_obra` | tarareo, beat, idea melódica | **se conserva** en R2, con calidad; es la obra | opcional, sólo para indexar/buscar |
| `audio_voz` | resumen diario, testimonio, diario hablado | **se conserva** comprimido en R2 junto a su nota | sí, es la entrada al resumen/reescritura/etiquetado |
| `audio_vehiculo` | dictado: recordatorio, mandado, tarea | **no se guarda**; temporal, se elimina al terminar o al fallar definitivamente | sí, es lo único que importa |

Ante duda entre `obra` y `voz`, conservar: el coste de guardar de más son megabytes y el de perder una obra es irrecuperable. Los audios viven en R2 referenciados por su nota, **nunca dentro de la bóveda sincronizada**. Se conserva el OGG/Opus original de Telegram como máster; no re-codificar a `.mp3` (pérdida de generación y más peso para la misma calidad), sólo transcodificar una copia si hace falta compatibilidad externa.

### Pipeline común

```text
Audio Telegram / audio extraído de medio
  → normalizar a mono 16 kHz (temporal efímero; sólo es la entrada del ASR,
    el máster que se conserve es el archivo original)
  → ASR seleccionado: Qwen3-ASR local (preferido) o Groq Whisper
  → conservar transcript crudo + idioma + timestamps/confianza disponibles
  → Jev clasifica intención: recordatorio | mandado | nota | otro/no claro
  → enrutar por decisión
```

- **ASR Qwen3 local:** ruta de privacidad/control preferida en F2 (L4 + `qwen-asr`/Transformers, pesos BF16 en Volume `models-telegram-bot` — audio.cpp descartado 2026-10-29). Aplicar a coreano, inglés y español; preservar el idioma original en la transcripción.
- **Groq Whisper:** alternativa externa (`whisper-large-v3-turbo` por relación coste/velocidad; `whisper-large-v3` cuando prima precisión). Enviar por la API de transcripción, no por la de traducción: la API de traducción de Groq sólo produce inglés y el bot debe conservar ko/en/es. Proporcionar `language` cuando se conozca y usar `verbose_json` si hacen falta segmentos/palabras con timestamps.
- **Selección ASR:** el router decide por disponibilidad/configuración, límite de tamaño, idioma, duración, sensibilidad/privacidad y calidad esperada. Por defecto intentar Qwen local; fallback a Groq sólo si está habilitado explícitamente y el usuario acepta que el audio sale del entorno local. El usuario podrá fijar preferencia con configuración futura. No duplicar llamadas de ASR salvo reintento o control de calidad explícito.
- Groq documenta actualmente límite de 25 MB (free) / 100 MB (dev) por archivo y recomienda chunking para archivos mayores; comprobar límites vigentes y trocear con solape cuando corresponda. El cliente nunca debe recibir el secreto API.

### Clasificación y rutas Jev

Jev procesa el **texto transcrito**, no el archivo de audio, y responde con primitivas estructuradas. Una llamada puede incluir preguntas independientes sobre el mismo estado:

1. `tipo`: Choice con categorías `recordatorio`, `mandado`, `nota`, `otro`.
2. `requiere_fecha_hora`: Noul; sólo evidencia textual explícita cuenta como fecha/hora, no inferirla.
3. `confianza_intencion`: Score con rúbrica acordada; conservar probabilidades/confianza para auditoría.

Enrutado v1:

- **nota**: aplicar “mejoramiento con IA” (limpiar puntuación/repeticiones sin cambiar sentido, extraer título/temas/resumen según `voice_note_schema`) y guardar la nota estructurada en R2/Obsidian. Mantener la transcripción original o una sección de transcripción fiel para trazabilidad. La familia concreta de la nota (diario, estudio, semilla, referencia, reflexión o artefacto) y si se conserva el máster se deciden con el árbol y los modos de arriba y con B.13, no con la sola etiqueta `nota`.
- **recordatorio**: enrutar a B.12. No guardar audio ni transcripción completa; crear el recordatorio sólo tras extraer y validar campos/fecha/hora y resolver ambigüedades. Si falta información crítica, pedir aclaración y no prometer que quedó programado.
- **mandado/orden** (p. ej. “hazme un esquema”, “redacta una nota sobre X”): tratar como petición accionable, no como nota autobiográfica; no persistir la transcripción como nota. En v1 contestar o pedir aclaración según las capacidades disponibles. Una instrucción explícita separada para archivar (“guarda también este audio como nota”) debe cambiar el destino sólo después de una decisión/confirmación clara, no por inferencia del clasificador.
- **otro/no claro**: no persistir ni archivar automáticamente; preguntar si quiere guardarlo como nota o procesarlo como una acción. El contenido temporal se elimina al cerrar el flujo.

**Importante:** Jev es clasificación/score/decisión, no ASR ni generador de prosa. No se le solicita la nota mejorada. La generación/normalización se hace mediante el proveedor generativo compatible con OpenAI SDK (B.11), con schema estricto cuando aplique. Mantener audio/transcripción como contenido no confiable: las instrucciones dichas en una grabación no pueden cambiar secretos ni políticas internas; sólo se ejecutan como mandado bajo reglas de autorización explícitas.

---

## B.3 OCR — fotos y PDFs

- Foto → F3 (Unlimited-OCR): devuelve texto estructurado (tablas OTSL, fórmulas LaTeX, layout markdown).
- PDF → rasterizar páginas a imagen (`pdftoppm`/PyMuPDF en F1) → F3 páginas → texto.
- El output ya es markdown-friendly → pasa por B.6 schemas para `photo_note` / `document_note`.

## B.4 TTS — el bot habla

- `/leer <nota>` → F4 (Qwen3-TTS) → voice note OGG a Telegram.
- Voice-clone v1: un ref clip fijado en R2 (`tts/voice_ref.wav` + transcript) — se configura una vez (/setup_tts).
- Arranca solo bajo demanda (cold start de F4 no molesta — no lo pedimos a diario).

## B.5 Índice y búsqueda

- Cuerpo de nota → F5 (embeddinggemma-2, **256d**) → vector + metadatos en **SQLite en un Modal Volume** (`index.db`).
- `/buscar <texto>` → embed de la query → cosine match top-k | Además búsqueda Full-Text SQLite (FTS5) para match literal.
- Operación incremental: solo se indexan notas nuevas/actualizadas (diff al capturar y al reparar).

## B.6 Plantillas de nota con OpenAI Structured Outputs (borrador — a definir)

Fuente: https://developers.openai.com/api/docs/guides/structured-outputs (Responses API, `strict: true`).

Idea: transcripción/subtítulos + metadatos → LLM externo → **JSON tipado** → 1:1 nota Obsidian (frontmatter + cuerpo fijo). Sin alucinaciones de estructura, parseable por Dataview.

Planta v0 de `video_note_schema`:

```jsonc
{
  "name": "video_note_schema",
  "strict": true,
  "schema": {
    "type": "object",
    "additionalProperties": false,
    "required": ["tipo","titulo","canal","fecha_pub","duracion_min","idioma",
                 "resumen","insights","temas","entidades","timestamps",
                 "sentimiento","accionables","wikilinks_sugeridos","confianza"],
    "properties": {
      "tipo":           { "type":"string","enum":["tutorial","entrevista","podcast","musica","otro"] },
      "titulo":         { "type":"string" },
      "canal":          { "type":"string" },
      "fecha_pub":      { "type":"string" },
      "duracion_min":   { "type":"number" },
      "idioma":         { "type":"string" },
      "resumen":        { "type":"string","description":"3-5 frases" },
      "insights":       { "type":"array","items":{"type":"string"},"minItems":1 },
      "temas":          { "type":"array","items":{"type":"string"} },
      "entidades":      { "type":"array","items":{"type":"string"} },
      "timestamps":     { "type":"array","items":{"type":"object",
                        "additionalProperties":false,
                        "required":["t","texto"],
                        "properties":{"t":{"type":"string"},"texto":{"type":"string"}}} },
      "sentimiento":    { "type":"string","enum":["positivo","neutral","negativo"] },
      "accionables":    { "type":"array","items":{"type":"string"} },
      "wikilinks_sugeridos": { "type":"array","items":{"type":"string"} },
      "confianza":      { "type":"number","minimum":0,"maximum":1 }
    }
  }
}
```

A DEFINIR (decisión diferida; queda contemplado desde el diseño):
- modelo del LLM externo para estos outputs,
- family de plantillas: `video_note` / `voice_note` / `photo_note` / `document_note` / `link_note`,
- mapeo campo → sección del body de Obsidian,
- qué pasa si `timestamps` ruina el strict mode (opcional vs required).

---

## B.7 TikTok, Instagram, X/Twitter y Pinterest

### Soporte de extracción y credenciales

- Reutilizar **yt-dlp** como primera vía para metadatos, captions/subtítulos y descarga de medios; yt-dlp lista extractores para varios sitios, pero el soporte no es garantía y puede romperse cuando cambian las webs. Hacer un adaptador por plataforma y probarlo con URLs públicas y con contenido accesible por sesión.
- Para Instagram/TikTok/X/Pinterest privados, contenido restringido o formatos no cubiertos por yt-dlp, añadir adaptadores alternativos sólo cuando una prueba concreta lo requiera (API oficial/export de datos u otro extractor mantenido). No acoplar el core del bot a una API no oficial.
- El usuario permite usar cookies porque es su bot personal. Guardarlas como **Modal Secret** o artefacto privado cifrado, nunca en el repo, logs, Telegram, R2 público ni dentro de la imagen. Cookies pueden caducar; usar perfiles por servicio, permisos mínimos, y poder rotarlas/revocarlas. No eludir controles de acceso ni guardar contenido que el usuario no pueda ver.
- Normalizar cada item a `source_platform`, `source_url`, `source_id`, `author`, `published_at`, `caption`, `language`, `media[]`, `subtitles[]`, `download_status`. Conservar URL/IDs y atribución en la nota.

### TikTok e Instagram

Usan los tres modos definidos para YouTube (B.1): `{url}` crea nota y no archiva el video; `!{url}` crea nota y guarda video/medios a R2; `!!{url}` sólo manda video al grupo privado de Telegram, sin nota/R2/Volume. Captions/subtítulos primero; si no hay, ASR Qwen3. Para Instagram, incluir Reels y posts/carruseles; para TikTok, también slideshows/fotos cuando el extractor lo permita. Preservar orden de slides/medios y no asumir que cada URL produce un solo MP4. Registrar qué extractor y qué sesión/cuenta pudieron acceder al contenido.

### X / Twitter

Sintaxis (la URL debe ser el primer token; texto posterior, si existe, es instrucción de LLM):

- `https://x.com/... [instrucción opcional]`: archiva texto/caption y medios localizables en R2; produce una nota con **resumen corto** si no hay instrucción. Si hay instrucción, úsala para la síntesis de texto y medios.
- `!https://x.com/... [instrucción opcional]`: nota limpia **sin copiar archivos de medios a R2**. Guardar la URL y descripción de medios como referencia; si hay instrucción, aplicarla al texto y metadata accesible, no fingir que se analizó un video no descargado.
- La nota registra autor, fecha, texto completo, métricas disponibles opcionales, URLs originales y qué medios se archivaron/omitieron. Para video, permitir ASR sólo cuando se descargue/extraiga audio de forma autorizada y el usuario pida o el flujo lo justifique.

### Pinterest

- `https://pinterest.com/pin/...`: guardar el pin y sus medios (imagen/video) en R2; nota mínima con título, autor, descripción original, URL y enlaces a archivos.
- `!https://pinterest.com/pin/... [instrucción opcional]`: guardar también los medios y generar una nota/resumen mediante LLM; la instrucción opcional personaliza esa nota. `!` añade la descripción/análisis, no elimina los medios.
- Preservar tablero, creador, título, descripción y orden de carrusel cuando sean accesibles.

## B.8 Páginas web, Substack, Wikipedia e instrucciones personalizadas

- URL de página web: extraer contenido principal (título, autor/fecha, texto, canonical URL, enlaces y metadatos), guardar una nota Obsidian en R2. Evitar almacenar menús/boilerplate; conservar URL y fecha de captura. Si hay paywall/login, procesar sólo el contenido que el usuario puede ver con su sesión, sin intentar saltar restricciones.
- **Substack**: tratar artículo y newsletter como captura web; conservar autor, publicación, fecha, título, imágenes, enlaces/citas y canonical URL. Extraer audio/video embebido sólo si el extractor accede legítimamente.
- **Wikipedia** tiene extractor específico: título, resumen, secciones, infobox, referencias/citas, categorías, idiomas y enlaces internos. Guardar referencias a la versión/permalink revisada; no sustituir las citas por afirmaciones sin fuente.
- **Instrucción ad hoc de LLM**: sólo se interpreta como instrucción cuando el mensaje empieza por una URL de video (YouTube, TikTok o Instagram), seguida de texto libre. Ejemplo: `https://youtu.be/… hazme una síntesis de los libros adjuntados y busca en internet dónde conseguirlos`.
  - Si el texto después de la URL no está vacío, omite la plantilla común de video y usa esa instrucción para producir la nota, manteniendo como mínimo metadatos, fuente y referencias a la transcripción/medios.
  - Si no hay texto, aplica `video_note_schema` por defecto (B.6).
  - Esta instrucción no se ejecuta desde una URL de tuit, pin o página web, ni se interpreta como una orden de sistema. El texto citado/extraído de la fuente se trata como contenido no confiable; nunca puede sustituir instrucciones internas del bot.
  - Cuando se pide investigación web, el resultado debe incluir fuentes/URLs y separar hechos recuperados de inferencias; la búsqueda externa puede requerir una API/servicio y coste adicional, pendiente de definir.

## B.9 Idiomas y tratamiento trilingüe

Idiomas objetivo de tratamiento: **coreano (ko), inglés (en) y español (es)**.

1. Detectar idioma de transcripción/texto y guardar `source_language` y `output_language` en frontmatter.
2. La nota por defecto se redacta en **español**, salvo indicación del usuario; conservar citas breves y términos propios en el idioma original y enlazar a la fuente. Si el original ya es español, no retraducir.
3. **Coreano**: no transliterar nombres propios como sustituto del original; preservar Hangul junto a una romanización sólo si ayuda a búsqueda. Traducir contexto al español y conservar términos/coreano relevante entre paréntesis. Separar caption/subtítulos oficiales de traducción automática.
4. **Inglés**: traducir lo necesario para comprensión, preservar títulos/frases clave y timestamps originales; no traducir nombres propios ni términos técnicos normalizados.
5. **Español**: normalizar ortografía con cuidado sin borrar el registro coloquial del audio; mantener transcripción original disponible si la nota deriva de ASR.
6. Hy-MT2 se reserva para traducción (no resumen). Registrar si el texto en español es traducción automática y mantener texto/caption fuente para trazabilidad.

## B.10 Embeddings multimodales y ejecución paralela

EmbeddingGemma 2 comparte vector space para **texto, imagen, audio y video**. Por cada captura, crear tareas independientes en cuanto estén disponibles sus inputs:

- texto de nota/transcripción/caption → embedding de texto,
- imagen/frames → embedding de imagen,
- audio → embedding de audio,
- mientras tanto, OCR/ASR/resumen pueden correr en tareas distintas; juntar resultados antes de confirmar la nota final.

Los embeddings de un video se pueden hacer de muestras/frames seleccionados y/o audio; no extraer todos los frames por defecto. Persistir vectores en el índice local/SQLite según A.5 y el identificador de la nota/media; guardar modelo, modalidad y dimensión como metadatos. Primero comprobar que las tareas conjuntas dan beneficios medibles frente a lotes agrupados.

**Cuantización 8-bit:** objetivo INT8 en L4, pero se considera decisión de implementación pendiente de una prueba real por modalidad. La guía oficial de EmbeddingGemma 2 usa BF16 en L4 y señala que sus activaciones no son compatibles con FP16; por tanto no cambiar a FP16 como atajo. Comparar INT8 con BF16 en texto, coreano, inglés, español, imágenes y audio (recall@k / similitud cross-modal, VRAM, latencia). Si alguna modalidad pierde calidad o el runtime no la soporta, usar BF16 para esa ruta. El truncado de vector a 256d es reducción de dimensiones post-embedding, **no** es cuantización de los pesos.

---

## B.11 Proveedores y contratos de IA

Separar los proveedores por **tipo de tarea**, no esconderlos detrás de un único “modelo IA”:

| Contrato interno | Uso | Proveedor/modelo considerado | Entrada/salida | Regla |
|---|---|---|---|---|
| `Transcriber` | ASR de audios y pistas extraídas | Qwen3-ASR local; Groq Whisper como ruta API | Audio → texto + idioma/timestamps/metadata disponibles | Qwen local preferido; Groq sólo si habilitado y permitido por privacidad |
| `IntentClassifier` | Decidir recordatorio/mandado/nota/otro | Jev (TypeSafe System One); Liquid d1 cuando se use su integración documentada | Texto/estado → Choice, Score, Noul | No produce texto libre; definir umbrales y ruta para baja confianza |
| `ReminderExtractor` | Normalizar fecha/hora, zona horaria, título y detalles | LLM generativo compatible con OpenAI SDK | Transcripción temporal + contexto → esquema JSON validado | No agenda si hay ambigüedad; normaliza el texto y descarta audio/transcripción al terminar |
| `NoteGenerator` | Mejorar transcripción y producir nota Markdown/JSON | API generativa compatible con OpenAI SDK; modelo/proveedor concreto pendiente | Prompt + fuente/metadatos → JSON con Structured Outputs cuando el endpoint lo soporte | No asumir que todo endpoint compatible implementa todas las funciones de OpenAI; comprobar schema mode/modelo |
| `LocalGenerator` (opcional) | Generación local / respaldo sin enviar transcripción fuera | Liquid LFM pequeño servido por vLLM/SGLang, si se prueba | Texto → texto/JSON | OpenAI-compatible sólo en el endpoint de serving local; validar idiomas y calidad antes de usar |

### Capas de modelo (T0–T3)

Regla de reparto entre local y hospedado (detalle de flujos en [FLUJOS.md](FLUJOS.md) §4.7): la frontera no es el tamaño del texto sino **decidir frente a redactar**. Decidir y extraer es barato y va local; redactar con calidad en tres idiomas es lo que los modelos pequeños no garantizan.

| Capa | Dónde | Tareas |
|---|---|---|
| **T0** | determinista, sin modelo | regex, fechas, FTS, conteos, agregados |
| **T1** | GGUF local (CPU o L4) | clasificar, etiquetar, extraer campos de transcripciones cortas, subtipo de semilla |
| **T2** | API rápida hospedada | reescritura/resumen del diario, plantillas con schema estricto, síntesis |
| **T3** | agente de consulta sobre la bóveda | preguntas sobre las notas, con citas; búsqueda semántica |

Promoción medida: una tarea sube de T1 a T2 sólo cuando su tasa de fallo lo justifica, y baja cuando deja de serlo.

**Modelos locales candidatos (verificados 2026-10-27, ambos Apache-2.0 y text-only):**

| Repo | Parámetros | GGUF | Advertencias verificadas |
|---|---|---|---|
| `openbmb/MiniCPM5-2B` | 2,52 B | **oficial** (`…-GGUF`): Q4_K_M ≈ 1,56 GB, Q8_0 ≈ 2,68 GB, F16 ≈ 5,04 GB | ficha lista **inglés y chino**; español/coreano **no documentados** |
| `XHToken/Spark-X2.6-4B` | 4,11 B | oficial + terceros (bartowski): Q4_K_M ≈ 2,62 GB | contexto declarado de 1 M, innecesario aquí y consume memoria; español/coreano **no documentados** |

Dos hechos que condicionan la implementación: **ninguno documenta español ni coreano** (hay que probarlos con muestras propias ko/en/es antes de depender de ellos) y **ninguno documenta modo JSON ni salida restringida por schema** (se pide JSON en el prompt y se valida/repara en Python, lo que refuerza la necesidad de validación de aplicación en los schemas de B.6).

**Proveedores hospedados:** documentan **JSON Schema estricto** (no sólo `json_object`) Groq, Cerebras y DeepInfra. Groq ya está previsto en el stack por Whisper, así que reutilizar su clave para T2 evita un secreto adicional. Ninguno de los proveedores revisados publica una garantía de calidad en español o coreano; lo hacen a nivel de familia de modelo, que no es una medición por endpoint. **Tensión abierta:** en T2 lo que sale de la máquina es sobre todo el diario, el contenido más sensible del sistema; conviene decidir la política de privacidad antes de acumular meses de diario en un proveedor.

### Jev / TypeSafe y Liquid AI

- TypeSafe Jev recibe `state` (texto u objeto) y varias preguntas `Choice`, `Score` o `Noul`; devuelve respuestas y probabilidades. Sirve para el router semántico de audio y otras decisiones acotadas, no para ASR, resumen ni nota libre.
- El campo `model` de TypeSafe elige un modelo/alias servido por TypeSafe; no es una selección arbitraria de cualquier proveedor. Guardar `TYPESAFE_API_KEY` como secreto de Modal.
- Liquid AI documenta **d1** como modelo de decisiones integrable mediante el SDK de TypeSafe y `base_url="https://api.liquid.ai"`. Esto es una API de decisiones, no se debe confundir con un endpoint general de chat compatible con OpenAI.
- Los modelos generativos **LFM** son pesos que pueden servirse con vLLM/SGLang; en ese caso el servidor puede exponer API OpenAI-compatible para usar el SDK OpenAI. Esto no prueba que una API hosted de Liquid ofrezca esa misma compatibilidad.
- Se consideran opciones pequeñas (p. ej. LFM2.5-1.2B-Instruct) sólo como candidato local: probar específicamente ko/en/es y calidad de resúmenes antes de elegir. La documentación revisada no garantiza esos tres idiomas para todos los modelos text-only; no fijar aún.

### API generativa compatible con OpenAI SDK

- Implementar un adaptador (`NoteGenerator`) configurado por `base_url`, API key, modelo y capacidades. La compatibilidad de protocolo no implica acceso al mismo catálogo, precios, privacidad, límites o soporte completo de Structured Outputs.
- Para video/notas usar Responses API + Structured Outputs cuando el proveedor/modelo lo soporte; para otros proveedores confirmar si ofrecen el mismo contrato o si hay que validar JSON en aplicación.
- Las instrucciones libres del usuario tienen prioridad sobre plantillas sólo en el caso establecido en B.8; la fuente externa, transcripción y OCR son datos no confiables y nunca mensajes de sistema.
- Las claves de Groq, TypeSafe/Liquid y el proveedor generativo se guardan como Modal Secrets; nunca en repo, notas, logs ni respuestas de Telegram.
- Antes de enviar audio/transcripciones a servicios externos, considerar que son datos personales: configurar fallback externo conscientemente y documentar retención/región/uso de datos según los términos vigentes de cada proveedor.

## B.12 Recordatorios — Jev → LLM → QStash + Google Calendar → log Obsidian

### Flujo de creación desde un audio

1. Transcribir el audio temporalmente según B.2. Jev decide `recordatorio` frente a `nota`, `mandado` u `otro`; la baja confianza deriva a aclaración, nunca a programación automática.
2. Si Jev clasifica `recordatorio`, pasar la transcripción **sólo en memoria** al LLM generativo (B.11) para extraer un objeto estructurado: `title`, `description` concisa, `due_at` ISO-8601, `timezone` IANA, `duration_minutes` si aplica, `notify_at`/anticipación y cualquier ubicación. No aceptar fechas inventadas por el modelo: cotejar con el texto y la zona horaria configurada; ante hora o fecha ambigua, preguntar al usuario.
3. Confirmar al usuario el resumen y la hora local si la interpretación no es inequívoca o la configuración requiere confirmación. No crear side effects hasta tener los campos requeridos.
4. Crear el evento en **Google Calendar** usando `events.insert` en `primary` (o calendario configurado), con start/end y zona horaria. OAuth de usuario con el scope mínimo compatible, preferiblemente `calendar.events.owned` si basta para el calendario propio; almacenar refresh token y client secret como secretos protegidos, nunca en el repo. El flujo necesita autorización inicial explícita del usuario.
5. Programar en **QStash** un mensaje one-shot al endpoint HTTPS público del bot con `Upstash-Not-Before` (epoch UTC) para `notify_at` — por defecto `due_at`, si el usuario no configura anticipación. El handler valida `Upstash-Signature`, el estado y la identidad del recordatorio antes de enviar un Telegram DM. QStash gestiona la entrega/reintentos; no es el registro de verdad del recordatorio ni sustituye Calendar.
6. Escribir/actualizar el log de Obsidian/R2 con estado, hora local, y los IDs de QStash y Calendar. Responder al usuario con el título, la hora y confirmación de que se creó el evento y quedó programado el aviso.

### Log persistente, sin audio

El audio y la transcripción completa **no se guardan** en R2, Volume ni en la nota de log. Se propone una nota diaria, por ejemplo `Registros/Recordatorios/2026-10-26.md`, con frontmatter de tipo/fecha y una entrada por recordatorio:

```yaml
---
type: reminder-log
date: 2026-10-26
---
reminders:
  - id: reminder_<uuid>
    title: "Llamar a la clínica"
    due_at: "2026-10-27T09:00:00-07:00"
    timezone: "America/Los_Angeles"
    notify_at: "2026-10-27T09:00:00-07:00"
    status: "scheduled" # needs_clarification | creating | scheduled | sent | failed | cancelled
    source: "telegram_voice"
    created_at: "2026-10-26T18:40:00Z"
    qstash_message_id: "..."
    google_calendar_event_id: "..."
    last_error: null
```

El log conserva el contenido normalizado necesario para administrar el recordatorio; no conserva el audio ni el texto íntegro reconocido. `last_error` debe ser breve y no incluir credenciales, tokens ni transcripción privada. La fecha/ruta del archivo sigue la zona horaria configurada por el usuario (decisión pendiente); los timestamps del registro deben ser RFC3339 con offset.

### Consistencia, edición y cancelación

Calendar y QStash no comparten transacción. Usar `reminder_id` estable e idempotente, escribir un estado `creating` y persistir cada ID externo al recibirlo; el handler de QStash debe tolerar entregas repetidas (QStash puede reintentar) y comprobar el estado antes de avisar. Usar deduplicación de QStash al publicar cuando corresponda, además de idempotencia propia: la ventana documentada de deduplicación es de 10 minutos, no una garantía de unicidad permanente.

Si Calendar se creó y QStash falla (o viceversa), marcar `failed`/`creating` con la etapa pendiente, intentar compensar cuando sea seguro o reconciliar en reintento sin crear un segundo evento/aviso. Un recordatorio sólo responde “programado” cuando ambos sistemas y el log reflejan los IDs/estado correspondiente.

Para editar: actualizar el evento existente y cancelar/reschedule el mensaje pendiente de QStash; conservar los IDs y anotar el cambio en log. Para cancelar: cancelar el mensaje QStash pendiente, borrar o marcar cancelado el evento de Calendar según la política configurada, actualizar el estado `cancelled` y confirmar al usuario. Tras el disparo, pasar de `scheduled` a `sent` sólo tras el resultado de Telegram; fallos persistentes van a `failed` para poder corregir/reintentar.

### Decisiones aún por fijar

- Zona IANA por defecto y cómo se configura/cambia.
- Si se requiere siempre confirmación explícita antes de crear o basta con hacerlo cuando Jev/LLM detecten ambigüedad.
- Duración predeterminada del evento (Calendar requiere start y end) y anticipación por defecto del aviso QStash.
- Política de cancelación en Calendar (borrar evento o dejarlo marcado como cancelado) y edición desde Telegram.
- Credenciales OAuth de Google y URL pública HTTPS/verificación de firma del endpoint QStash. Los secretos serán `QSTASH_TOKEN`, claves actuales/siguientes para verificar firmas, y credenciales/tokens de Google OAuth, gestionados como secretos Modal.
- Formato final y ubicación del diario de logs en la bóveda Obsidian.

## B.13 Familias de nota, series de hábitos y espejo de tareas

El árbol de decisión que lleva hasta aquí está en [FLUJOS.md](FLUJOS.md) §4.1–§4.7. Esta sección recoge lo implementable.

### Ocho familias de nota

| Familia | Cadencia | Plantilla | Qué produce |
|---|---|---|---|
| `diario` | **diaria** | resumen + reescritura + etiquetas | hábitos del día derivados (sin preguntar) |
| `estudio` | por clase | curso, fuente, cita | `preguntas[]` de autoevaluación |
| `semilla` | ninguna | subtipo + estado + vínculos | semillero de ideas |
| `referencia` | ninguna | fuente + por qué lo guardo | índice consultable |
| `reflexion` | ninguna | prosa libre, sin estructura forzada | texto |
| `registro` | diaria/por evento | una línea en una serie | tabla agregable |
| `artefacto` | ninguna | ficha + archivo conservado | media en R2 |
| `log` | automática | frontmatter + entrada | trazabilidad del sistema |

Subtipos de `semilla`: `musica`, `codigo`, `narrativa`, `investigacion`, `proyecto`.

**Sólo `diario` y `registro` tienen cadencia.** Exigir periodicidad a una idea es la vía más rápida a que deje de aparecer. La cadencia es además lo que permite detectar el hueco (tres resúmenes diarios ausentes) sin convertirlo en una racha que romper.

### Series de hábitos

Una nota mensual por serie, una línea por día. **Nunca una nota por hábito por día** (serían miles de archivos y una bóveda inútil).

```yaml
---
type: habit-series
month: 2026-10
habitos: [sueno, entrenamiento, estudio, animo]
---
2026-10-27: {sueno: 7.5, entrenamiento: 1, estudio: 2.5, animo: 4, fuente: dicho}
2026-10-28: {entrenamiento: 0, estudio: 1.0, fuente: inferido}
```

- `fuente: dicho` (lo contó en el resumen diario), `medido`, o `inferido`. **Un valor inferido nunca se presenta como medido** y se corrige en la revisión semanal.
- Métrica de cobertura (días registrados de los posibles); **sin rachas y sin presión**. Para este perfil, la racha rota es la causa clásica de abandono del sistema completo.
- Máximo ~5 hábitos en `seguimiento: activo` a la vez. Esto no es una app de hábitos.

### Espejo de tareas

**Proveedor recomendado: Todoist** (token personal, sin OAuth; proyectos, subtareas, recurrencia y webhooks; API gratis). Se descarta Google Tasks como primera opción por su API: vencimiento **sólo fecha** (descarta la hora), sin recurrencia y sin notificaciones de cambio, además de que en modo *Testing* el refresh token de OAuth caduca a los 7 días. Microsoft To Do (Graph) queda como alternativa si se quiere recurrencia y *delta queries* a cambio de más trabajo de credenciales. Nota: el catálogo de proveedores consultado **no ofrece ningún servicio de gestión de tareas**, así que la elección es entre las APIs de los fabricantes.

Reglas, válidas para cualquier proveedor:

- **La bóveda guarda el registro; la app guarda el estado.** Mismo patrón que B.12: `id` propio, `external_id`, `status`.
- **Un solo punto de captura es el bot.** Y Telegram debe poder **cerrar** tareas, no sólo crearlas: dos sitios que revisar equivale a no revisar ninguno. La oferta diaria de «una sola cosa» (FLUJOS §5 `W5`) debe leer el estado del proveedor, no la copia de la bóveda.
- Sin idempotencia documentada en `POST /tasks`, antes de reintentar se reconcilia por título + fecha para no duplicar.

```yaml
type: task-log
tasks:
  - id: task_<uuid>
    title: "Entregar informe"
    provider: todoist
    project_id: "..."
    external_id: "..."
    due_date: "2026-10-29"
    status: created            # created | completed | deleted | failed
    created_at: "2026-10-27T18:40:00-07:00"
    last_error: null
```

---

## Fuentes de referencia consultadas

- Modal cold starts: https://modal.com/docs/guide/cold-start
- Modal memory snapshots: https://modal.com/docs/guide/memory-snapshots
- EmbeddingGemma 2 en Sentence Transformers (texto/imagen/audio/video; L4 BF16): https://ai.google.dev/gemma/docs/embeddinggemma/fine-tuning-multimodal-embeddinggemma-with-sentence-transformers
- Extractores soportados por yt-dlp (el propio proyecto advierte que el soporte puede romperse y debe probarse): https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md
- Telegram Bot API y límites/local Bot API server: https://core.telegram.org/bots/api
- QStash quickstart (mensajes, scheduling y SDK Python): https://upstash.com/docs/qstash/overall/getstarted
- QStash delay/`Upstash-Not-Before`: https://upstash.com/docs/qstash/features/delay
- QStash schedules y zonas horarias: https://upstash.com/docs/qstash/features/schedules
- QStash firma de solicitudes: https://upstash.com/docs/qstash/features/security
- QStash deduplicación: https://upstash.com/docs/qstash/features/deduplication
- QStash cancelar mensaje: https://upstash.com/docs/qstash/api-reference/messages/cancel-a-message
- Google Calendar crear eventos: https://developers.google.com/workspace/calendar/api/guides/create-events
- Google Calendar `events.insert`: https://developers.google.com/workspace/calendar/api/v3/reference/events/insert
- Google Calendar OAuth scopes: https://developers.google.com/workspace/calendar/api/auth
- Google OAuth web server / refresh tokens: https://developers.google.com/identity/protocols/oauth2/web-server
- Qwen3-ASR Hub: https://huggingface.co/Qwen/Qwen3-ASR-1.7B
- Groq Speech-to-Text (modelos, idiomas, límites, timestamps): https://console.groq.com/docs/speech-to-text
- TypeSafe Jev quickstart (Choice/Score/Noul y SDK): https://docs.typesafe.ai/introduction/quickstart
- Liquid AI d1: https://docs.liquid.ai/lfm/models/d1
- Liquid AI serving vLLM/OpenAI-compatible: https://docs.liquid.ai/deployment/gpu-inference/vllm
- Liquid AI LFM2.5 1.2B Instruct: https://docs.liquid.ai/lfm/models/lfm25-1.2b-instruct
- OpenAI Structured Outputs: https://developers.openai.com/api/docs/guides/structured-outputs

---

## Pendientes (roadmap v1)

- [ ] Configurar Modal: `modal setup` + secretos (`TELEGRAM_TOKEN`, credenciales R2, clave del proveedor generativo; `TYPESAFE_API_KEY` si se usa Jev y `GROQ_API_KEY` sólo si se habilita Groq; `QSTASH_TOKEN`, claves de firma y credenciales/tokens Google OAuth para recordatorios)
- [ ] F0 webhook CPU: regex de los 3 comandos, notas de texto, upload de voz
- [ ] F1 worker CPU: adaptadores de URL + extracción + enrutado de IA/ASR + escritura R2 (frontmatter Obsidian)
- [ ] Contrato `IntentClassifier` Jev: Choice nota/recordatorio/mandado/otro + umbrales, abstención y aclaraciones
- [ ] Recordatorios B.12: esquema LLM/validación de fecha-hora + QStash firmado/idempotente + OAuth Google Calendar + log estructurado Obsidian sin audio/transcripción completa
- [ ] Contrato `Transcriber`: ruta Qwen local preferida, fallback Groq opt-in, chunking y borrado de temporales
- [ ] Contrato `NoteGenerator` OpenAI-compatible: provider/base_url/model/capacidades; probar Structured Outputs con proveedor elegido
- [ ] F2 ASR L4: qwen-asr/Transformers + Qwen3-ASR-1.7B BF16 desde Volume `models-telegram-bot` + `check_models()` + snapshots
- [ ] F7 titler T4: llama.cpp + GGUF de títulos (modelo por colocar en `models-telegram-bot/titler/`) + rename diferido + update de frontmatter
- [ ] F3 OCR L4: vLLM + Unlimited-OCR (BF16 primero, luego FP8)
- [ ] F4 TTS L4: qwen-tts (voice-clone /setup_tts)
- [ ] F5 embedder multimodal L4 (int8 a validar) + `index.db` + `/buscar`
- [ ] F6 translator CPU: llama.cpp + Hy-MT2 Q4_K_M
- [ ] `api_structured()` (B.6), schemas por plantilla y override de instrucción libre para URLs de video
- [ ] Adaptadores y pruebas de TikTok, Instagram, X/Twitter, Pinterest, Substack, páginas web y Wikipedia; validar cookies/sesiones en Modal sin filtrarlas
- [ ] Política de idioma es/en/ko y trazabilidad de original/traducción
- [ ] Evaluar embeddings de texto/imagen/audio/video en paralelo; benchmark INT8 vs BF16 y latencia/coste en L4
- [ ] prueba GPU Memory Snapshots en F2/F3
- [ ] decidir límite 50 MB `!!{url` (a/b/c)
- [ ] Elegir proveedor/modelo generativo compatible OpenAI SDK y verificar soporte real de Structured Outputs, idiomas ko/en/es, retención y precio
- [ ] Medir calidad/coste/privacidad Qwen3-ASR local vs Groq Whisper con muestras propias ko/en/es; fijar reglas de fallback
- [ ] Confirmar si Jev TypeSafe o Liquid d1 será el clasificador de intención principal; revisar límites de confianza y la política de datos del servicio
- [ ] Implementar los tres modos de audio (`audio_obra` / `audio_voz` / `audio_vehiculo`) y la escritura del máster en R2 sin re-codificar a mp3 (B.2, FLUJOS §4.4)
- [ ] Ocho plantillas de familia de nota (B.13) + `api_structured()` con validación de aplicación para la capa local
- [ ] Serie mensual de hábitos: formato de una línea por día, `fuente` dicho/medido/inferido, derivación desde el resumen diario y ventana de corrección en la revisión
- [ ] Espejo de tareas: elegir Todoist o Google Tasks, registrar `external_id`/`status`, permitir cerrar tareas desde Telegram y reconciliar por título+fecha
- [ ] Evaluación T1 local: MiniCPM5-2B Q4_K_M y Spark-X2.6-4B Q4_K_M con muestras propias ko/en/es; medir tasa de fallo de extracción y de JSON válido antes de asignarles tareas
- [ ] Decidir la política de privacidad de T2 (si el diario puede salir a un proveedor hospedado o debe quedarse local)
- [ ] Agente de consulta sobre la bóveda (T3): herramientas de búsqueda/apertura/consulta, respuestas siempre con cita a nota y «no lo encontré» explícito
