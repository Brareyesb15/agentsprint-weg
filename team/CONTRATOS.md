# CONTRATOS DE INTERFAZ — v1

**Dueño: Brandon.** Cambios: se editan acá + línea `⚠ CONTRATO:` en el AHORA + aviso verbal.
Todos construyen contra ESTE documento, **no** contra la implementación del otro.

Este documento define **el sobre, no la carta**: ningún campo de acá menciona el dominio.
Cuando llegue el reto solo se llena la sección 7.

---

## 1. Eventos que el backend envía al front (SSE)

Todo evento tiene la misma envoltura:

```json
{ "type": "<tipo>", "ts": 1753400000000, "data": { } }
```

`ts` = epoch en **milisegundos**.

Ocho tipos, ninguno depende del dominio:

| # | `type`        | `data`                                              |
|---|---------------|-----------------------------------------------------|
| 1 | `thought`     | `{ text }`                                          |
| 2 | `tool_call`   | `{ id, tool, args, motivo }`                        |
| 3 | `tool_result` | `{ id, tool, ok, ms, summary, sources[] }`          |
| 4 | `verify`      | `{ ok, checked, confirmed, detail }`                |
| 5 | `token`       | `{ text }`                                          |
| 6 | `citation`    | `{ doc, section, page, snippet }`                   |
| 7 | `memory`      | `{ key, value }`                                    |
| 8 | `error`       | `{ where, message, recoverable }`                   |

Detalles que no se negocian el sábado:

- **`tool_call.motivo`**: UNA frase corta en español, el *por qué* de la acción.
  Es lo que convierte el panel en línea de tiempo narrada. Obligatorio.
- **`tool_call.args` NO incluye `motivo`.** El modelo lo manda dentro de los
  argumentos, pero el agente lo saca antes de emitir. Puedes pintar
  `Object.entries(args)` directo sin que el motivo salga duplicado.
- **`verify` puede llegar DOS veces en un mismo turno.** El primero es el veredicto
  que disparó el reintento (`ok: false`); el último es el definitivo. Pinta la
  secuencia — *bloqueó → reintentó → confirmó* es la mejor escena de la demo — y
  quédate con el último para el estado final.
- **`error` con `recoverable: false`** significa que el turno murió (cuota agotada,
  red caída). Va seguido de un `verify` en rojo y un `token` con una respuesta
  honesta: el agente nunca deja la pantalla en blanco.
- **`tool_call.id`**: string. El `tool_result` correspondiente trae **el mismo `id`**,
  para que el panel empareje llamada y resultado.
- **`tool_result.ms`**: entero, milisegundos que tardó la herramienta.
- **`verify.checked` y `verify.confirmed` son ENTEROS** (cuentas), para que el panel
  pinte "4/4 valores confirmados". `verify.detail` es un string legible en español.
- **`token`**: fragmento de la respuesta final. Llega en streaming.
  El front concatena; no asumas que cada token es una palabra.

## 2. Forma de una fuente (`source`)

Usada en `tool_result.sources[]` y en el evento `citation`.

```json
{ "doc": "<archivo o referencia>",
  "section": "<sección>",
  "page": 2,
  "snippet": "<texto EXACTO de la fuente>" }
```

- `page` es número **o `null`** (hay fuentes sin paginación).
- `snippet` tiene que ser **texto literal** de la fuente, no un resumen.
  El guard de citas verifica los números contra este campo: si el snippet es
  parafraseado, el guard falla y tiene razón en fallar.

## 3. Convención de firma de TODA herramienta

**Entrada:** argumentos validados con esquema (Pydantic) + `motivo: str` (obligatorio).

**Salida:**

```json
{ "result": <cualquier cosa>,
  "sources": [ <source>, ... ],
  "uncertainty": <string|null> }
```

**REGLA DURA:** si una herramienta afirma algo del mundo, DEBE devolver de dónde lo
sacó en `sources`. Si no puede, devuelve `uncertainty` explicando por qué.

Gracias a esto el guard de citas funciona con **cualquier** herramienta futura,
incluidas las que se inventen mañana cuando sepamos el reto.

Además, cada herramienta se registra con una bandera:

- `es_conocimiento=True` → esta herramienta consulta el corpus. El guard exige que
  al menos una así se haya llamado en el turno antes de dejar emitir una afirmación.
- `usa_modelo=True/False` → para poder decir en el pitch cuántas herramientas son
  código determinista. Aspiramos a que la mayoría sean `False`.

## 4. Endpoints

| Método | Ruta         | Body                                        | Respuesta                       |
|--------|--------------|---------------------------------------------|---------------------------------|
| POST   | `/chat`      | `{ session_id, message, image?: base64 }`   | SSE con los eventos de arriba   |
| POST   | `/upload`    | multipart `file`                            | `{ image_id }`                  |
| GET    | `/health`    | —                                           | `{ ok: true }`                  |
| POST   | `/eval/run`  | `{ set: "doradas" }`                        | SSE (mismos eventos + `verify`) |

Content-Type del SSE: `text/event-stream`. Cada evento va como
`data: <json en una línea>\n\n`.

## 5. Configuración (nombres exactos, para que nadie invente)

```
GOOGLE_API_KEY_1..4      las cuatro keys, con rotación
MODEL_NAME               nombre del modelo (JAMÁS escrito en el código)
MODEL_NAME_LIGHT         modelo barato para pasos de texto liviano (opcional)
API_PORT=8000            backend
UI_PORT=5173             front
DATA_DIR=./data
IMAGE_MAX_SIDE=768       lado mayor al que se reescala la foto antes de enviarla
GUARD_TOLERANCIA=0.02    tolerancia relativa al comparar unidades equivalentes
```

## 6. Contrato interno del agente (para quien toque `agent/`)

- `agent.events.Emitter` es el único que serializa eventos. Nadie arma JSON a mano.
- `agent.guardrails.verificar()` corre **antes** de emitir la respuesta final.
  Devuelve `VerifyResult`; el loop lo convierte en el evento `verify`.
- `agent.memory.SessionMemory` guarda hechos del turno y emite `memory`.
- El registro de herramientas vive en `agent/tools/__init__.py`.

## 7. Espacios a llenar mañana cuando llegue el reto

- [ ] **Herramientas de dominio**: nombre, argumentos, qué devuelve, `es_conocimiento`, `usa_modelo`
- [ ] **Formato de los archivos de `data/`**: qué campos trae el corpus
- [ ] **Qué hechos guarda la memoria de sesión** (las `key` del evento `memory`)
- [ ] **Preguntas doradas** en `evals/sets/doradas.json`
- [ ] **La frase**: "Nuestro agente ayuda a ___ a hacer ___."
