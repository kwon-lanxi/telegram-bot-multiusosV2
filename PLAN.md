# 🚧 PLAN — De diseño a v0.1 usable

> Plan de construcción del bot. Complementa [BOT.md](BOT.md) (arquitectura/features) y [FLUJOS.md](FLUJOS.md) (flujos/puertas). Aquí se define **qué se construye, en qué orden, con qué integraciones y cómo se valida**. Actualizado: 2026-10-29.

---

## 1. Alcance de v0.1 (la versión "usable")

**Entra:**

1. Webhook de Telegram en Modal (F0, CPU) que responde en <1 s.
2. Captura cruda sin fricción a la **incubadora**: notas de texto, fotos, notas de voz y audios → prefijos del bucket `bucket-prueba` bajo `inbox/`.
3. Transcripción de audio real (F2, L4 + Transformers/`qwen-asr` + Qwen3-ASR-1.7B BF16 — pesos ya en el Volume `models-telegram-bot`).
4. Nota de voz mínima: transcripción fiel + acuse, sin clasificación generativa todavía.
5. Smoke tests locales contra R2 y contra el webhook.

**No entra (diferido, no descartado):** OCR, TTS, embeddings, traducción (F3–F6), Jev/triaje completo (W2 diferido), recordatorios (B.12), descargas de URL (B.1), espejo de tareas (B.13), búsqueda (B.5). Cada uno ya tiene su diseño en BOT.md; entran una vez que la captura funcione a diario.

**Horizonte:** ~4–6 días de trabajo enfocado para captura completa usable (M0–M2), +3–4 días para ASR real (M3).

---

## 2. Layout del bucket `bucket-prueba` (v0.1)

```text
bucket-prueba/
  inbox/                                          # incubadora = destino de TODA captura nueva
    notas/YYYY-MM-DD_HH-MM-SS--{titulo}.md        # texto dictado o pegado
    audio/YYYY-MM-DD_HH-MM-SS--voz.md             # NOTA principal: transcripción, con el audio embebido ARRIBA
    audio/YYYY-MM-DD_HH-MM-SS--voz.ogg            # máster OGG/Opus original de Telegram
    fotos/YYYY-MM-DD_HH-MM-SS--foto.md            # NOTA principal de la foto (1 línea en v0.1; OCR en v1)
    fotos/YYYY-MM-DD_HH-MM-SS--foto.<ext>         # foto tal cual llega
    docs/YYYY-MM-DD_HH-MM-SS--doc.<ext>           # documentos crudos (nada + nota en v1)
  media/                        # v1: obra conservada / videos (FUERA de la bóveda sincronizada)
  vault/                        # v1: destino tras triaje — carpeta Obsidian sincronizada
  logs/                         # v1: logs del sistema (recordatorios, operaciones)
```

Reglas v0.1:

- **Todo entra a `inbox/`.** Nada se clasifica en camino (R1 de FLUJOS). El triaje moverá luego; v0.1 no mueve nada.
- **Nomenclatura de archivos (decisión 2026-10-29):** `YYYY-MM-DD_HH-MM-SS--{titulo}.md` en carpeta plana, **con el número de la fecha siempre en el nombre**, sin subcarpetas por año/mes. Si dos capturas caen en el mismo segundo, se añade `-2` al final. Nota: tu ejemplo decía `hh_ss`; adopté `HH-MM-SS` porque con solo hora y segundo, dos mensajes del mismo minuto colisionarían.
- `id` = el nombre de archivo sin extensión — las referencias internas usan eso; ya no existe un id sintético aparte.
- **La nota es el principal; el media va ARRIBA (decisión 2026-10-29):** en `inbox/audio/` y `inbox/fotos/` el documento principal de cada captura es su nota `.md`; la primera línea del cuerpo embebe el media (p. ej. `![[YYYY-MM-DD_HH-MM-SS--voz.ogg]]`) para que, al abrir la nota, se vea el audio/foto primero. El media conserva su nombre con sufijo fijo (`--voz.ogg`, `--foto.<ext>`) y queda ligado a la nota por el campo `ruta:` del frontmatter; cuando el titler renombra la nota, actualiza `ruta:` en el mismo paso.
- **Título generado, no provisional (decisión 2026-10-29):** toda captura nace con slug provisional (primeras palabras del contenido; en audio: `voz`) y el **F7 titler** le da el título final con un modelo GGUF en T4 — rename en R2 + update de `titulo:`. Detalle completo en §4.5.
- El máster de audio y las fotos viven en su propio prefijo (no dentro de `inbox/notas/`), para poder mantenerlos en v1 fuera de la sincronización del vault; la nota los referencia con `ruta:` en frontmatter.
- `vault/` no existe aún en v0.1: el triaje todavía no corre. La bóveda sincronizada del dispositivo apunta al bucket completo y usable desde el día uno vía el prefijo que decidas sincronizar (§3).

---

## 3. Sincronización Obsidian — cómo entra el bucket en tus dispositivos

**Respuesta a tu duda (copia o no copia):** no hay copia. R2 es la **fuente de verdad** de la bóveda y Obsidian se sincroniza a ella, igual que el plan de BOT.md A.1:

- Plugin **Remotely Save** (Obsidian, multiplataforma: escritorio, iOS, Android) con backend **S3-compatible → Cloudflare R2** (endpoint `https://<account_id>.r2.cloudflarestorage.com`). Cada dispositivo (PCs, celulares) sincroniza el mismo bucket.
- En v0.1 se recomienda sincronizar **solo `inbox/`** a los dispositivos (el resto de los prefijos — másteres de audio, fotos, media — es archivo frío en R2; la nota los referencia con `ruta:`). Así el celular no arrastra gigas.
- Para embeddings y búsqueda, **no** se duplica el vault: el índice (`index.db` en un Volume de Modal, v1) referencia por `id` + `ruta`. Los pesos de modelos tampoco van a R2 (§4.3).

---

## 4. Arquitectura v0.1 — funciones y respuestas a tus dudas técnicas

### 4.1 Funciones Modal activas en v0.1

| # | Función | HW | Trabajo | Snapshot |
|---|---|---|---|---|
| F0 | `webhook` | CPU 0.25 core | recibe update, valida firma/usuario, **responde 200** y encola a F1 | CPU snapshot (estable, `enable_memory_snapshot=True`) |
| F1 | `worker` | CPU 1 core | baja el archivo de Telegram (foto/audio), genera la nota `.md`, escribe a R2 | CPU snapshot |
| F2 | `asr` | **L4** | **qwen-asr (Transformers)** + Qwen3-ASR-1.7B **BF16** desde Volume `models-telegram-bot` (`asr/Qwen3-ASR-1.7B`) | CPU + GPU snapshot (alpha, A.6.4) |
| F7 | `titler` | **T4** | llama.cpp `llama-server` + GGUF de títulos (Volume `models-telegram-bot/titler/`) | CPU snapshot — §4.5 |

**Por qué L4 y no T4 en v0.1:** L4 cuesta ~$0.000222/s (A.3) y es la misma familia que usarán OCR/embedder/TTS — una sola operativa. Qwen3-ASR BF16 consume ~4–5 GB de VRAM: sobra en 24 GB. T4 queda como plan B solo si los GPU snapshots (alpha) dieran guerra; el downgrade es de una línea (`gpu="T4"`).

**El flujo mínimo de captura (M0–M2) no toca GPU**: corre 100% CPU. La GPU entra con el primer audio en M3.

### 4.2 Cómo se accede a R2: `boto3`, no `CloudBucketMount` (respuesta a tu pregunta del S3 mount)

**Figura clave:** el ejemplo oficial [s3_bucket_mount](https://modal.com/docs/examples/s3_bucket_mount) usa `modal.CloudBucketMount`, que **sí soporta Cloudflare R2** (verificado: https://modal.com/docs/guide/cloud-bucket-mounts). Requiere un token de API R2 con permisos de objeto (read/write/list) en ese bucket y **sin** "Client IP Address Filtering". PERO hereda las reglas de **AWS Mountpoint**, que chocan con nuestro uso:

- ❌ **Append no permitido**: abrir un archivo en modo append → `PermissionError`.
- ❌ **seek + write no permitido**: escribir implica abrir en modo truncate.
- ⚠️ Hay que crear el directorio padre explícitamente antes de escribir (`mkdir -p`).
- ⚠️ Renombrar archivos no está soportado.
- ✅ Optimizado para **lectura secuencial de archivos grandes**.

**Decisión v0.1:** F1 accede a R2 con **`boto3` (S3 API directa)**, no con `CloudBucketMount`:

- Las notas `.md` son archivos pequeños *write-once* por **PUT completo** → exactamente lo que boto3 hace bien y Mountpoint sufre.
- Listar el inbox, subir un máster, borar un temporal: llamadas triviales de la S3 API.
- Errores claros sin la capa FUSE; control fino del `endpoint_url` de R2.

`CloudBucketMount` queda como opción para **F5 embedder en v1** (lecturas secuenciales en bloque de fotos/audio de media — exactamente su caso de uso óptimo). Patrón si se usa: escribir/montar local y **subir con boto3** al terminar.

Credenciales: **Modal Secret `r2-creds`** con `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY` — nunca en `.env` del repo, ni en código, ni en logs.

### 4.3 Pesos: Volume `models-telegram-bot` (ya descargados), NO en R2 ni en HF Hub

Inventario verificado con `modal volume ls` (2026-10-29) — los pesos YA están en el Volume:

| Prefijo | Contenido | Uso |
|---|---|---|
| `asr/Qwen3-ASR-1.7B` | safetensors BF16 + configs (formato HF estándar) | **F2 ASR (v0.1)** |
| `ocr/` | Xiaomi-OCR-0 · GLM-OCR | F3 (v1) |
| `tts/` | Qwen3-TTS-Tokenizer-12Hz · Qwen3-TTS-12Hz-1.7B-Base · Qwen3-TTS-12Hz-1.7B-CustomVoice · LFM3-Audio-2B | F4 (v1) |
| `embeddings/` | embeddinggemma-2 · jina-embeddings-v5-omni-small | F5 (v1) |
| `decision/` | LFM3-Omni-2B · laya-multilingual | T1 local (v1) |

- `models-telegram-bot` se monta con `Volume.from_name("models-telegram-bot")`; **no hace falta `download_models()`** — solo una función `check_models()` que valida que los archivos existen antes del deploy.
- R2 guarda vida y documentos, no pesos: los snapshots no aceleran la carga desde disco (A.6.1) y los fetchs de red del arranque matarían el TTL del GPU snapshot.
- ⚠️ Divergencia detectada: BOT.md A.4 eligió **baidu/Unlimited-OCR** para OCR, pero en el Volume hay descargados **Xiaomi-OCR-0** y **GLM-OCR**. Y para el eje de decisión existen 2 modelos locales (LFM3-Omni-2B, laya-multilingual) además del Jev hosted. Resolver en el momento de abrir F3/decisión — para ASR/TTS/embeddings sí coincide con lo decidido.

**Runtime del ASR (decisión 2026-10-29, reemplaza audio.cpp):** los pesos son safetensors **BF16 en formato HF estándar**. Dos rutas, sin conversiones GGUF:

1. **Primaria: Transformers con el paquete oficial `qwen-asr` / `examples/example_qwen3_asr_transformers.py`** (repo QwenLM/Qwen3-ASR). Carga directa `from_pretrained("/vol/asr/Qwen3-ASR-1.7B")` en BF16 sobre L4 — cero conversión, ideal para nuestro patrón de invocaciones esporádicas con snapshots.
2. **Serving: vLLM** para ráfagas/batches — receta oficial existe ([recipes.vllm.ai/Qwen/Qwen3-ASR-1.7B](https://recipes.vllm.ai/Qwen/Qwen3-ASR-1.7B); offline batch + online async). ⚠️ Pin de versión: hay issue documentado de incompatibilidad con vLLM 0.16.0+ (repo QwenLM/Qwen3-ASR issue #119) — fijar la versión compatible en la imagen.
3. **SGLang: no verificado** para Qwen3-ASR; no se usa hasta probarlo.

**Actualización 2026-10-30 (bloqueo real: sin solicitud de GPU L4 pendiente):** ruta primaria pasa a **Groq `whisper-large-v3-turbo`** vía endpoint OpenAI-compatible (`bot/asr.py`, CPU, secret `groq-creds`). Qwen3-ASR local queda diferido (pesos intactos en el Volume) hasta tener L4; `whisper.cpp` solo como plan B de privacidad total. Detalles operativos: Groq rechaza `.oga` (Telegram voice) → se renombra a `.ogg` al subir; límite 25 MB (flac-16k si excede); `verbose_json` da idioma detectado. ⚠️ Red local del usuario bloqueada por Groq (Cloudflare 1010) pero **egress de Modal OK** — validar siempre contra la API, no desde la máquina local.

### 4.4 Anti-cold-start aplicado (resumen de A.6)

- F0/F1: `enable_memory_snapshot=True`, `scaledown_window=60` (CPU barata).
- F2: CPU snapshot en `enter(snap=True)` para imports/init; GPU snapshot alpha + `enter(snap=False)` para `.to("cuda")` y warm-up con 1 inferencia; `scaledown_window=300`.
- Sin `min_containers`: uso esporádico; frío-rápido con snapshots > contenedor caliente pagándose.
- ⚠️ Con Transformers/torch (F2 desde 2026-10-29): en fase `snap=True` no se toca CUDA (solo imports y carga de tokenizer/config a CPU); `.to("cuda")` y warm-up van en `enter(snap=False)` — `torch.cuda.is_available()` durante un snapshot congela CUDA con 0 GPUs (A.6.7).

### 4.5 Titler (F7) — título generado para TODAS las capturas

Decisión 2026-10-29: toda captura recibe un título generado por un modelo **GGUF** pequeño servido en **T4**.

| Aspecto | Decisión |
|---|---|
| Runtime | **llama.cpp** (`llama-server`) — GGUF nativo con CUDA en T4; mismo patrón que el traductor F6 (B.11), que ya usa llama.cpp con GGUF en otro hardware |
| Pesos | Volume `models-telegram-bot/titler/` — **el modelo lo coloca el usuario** (GGUF, multilingüe ≤~2B recomendado). No fijado aún; no reutilizar los pesos de `decision/` tal cual (son BF16 HF, no GGUF) |
| HW | **T4** ($0.000164/s): generar ≤~30 tokens es tarea corta; no se gasta L4 |
| Entrada | texto crudo de la nota, o transcripción del ASR (audio); nada de OCR aún en v0.1 |
| Salida | título corto (≤ ~6 palabras, en el idioma de la captura) + slug ASCII para el nombre de archivo |
| Cuándo | **diferido en lote**: la captura jamás espera al titler (R1 de FLUJOS). F1 encola el job tras escribir; los títulos salen en la misma racha, y el contenedor T4 se reusa con `scaledown_window=300` |
| Escritura | rename en R2 con boto3 (**copy + delete** — R2/S3 no rename): nuevo nombre `YYYY-MM-DD_HH-MM-SS--{titulo-slug}.md`, update de `titulo:` y de `ruta:` en el mismo paso. La traza anota `titler` con la marca de tiempo |
| Robustez | hasta que corre el titler, el archivo conserva el slug provisional; si el titler falla, se reintenta — nunca se pierde nada y el comentario provisional sigue válido |

Coste estimado: racha de 5 min en T4 ≈ $0.0516 (A.3); con ventana de reuso el marginal por captura es irrisorio. En frío en caliente, el T4 es la opción decidida por el usuario para su uso.

---

## 5. Contratos e interfaces (lo que codifica F1)

### 5.1 Dispatch de mensajes Telegram

| Mensaje | Ruta F1 | Acción v0.1 |
|---|---|---|
| `message.text` sin URL | `nota_texto` | escribe `inbox/notas/YYYY-MM-DD_HH-MM-SS--{titulo}.md` → encola job de F7 (título) |
| `message.text` con URL | `link` | guarda nota con URL cruda y `estado: capturado` + acuse "URL guardado ✓ (descarga en v1)" — los modos `{url}`/`!{url}`/`!!{url}` de B.1 llegan en v1 |
| `message.photo` | `foto` | `getFile` → sube bytes a `inbox/fotos/YYYY-MM-DD_HH-MM-SS--foto.<ext>` + nota principal con el embed arriba → encola F7 |
| `message.voice` / `message.audio` | `audio` | `getFile` → sube máster a `inbox/audio/YYYY-MM-DD_HH-MM-SS--voz.ogg`; en M3 llama a F2 y crea la nota principal `...--voz.md` con el audio embebido arriba + transcripción → encola F7 |
| `message.document` | `doc` | guarda crudo en `inbox/docs/YYYY-MM-DD_HH-MM-SS--doc.<ext>` (procesamiento en v1) |
| `/status` | comando | últimos 3 items del inbox + contador total |
| `/help` | comando | capacidades v0.1 |

### 5.2 Frontmatter v0.1 (mínimo, común a todas)

```yaml
---
created: 2026-10-08T23:39:00.0000000Z    # OBLIGATORIO en todas las capturas: ISO-8601 UTC, 7 dígitos fraccionarios
titulo: idea para el beat de la escala     # slug provisional hasta que llega el título de F7 (título generado)
tipo_captura: texto | foto | audio | document | link
canal: telegram
telegram_msg_id: 44821
estado_vital: incubadora                  # Eje 4 FLUJOS §2
ruta: inbox/notas/2026-10-08_23-39-00--idea-para-el-beat.md
traza: [W1]                               # aún sin puertas Jev en v0.1
---
<cuerpo libre / transcripción cruda / referencia de ruta>
```

Regla dura: **todo lo capturado lleva el número de la fecha DOS veces** — en el nombre del archivo (`YYYY-MM-DD_HH-MM-SS--`) y en el frontmatter (`created:`). Formato exacto de `created` (como tu ejemplo de Obsidian): `YYYY-MM-DDTHH:MM:SS.0000000Z`, UTC con 7 dígitos fraccionarios. Se genera con `dt.strftime("%Y-%m-%dT%H:%M:%S.%f") + "0Z"` (`%f` son 6 dígitos, se les añade un `0`).

En v1 estos campos crecen hacia los de FLUJOS §9 (intención, horizonte, familia). **v0.1 no clasifica:** captura es barata, el triaje viene después (R1 + R2).

### 5.3 Contrato `Transcriber` (B.11), v0.1

```
asr(audio_path: str) -> {"text": str, "language": str,
                         "model": "qwen3-asr-1.7b-bf16",
                         "segments": [...]|None}
```

Sin Groq ni proveedores externos en v0.1 (un secreto menos, cero datos saliendo del stack); el fallback externo opt-in queda definido en v1 (M6).

---

## 6. Integraciones — setup exacto

### 6.1 Cloudflare R2

1. `wrangler login`
2. `wrangler r2 bucket create bucket-prueba` — verificar ubicación con `wrangler r2 bucket info bucket-prueba` (la zona de Modal importa poco para escritura, pero anótala).
3. **Token de API R2**: dashboard cloudflare.com → Perfil → API Tokens → plantilla **"Cloudflare R2 Token"**: *Object Read & Write* restringido **sólo** a `bucket-prueba`. El filtro de IP del cliente debe quedar desactivado (Modal sale de IPs dinámicas de AWS; lo exige Mountpoint y boto3 también lo agradece).
4. Obtener el **Account ID** (dashboard, derecha) — con él se construye el `endpoint_url`.
5. Las 3 variables → **Modal Secret `r2-creds`** (§6.2). Nunca en `.env` del repo ni en el código.
6. Cuardar la dirección del token sin "Account Restricted"? — re stringido a bucket y permisos de objeto es lo mínimo privilegiado.

### 6.2 Modal

1. `pip install modal` + `modal setup`.
2. Secretos:
   ```bash
   modal secret create r2-creds R2_ACCOUNT_ID=... R2_ACCESS_KEY_ID=... R2_SECRET_ACCESS_KEY=...
   modal secret create telegram-creds TELEGRAM_TOKEN=...
   # en M5, al integrar Jev:
   modal secret create typesafe-creds TYPESAFE_API_KEY=...
   ```
3. Webhook: tras `modal deploy`, obtener URL pública de F0 y registrarla en Telegram:
   ```bash
   TOKEN_SECRET="$(openssl rand -hex 32)"
   curl "https://api.telegram.org/bot${TELEGRAM_TOKEN}/setWebhook" \
        -d url="https://<modal-url>/<path>" \
        -d secret_token="${TOKEN_SECRET}"
   ```
   F0 valida el header `X-Telegram-Bot-Api-Secret-Token`; sin él → 403. El `TOKEN_SECRET` también va en un Modal Secret (`telegram-webhook-secret`): no se re-deriva ni reaparece en repo.
4. **Allowlist de `user_id`**: rechazar 403 a todo `user_id` distinto del tuyo en `config.py` (es un archivo de TU vida, no un bot público).

### 6.3 TypeSafe (Jev) — M5, no antes

- SDK Python documentado en [docs.typesafe.ai](https://docs.typesafe.ai/introduction/quickstart): primitivas `Choice` / `Score` / `Noul`, **una llamada con varias preguntas** sobre el mismo estado (FLUJOS §3.4).
- Primera aplicación: `P2/P3/P4` en **una** llamada cuando el turno sea triaje diferido de audio. Frontera: Jev decide, nunca redacta (B.11).
- Model aliases de TypeSafe: fijar en código con el `model` por defecto documentado; no seleccionar proveedores arbitrarios con ese campo (restricción B.11).
- Orden de integración: **captura → ASR → decisión** (barato antes que caro, FLUJOS §3).

### 6.4 Imagen de M3 (ASR)

- Imagen Modal: `python3.11` + `pip install qwen-asr transformers ffmpeg` (o adaptar el ejemplo oficial del repo QwenLM/Qwen3-ASR) con `Image.imports()` para que queden en el snapshot. Pesos YA en el Volume (§4.3) — cero descargas en runtime.
- ⚠️ Pin de dependencias conocido: el paquete `qwen-asr` pidió `transformers==4.57.6`, mientras el soporte nativo de Qwen3-ASR en Transformers llegó en 5.13.0 (repo issue #220) — fijar la combinación que funcione al abrir M3.
- Entrada de audio: normalizar a **mono 16 kHz** con ffmpeg en F1 (copia temporal en disco efímero). El máster OGG/Opus original **jamás** se re-codifica (FLUJOS §4.4).

---

## 7. Hitos de construcción (DOD = criterio de listo)

| M | Entrega | DOD |
|---|---|---|
| **M0** | Andamio: repo `bot/` (`webhook.py`, `worker.py`, `r2.py`, `telegram.py`, `formats.py`, `smoke.py`), `pyproject` con `uv`, bucket `bucket-prueba` creado, secretos `r2-creds` + `telegram-creds` cargados | `modal run bot/smoke.py` escribe y re-leer un objeto en `bucket-prueba` vía boto3; `pytest` cliente R2 con mock no rompe pipeline |
| **M1** | F0 webhook + F1 worker: mensaje de texto → nota en `inbox/notas/` + acuse "Guardado ✓" | 3 mensajes → 3 `.md` con frontmatter completo listables en R2; webhook responde ≤1 s; 403 sin `X-Telegram-Bot-Api-Secret-Token` y con `user_id` extraño |
| **M2** | Fotos y audios → máster en `inbox/{fotos,audio}/` + nota de 1 línea; `/status` y `/help` | foto subida byte-to-byte idéntica al original; audio OGG intacto (máster sin transcodificar); `/status` cuenta y lista el inbox |
| **M3** | **ASR real (F2, Groq)**: audio → transcript → nota principal `...--voz.md` con el audio embebido arriba + sección "Transcripción (fiel)" | Nota de voz real en ES transcrita legible con idioma detectado (verificado 2026-10-30); Qwen3-ASR local diferido hasta L4 |
| **M4** | **Titler F7 (T4, llama.cpp + GGUF en `titler/`)**: títulos diferidos + rename R2 y update de `titulo:`/`ruta:`; `/borrar <id>` y demás comandos | toda captura existente en el inbox termina con título generado y el archivo renombrado; rename sin perder referencias `id`; borrado auditado en log |
| **M5** | **Jev integrado** (una llamada por audio con Choice): en análisis, tag en `traza` en frontmatter | decisión visible en `traza: [W1, P2, P4]`; confianza baja → sigue como nota y pregunta "¿nota u otra cosa?" (salida `dudo` FLUJOS) |
| **v1+** | OCR (F3), embeddings (F5), traducción (F6), recordatorios B.12, URLs `!{}` (B.1), tareas B.13, `/leer` TTS | roadmapped en BOT.md |

Orden recomendado: **M0 → M1 → M2 sin pausa** (CPU puro, riesgo bajo). **Pausa de revisión antes de M3** (primera función GPU — validar la operativa on-cloud vs plan de presupuesto).

---

## 8. Riesgos y decisiones por fijar

1. **GPU snapshots (alpha)**: si M3 falla, degradar F2 a solo CPU snapshot — con Transformers/torch el arranque pesa más que con un binario C++, por eso el GPU snapshot vale más aquí; es ganancia, no bloqueo.
2. **"Otro" con confianza baja**: en v0.1 nada se descarta — audio ambiguo queda como nota con transcripción y `estado_vital: incubadora`, nunca perdido (REGLA R3 de FLUJOS).
3. **Zona horaria**: fijar en `config.py` / Modal Secret (`TIMEZONE` TZ IANA) **antes** de M4; todas las fechas de frontmatter dependen de ella. Recomendado: la del dispositivo del usuario (config explícita), no UTC.
4. **Límite Bot API**: `getFile` está limitado a ~20 MB con el Bot API estándar. Las notas de voz de Telegram normales quedan por debajo; audios/DIDs largos darán guerra — si llega a molestar, el **local Bot API server** (B.1.3) sube el límite a 2 GB (v2). Monitorear desde M2.
5. **Presupuesto Modal**: Starter = $0/mes + $30 crédito. Estimación A.3: una racha de 5 min en F2 (L4) por dicio ativo duración ≤$0.05. Con uso personal, el coste dominante será cold starts, mitigades por snapshots, no horas corridas de GPU.
6. **Offline (sin acceso a Modal en tu red / IP bloqueada)**: no aplica al caso normal; si te diera problema de red, revisar proxy/WARP antes de depender del deploy diario.
7. **`.env` existente**: definir si se convierte en placeholder de **sólo PLAY local no secrets** o se elimina — el repo nunca debe cargar claves reales (los valores reales van a Modal Secrets).

---

## 9. Estructura propuesta del código (scaffold M0)

```text
bot/
  __init__.py
  webhook.py        # F0 — FastAPI. Validar secret + user. Solo parsear y encolar.
  worker.py         # F1 — dispatcher: nota_texto | foto | audio | document | link
  asr.py            # F2 — función L4, qwen-asr/Transformers (a partir de M3)
  titler.py         # F7 — títulos con GGUF en T4 llama.cpp (a partir de M4)
  r2.py             # cliente boto3 + helpers put/get/list/delete
  telegram.py       # helpers API Bot: get_file, sendMessage
  formats.py        # generador de nota Markdown + frontmatter (§5.2)
  smoke.py          # prueba R2 escritura/lectura (M0)
  test_worker.py    # fixtures de updates Telegram para tests locales
pytest/
  test_r2.py        # (opcional) unit tests con mock de boto3
pyproject.toml
Makefile            # deploy / smoke / test
```

Estilo: funciones Modal en móbles propios (A.5), import de `modal` solo en los módulos con funciones; tests con `pytest` y fake de las llamadas externas; **ninguna clave en el repo**.

---

## 10. Checklist de arranque (M0, copiable)

```bash
# 1) bucket (requiere wrangler login)
wrangler r2 bucket create bucket-prueba
wrangler r2 bucket list

# 2) modal auth + secretos (los valores SE ESCRIBEN, no se guardan en shell history; usa prompts modal cuando pida)
pip install modal
modal setup
modal secret create r2-creds R2_ACCOUNT_ID=xxx R2_ACCESS_KEY_ID=xxx R2_SECRET_ACCESS_KEY=xxx
modal secret create telegram-creds TELEGRAM_TOKEN=xxx

# 3) deploy + smoke R2 (primera prueba)
modal deploy bot/webhook.py   # devuelve la URL pública de F0
modal run bot/smoke.py

# 4) registrar webhook en Telegram con secret_token
export TOKEN_SECRET="$(openssl rand -hex 32)"
curl "https://api.telegram.org/bot${TELEGRAM_TOKEN}/setWebhook" \
     -d url="https://<url-modal>/<path>" \
     -d secret_token="${TOKEN_SECRET}"
# verificación: curl "https://api.telegram.org/bot${TELEGRAM_TOKEN}/getWebhookInfo"
```

---

## Estado

- **M1/M2-media — LISTO (2026-10-30).** F0→F1 desplegados y probados e2e:
  - `bot/worker.py`: texto (nota/link), **foto → SOLO máster** `inbox/fotos/YYYY-MM-DD_HH-MM-SS--foto.<ext>` sin nota (nota solo con `/ocr` en el caption), **voz/audio → máster** `inbox/audio/…--voz.<ext>`, **doc → máster** `inbox/docs/…--doc.<ext>`; `/status`, `/help`, `/ocr`. Nada de medias se pierde esperando a M3/v1.
  - Despliegue: `modal deploy -m bot.webhook` (una sola App `tg-bot` con `telegram_update` + `process`). URL: https://kwon-lanxi--tg-bot-telegram-update.us-east.modal.run, webhook registrada en Telegram con `secret_token`.
  - **Lecciones del deploy (que casi nos cuestan un crash-looping, ver logs):** (1) la imagen de F0 debe instalar TODO lo que importe el paquete (`boto3` faltaba al importar `worker` → snapshot-crash-loop en Modal); (2) F0 y F1 deben vivir en la **misma App** (`bot/app.py` compartida) — un `spawn` cross-app desde un web-endpoint lanza `ExecutionError: not hydrated` en cada request; (3) el dispatch usa `spawn.aio` en contexto async.
  - **E2e verificado concretamentecontra `post_update.py`:** 403 sin firma · 403 firma+usuario ajeno · 200 + nota `inbox/notas/2026-10-30_00-37-13--…--…md` en R2 con frontmatter completo (created 7 dígitos, doble fecha,ruta/traza W1) · 200 en `/status`. El acuse llega al chat del propietario.
  - **Cómo probar tú desde el celular:** abre el chat del bot en Telegram y manda un texto (acuse “Guardado ✓”), una foto, una nota de voz, `/status` y `/help`; las notas salen en `inbox/` y aparecen vía Remotely Save. Frío ~6 s la primera vez; luego <1 s.
  - `pytest` 15/15 (foto solo-máster, foto+/ocr, audio-máster, doc-máster). Deploy 2026-10-30 verificado: sin crash-loop (sin `ModuleNotFoundError`), 403 sin firma correcto, snapshots restaurando.
- **OCR — LISTO (2026-10-30).** F2-OCR Groq vision (`bot/ocr.py`, CPU, `transcribe_image`) cableado a `/ocr` en caption: foto → máster + `--foto.md` con texto extraído + acuse. Fallback scout→maverick si dan de baja un modelo. Xiaomi/GLM-OCR locales diferidos hasta L4 (resuelve divergencia §4.3). Falta prueba con foto real.
- **M3 — LISTO (2026-10-30).** F2 Groq desplegado y probado con audio real: voz de 17 KB en ES → `--voz.md` con transcripción fiel + idioma `Spanish` + acuse. Detectado y corregido en vivo: Groq rechaza extensión `.oga` (se sube como `.ogg`); clave válida solo desde egress Modal (red local da Cloudflare 1010). `pytest` 17/17 (nuevos: `test_asr.py` Groq ok + 401). Script `scripts/retranscribe.py` para reprocesar un máster sin reenviar. Siguiente: **M4** titler.
- **M0 — LISTO (2026-10-29).** Ejecutado el checklist de §10 con resultado:
  - Scaffold del §9 en pie: `bot/webhook.py` (F0 con 403 de firma+allowlist, dispatch en M1), `bot/worker.py` (stub F1), `bot/r2.py`, `bot/telegram.py`, `bot/formats.py`, `bot/smoke.py`, `bot/config.py`, `pyproject.toml` (uv), `Makefile` y `tests/`.
  - DOD de M0 superado en doble vía: `python -m bot.smoke` (local, `.env`) **y** `modal run -m bot.smoke` (runtime Modal con `r2-creds` + `telegram-creds`) — PUT/GET byte a byte/LIST/DELETE contra `bucket-prueba` PASS. En Modal, el comando es con flag de módulo (`modal run -m bot.smoke`): modal suelto sube un solo archivo y rompe los imports relativos.
  - Modal Secrets creados desde `.env` (script `scripts/create_modal_secrets.py`, sin imprimir valores): `r2-creds` (R2_ENDPOINT/BUCKET/ACCESS_KEY/SECRET_KEY), `telegram-creds` (TELEGRAM_TOKEN/OWNER_IDS/ARCHIVE_CHAT_ID/TZ_NAME), `telegram-webhook-secret` (TELEGRAM_WEBHOOK_SECRET generado y persistido en `.env` local para setWebhook).
  - ⚠️ Nota Windows: la consola cp1252 no imprime símbolos Unicode de Modal — correr `PYTHONIOENCODING=utf-8` antes de `modal run`.
  - `pytest` 7/7 (formatos: created de 7 dígitos, slug, embed-arriba; R2: roundtrip con moto).
- **Siguiente: M1** — implementar el dispatch real en F0→F1 (texto → `inbox/notas/` + acuse), deploy del webhook y registro en Telegram con `secret_token` (§10 paso 4).
- Pendiente de fijar (no bloquea M1): GGUF del titler (M4); divergencia OCR de A.4 vs Volume (v1).
