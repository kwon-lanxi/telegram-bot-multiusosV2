# 📓 BOT — Documento vivo de construcción

> Documento vivo del proyecto. Actualizado: 2026-10-25. Dividido en **Parte A (Arquitectura)** y **Parte B (Features)**.

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
| ASR | **Qwen/Qwen3-ASR-1.7B** (1.7B LLM + encoder audio ~300M) | 3.9 GB BF16 | **GGUF Q8_0** (audio.cpp native) ~2 GB | **audio.cpp** (docs/models/qwen3.md) — fallback: llama.cpp con `ggml-org/Qwen3-ASR-1.7B-GGUF` | ~2–3 GB VRAM | Apache-2.0 |
| Embeddings multimodales | **google/embeddinggemma-2** (texto, imagen, audio y video en espacio compartido de 768d) | 1.49 GB BF16 (checkpoint completo) | Objetivo de prueba: **INT8**; BF16 como baseline de calidad (L4 soporta BF16) | **Sentence Transformers** en GPU L4; cargar encoders requeridos por modalidad | Medir VRAM de los encoders activados; 24 GB disponibles | Apache-2.0 |
| TTS | **Qwen/Qwen3-TTS-12Hz-1.7B-Base** (1.93B) | 3.86 GB BF16 | BF16 (sin cuantizar) | **paquete oficial `qwen-tts`** + FlashAttention2 | ~5–6 GB VRAM | Apache-2.0 |
| Traducción | **tencent/Hy-MT2-1.8B** (2.04B; traducción pura, 33 idiomas) | 4.08 GB BF16 | **GGUF OFICIAL** Q4_K_M (**1.13 GB**) | **llama.cpp `llama-server`** en CPU | ~1.5–2 GB RAM | Apache-2.0 |

### Decisiones con razonamiento

**OCR — Unlimited-OCR** ✅
- Xiaomi-OCR-0 (0.87B) y TeleOCR (1.42B) son **solo chino/inglés** — descartados para un bot en español.
- Unlimited-OCR es MoE: 3B totales pero **500M activos por token** → inferencia rápida pese al tamaño.
- La receta oficial es Transformers/vLLM/SGLang; el GGUF es solo comunitario. En la L4 (FP8 nativo) → vLLM con `quantization=fp8` es la vía óptima; el GGUF Q4 vía llama.cpp sería plan B.
- Aceptar: primer deploy en BF16 (6.67 GB, entra holgado en 24 GB) → luego FP8.

**ASR — Qwen3-ASR-1.7B con audio.cpp** ✅ (tu preferencia, razonable)
- 30 idiomas oficiales **incluido español**, superior a Whisper small en español de conversación; hasta **20 minutos de audio** por pasada.
- ⚠️ Cuidado: audio.cpp usa **GGUF con layout propio** — no usar los GGUF de `ggml-org` (llama.cpp) con audio.cpp ni viceversa.
- whisper.cpp queda descartado (solo corre modelos Whisper; su repo HF es `ggerganov/whisper.cpp` con GGML `.bin`, no GGUF).
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
| F1 | `worker` | CPU 2 core | yt-dlp, ffmpeg, R2 I/O, llamadas a F2–F6, Jev para decisiones, API LLM OpenAI-compatible para generación, envío a Telegram | CPU snapshot |
| F2 | `ASR` | **L4** | audio.cpp + Qwen3-ASR-1.7B Q8_0 | CPU+GPU snapshot (alpha) |
| F3 | `OCR` | **L4** | vLLM + Unlimited-OCR FP8/BF16 | CPU snapshot (+GPU v1.5) |
| F4 | `TTS` | **L4** | `qwen-tts` BF16 + FlashAttention2 | CPU snapshot |
| F5 | `embedder` | **L4** | embeddinggemma-2 texto/imagen/audio/video, salida inicial 256d; objetivo INT8 tras validar | CPU snapshot (+ GPU snapshot experimental) |
| F6 | `translator` | CPU 2 core | llama.cpp `llama-server` + Hy-MT2 Q4_K_M | CPU snapshot |

**Pico GPU si F2+F3+F4 vivos a la vez**: ≈ 2 + 7 + 6 = ~15 GB en 3 contenedores L4 distintos → Modal los escala por separado, nunca compiten por VRAM en el mismo contenedor.

## A.6 Anti-cold-start (docs: cold-start + memory-snapshots)

Fuentes: https://modal.com/docs/guide/cold-start · https://modal.com/docs/guide/memory-snapshot

1. **Pesos en `modal.Volume`** (`/models`, pre-descargados con una función `download_models()` al desplegar). El contenedor nunca descarga pesos de la red en runtime.
   > ⚠️ Los Memory Snapshots **no aceleran** la carga desde disco (usan el mismo FS); sirven para saltarse lo demás (imports, JIT, init).
2. **Modo Cls** + `@modal.enter(snap=True)` para lo que va en el snapshot (carga del modelo a RAM CPU) y `@modal.enter(snap=False)` para lo que toca GPU (`.to("cuda")`, warm-up con 1 inferencia). El patrón por sí solo reduce_arranques ~3×, incluso sin GPU snapshots.
3. **CPU Memory Snapshots** (`enable_memory_snapshot=True`) desde v1 — estables.
4. **GPU Memory Snapshots** (`experimental_options={"enable_gpu_snapshot": True}`) — **alpha**. Especialmente prometedor para **ASR (audio.cpp es C++, sin torch)** y para la fase de vLLM OCR. Riesgo conocido: al cambiar código/config los snapshots se invalidan y Modal recalcula (≈6 CPU / 2–3 por GPU) → primeras invocaciones tras redesplegar serán lentas. Es normal.
5. **`scaledown_window=300`** en F2/F3/F4: reusa contenedor entre mensajes seguidos. Coste rango: 300 s idle de L4 = $0.066 por racha. F0/F1 sin ventana larga (CPU barata), cap de 60 s.
6. **Imports en `Image.imports()`** para que las deps queden en el snapshot.
7. ⚠️ Si alquien importa torch en fase `snap=True` CPU-snapshot: `torch.cuda.is_available()` puede inicializar CUDA con 0 GPUs → re-importar torch en `enter(snap=False)` (audio.cpp no sufre esto, C++).
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

**Regla base:** todo audio recibido se transcribe sí o sí, aunque después no se archive como nota. El audio original y la transcripción permanecen sólo en memoria/almacenamiento temporal durante el procesamiento; no se guardan en R2/Volume ni como nota si la clasificación da recordatorio, mandado, otro o no claro. Sólo la clase `nota` persiste como nota en Obsidian/R2, con la transcripción fiel disponible para trazabilidad. El audio temporal se elimina al terminar o al fallar definitivamente.

### Pipeline común

```text
Audio Telegram / audio extraído de medio
  → normalizar a mono 16 kHz (temporal efímero)
  → ASR seleccionado: Qwen3-ASR local (preferido) o Groq Whisper
  → conservar transcript crudo + idioma + timestamps/confianza disponibles
  → Jev clasifica intención: recordatorio | mandado | nota | otro/no claro
  → enrutar por decisión
```

- **ASR Qwen3 local:** ruta de privacidad/control preferida en F2 (L4 + audio.cpp). Aplicar a coreano, inglés y español; preservar el idioma original en la transcripción.
- **Groq Whisper:** alternativa externa (`whisper-large-v3-turbo` por relación coste/velocidad; `whisper-large-v3` cuando prima precisión). Enviar por la API de transcripción, no por la de traducción: la API de traducción de Groq sólo produce inglés y el bot debe conservar ko/en/es. Proporcionar `language` cuando se conozca y usar `verbose_json` si hacen falta segmentos/palabras con timestamps.
- **Selección ASR:** el router decide por disponibilidad/configuración, límite de tamaño, idioma, duración, sensibilidad/privacidad y calidad esperada. Por defecto intentar Qwen local; fallback a Groq sólo si está habilitado explícitamente y el usuario acepta que el audio sale del entorno local. El usuario podrá fijar preferencia con configuración futura. No duplicar llamadas de ASR salvo reintento o control de calidad explícito.
- Groq documenta actualmente límite de 25 MB (free) / 100 MB (dev) por archivo y recomienda chunking para archivos mayores; comprobar límites vigentes y trocear con solape cuando corresponda. El cliente nunca debe recibir el secreto API.

### Clasificación y rutas Jev

Jev procesa el **texto transcrito**, no el archivo de audio, y responde con primitivas estructuradas. Una llamada puede incluir preguntas independientes sobre el mismo estado:

1. `tipo`: Choice con categorías `recordatorio`, `mandado`, `nota`, `otro`.
2. `requiere_fecha_hora`: Noul; sólo evidencia textual explícita cuenta como fecha/hora, no inferirla.
3. `confianza_intencion`: Score con rúbrica acordada; conservar probabilidades/confianza para auditoría.

Enrutado v1:

- **nota**: aplicar “mejoramiento con IA” (limpiar puntuación/repeticiones sin cambiar sentido, extraer título/temas/resumen según `voice_note_schema`) y guardar la nota estructurada en R2/Obsidian. Mantener la transcripción original o una sección de transcripción fiel para trazabilidad. Ésta es la única clase de audio que se guarda como nota automáticamente.
- **recordatorio**: no convertirlo silenciosamente en nota ni persistir la transcripción. Requiere una feature de recordatorios y confirmación/fecha/hora clara; hasta implementar esa feature, responder que fue detectado pero no programado y pedir aclaración/confirmación según corresponda. No inventar fecha ni prometer notificación.
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
| `NoteGenerator` | Mejorar transcripción y producir nota Markdown/JSON | API generativa compatible con OpenAI SDK; modelo/proveedor concreto pendiente | Prompt + fuente/metadatos → JSON con Structured Outputs cuando el endpoint lo soporte | No asumir que todo endpoint compatible implementa todas las funciones de OpenAI; comprobar schema mode/modelo |
| `LocalGenerator` (opcional) | Generación local / respaldo sin enviar transcripción fuera | Liquid LFM pequeño servido por vLLM/SGLang, si se prueba | Texto → texto/JSON | OpenAI-compatible sólo en el endpoint de serving local; validar idiomas y calidad antes de usar |

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

## Fuentes de referencia consultadas

- Modal cold starts: https://modal.com/docs/guide/cold-start
- Modal memory snapshots: https://modal.com/docs/guide/memory-snapshots
- EmbeddingGemma 2 en Sentence Transformers (texto/imagen/audio/video; L4 BF16): https://ai.google.dev/gemma/docs/embeddinggemma/fine-tuning-multimodal-embeddinggemma-with-sentence-transformers
- Extractores soportados por yt-dlp (el propio proyecto advierte que el soporte puede romperse y debe probarse): https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md
- Telegram Bot API y límites/local Bot API server: https://core.telegram.org/bots/api
- Qwen3-ASR Hub: https://huggingface.co/Qwen/Qwen3-ASR-1.7B
- Groq Speech-to-Text (modelos, idiomas, límites, timestamps): https://console.groq.com/docs/speech-to-text
- TypeSafe Jev quickstart (Choice/Score/Noul y SDK): https://docs.typesafe.ai/introduction/quickstart
- Liquid AI d1: https://docs.liquid.ai/lfm/models/d1
- Liquid AI serving vLLM/OpenAI-compatible: https://docs.liquid.ai/deployment/gpu-inference/vllm
- Liquid AI LFM2.5 1.2B Instruct: https://docs.liquid.ai/lfm/models/lfm25-1.2b-instruct
- OpenAI Structured Outputs: https://developers.openai.com/api/docs/guides/structured-outputs

---

## Pendientes (roadmap v1)

- [ ] Configurar Modal: `modal setup` + secretos (`TELEGRAM_TOKEN`, credenciales R2, clave del proveedor generativo; `TYPESAFE_API_KEY` si se usa Jev y `GROQ_API_KEY` sólo si se habilita Groq)
- [ ] F0 webhook CPU: regex de los 3 comandos, notas de texto, upload de voz
- [ ] F1 worker CPU: adaptadores de URL + extracción + enrutado de IA/ASR + escritura R2 (frontmatter Obsidian)
- [ ] Contrato `IntentClassifier` Jev: Choice nota/recordatorio/mandado/otro + umbrales, abstención y aclaraciones
- [ ] Contrato `Transcriber`: ruta Qwen local preferida, fallback Groq opt-in, chunking y borrado de temporales
- [ ] Contrato `NoteGenerator` OpenAI-compatible: provider/base_url/model/capacidades; probar Structured Outputs con proveedor elegido
- [ ] F2 ASR L4: audio.cpp + Qwen3-ASR-1.7B Q8_0 + `download_models()` + Volume
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
