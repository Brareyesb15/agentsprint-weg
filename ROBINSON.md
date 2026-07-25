# Robinson — empieza acá (`api/` + `ui/`)

Léelo completo antes de escribir código. Son 4 minutos y te ahorra media hora.

## Qué construyes, en una frase

Una pantalla donde el vendedor sube la **foto de una placa de motor**, escribe su
pregunta, y ve **en vivo** cómo el agente busca en el catálogo de WEG, verifica cada
cifra contra su fuente y responde con citas clicables.

El panel de trazas **no es un extra**: es la evidencia del checklist técnico (20% de
la nota) y es el espectáculo de la demo. Sin él, los segundos de espera son silencio.

---

## La decisión ya está tomada: UN archivo HTML, sin npm

**No uses React ni Vite.** Tres razones, en orden de peso:

1. `npm install` en el wifi del auditorio es una ruleta. Si sale mal perdiste 20 de
   tus 60 minutos y no tienes nada que mostrar.
2. Necesitas una lista de eventos y una burbuja de chat. Eso son ~150 líneas de JS
   plano. React acá no compra nada.
3. **Si sirves el HTML desde FastAPI, el CORS desaparece.** Un proceso, un puerto,
   un comando. El CORS mal configurado es el sumidero de tiempo #1 en hackathons y
   falla *en silencio*.

**Excepción única:** si ya tienes una plantilla de Vite cacheada en tu disco y eres
mucho más rápido ahí, úsala. Pero **jamás** un `npm install` fresco hoy.

Estructura:

```
api/main.py       FastAPI: /chat, /upload, /health, /eval/run + sirve ui/
ui/index.html     TODO el front acá: chat, upload, panel, chips de cita
```

Montar el estático (esto es lo que mata el CORS):

```python
from fastapi.staticfiles import StaticFiles
# ¡al FINAL del archivo, después de declarar las rutas!
app.mount("/", StaticFiles(directory="ui", html=True), name="ui")
```

Luego `http://localhost:8000` sirve tu HTML y `http://localhost:8000/chat` es la API.
Mismo origen. Cero CORS.

---

## Puedes empezar YA, sin esperar el agente

Hay un emisor de eventos **falsos** que cumple el contrato exacto:

```bash
.venv\Scripts\python.exe -m uvicorn tools.fake_stream:app --port 8000
```

- `GET /eventos` → los 8 eventos de golpe, en un JSON. **Empieza por acá**: maqueta
  con datos quietos antes de pelear con el streaming.
- `GET /chat` o `POST /chat` → los mismos eventos por SSE, uno cada 0,45 s.

Si tu panel pinta bien contra esto, pinta bien contra el agente real. El sobre es el
mismo.

---

## Los 8 eventos, con ejemplo real

Envoltura siempre igual. `ts` en epoch **milisegundos**:

```json
{ "type": "tool_call", "ts": 1753400000000, "data": { } }
```

| `type` | `data` real | Cómo pintarlo |
|---|---|---|
| `thought` | `{"text": "Voy a consultar la documentación antes de afirmar nada."}` | gris, chico, es contexto |
| `tool_call` | `{"id":"a1b2c3d4","tool":"buscar_motor","args":{"hp":10,"polos":4},"motivo":"La placa marca 1750 RPM, busco equivalentes de 4 polos."}` | nombre de la herramienta **y el `motivo` grande** — el motivo es lo que convierte el panel en historia narrada |
| `tool_result` | `{"id":"a1b2c3d4","tool":"buscar_motor","ok":true,"ms":41,"summary":"2 fragmento(s): catalogo_W22.pdf / Tabla de rendimiento · 2 fuentes","sources":[…]}` | ok/falla, los `ms`, el `summary`, cuántas fuentes |
| `verify` | `{"ok":true,"checked":3,"confirmed":3,"detail":"3/3 valores confirmados en catalogo_W22.pdf, pág. 47"}` | **lo más importante de la pantalla.** Verde con "3/3", rojo con el `detail` completo cuando bloquea |
| `token` | `{"text":"El equivalente es el "}` | concatena en la burbuja. **No asumas que cada token es una palabra** |
| `citation` | `{"doc":"catalogo_W22.pdf","section":"Tabla de rendimiento","page":47,"snippet":"W22 IE3 10 HP 4P 132M — rendimiento 91,0 / 91,7 / 91,7"}` | chip clicable `doc · sección · pág`. Al abrirlo, el `snippet` literal |
| `memory` | `{"key":"tarifa_kwh","value":"814,10 COP"}` | franja aparte tipo `MEMORIA: tarifa = 814,10 COP`. Se usa a propósito en la demo |
| `error` | `{"where":"agente","message":"…","recoverable":false}` | rojo, con `recoverable` visible |

Forma de un `source` (en `tool_result.sources[]` y en `citation`):

```json
{ "doc": "catalogo_W22.pdf", "section": "Tabla de rendimiento",
  "page": 47, "snippet": "texto LITERAL de la fuente" }
```

`page` puede ser `null` (hay fuentes sin paginación). `snippet` es texto literal, no
un resumen — el guard verifica los números contra ese campo.

---

## El lector de streaming — la trampa que cuesta media hora

**`EventSource` NO sirve.** Solo hace GET, y `/chat` es **POST con body** porque la
imagen va en base64. Usa `fetch` + `ReadableStream`:

```js
async function preguntar(mensaje, imagenBase64) {
  const r = await fetch("/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: "demo", message: mensaje, image: imagenBase64 }),
  });

  const reader = r.body.getReader();
  const dec = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += dec.decode(value, { stream: true });

    // Los eventos SSE se separan por línea en blanco. OJO: un chunk puede traer
    // medio evento, así que hay que acumular y solo procesar los completos.
    const partes = buffer.split("\n\n");
    buffer = partes.pop();                       // el último queda incompleto
    for (const p of partes) {
      const linea = p.split("\n").find((l) => l.startsWith("data: "));
      if (linea) pintar(JSON.parse(linea.slice(6)));
    }
  }
}
```

Ese `buffer = partes.pop()` es lo que evita el `JSON.parse` roto a mitad de demo.

---

## Cinco trampas verificadas

1. **`verify` puede llegar DOS veces en un turno.** El primero es el veredicto que
   disparó el reintento (`ok:false`); el último es el definitivo. **Pinta la
   secuencia** — *bloqueó → reintentó → confirmó* es la mejor escena de la demo — y
   quédate con el último para el estado final.
2. **Empareja `tool_call` con `tool_result` por el campo `id`, no por orden.** Puede
   haber varias herramientas en vuelo.
3. **`tool_call.args` ya NO trae `motivo` adentro.** Puedes pintar
   `Object.entries(args)` directo sin que salga duplicado.
4. **La respuesta final NO llega en streaming desde el modelo.** El guard la verifica
   completa antes de que se vea. Durante la fase de consulta llegan `thought`,
   `tool_call` y `tool_result`; los `token` llegan al final, de golpe pero troceados.
   No pongas un spinner que asuma tokens desde el segundo uno.
5. **`error` con `recoverable:false`** significa que el turno murió (cuota agotada,
   red caída). Viene seguido de un `verify` en rojo y un `token` con una respuesta
   honesta. El agente nunca deja la pantalla en blanco — no la dejes tú tampoco.

---

## Endpoints que tienes que exponer

| Método | Ruta | Body | Respuesta |
|---|---|---|---|
| POST | `/chat` | `{session_id, message, image?: base64}` | SSE de los 8 eventos |
| POST | `/upload` | multipart `file` | `{image_id}` |
| GET | `/health` | — | `{ok: true}` |
| POST | `/eval/run` | `{set: "doradas"}` | SSE (mismos eventos) |

**Si vas justo de tiempo, `/upload` es opcional:** manda la imagen en base64 dentro
de `/chat` y listo. Un `<input type="file">` + `FileReader.readAsDataURL` te da el
base64 sin backend. **No reescales la imagen en el navegador:** el agente ya lo hace
(baja una foto de 8 MB a ~2 KB).

Para conectar el agente real cuando exista, mira `scripts/prueba_agente.py`: hace
exactamente lo que necesitas, pero pintando en consola. Le pasas un `Emitter` cuyo
`sink` empuje a la cola del SSE, y `Event.to_sse()` ya produce el
`data: {...}\n\n` que manda el contrato. **No armes el JSON a mano.**

---

## Orden de trabajo, con reloj

| Min | Qué |
|---|---|
| 0–5 | Levanta `tools.fake_stream` y abre `GET /eventos` en el navegador. Mira los datos reales |
| 5–20 | `ui/index.html`: burbuja de chat + panel a la derecha, pintando el JSON quieto de `/eventos` |
| 20–35 | Cambia a streaming con el lector de arriba, contra `POST /chat` del falso |
| 35–45 | `api/main.py` con `/health` y `/chat`, sirviendo `ui/` como estático |
| 45–60 | Conecta el agente real. **Modo presentación:** pantalla completa, tarjetas grandes, legibles a 3 metros |

## Criterio de listo

- Pinta los **8 tipos** de evento con el emisor falso.
- Tiene **modo presentación** legible a 3 metros — es el modo con el que se corre el
  eval frente al jurado.
- Un `verify` en rojo se ve **distinto y obvio** frente a uno en verde. Ese contraste
  es el argumento entero del proyecto.

## Si algo del contrato no te alcanza

Pídeselo a Brandon. **No inventes un campo**: si lo inventas, el otro lado no lo va a
estar esperando. El contrato completo está en `team/CONTRATOS.md`.
