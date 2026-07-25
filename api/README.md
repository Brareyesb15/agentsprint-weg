# `api/` — carril de ROBINSON

Está vacío a propósito: es tu carril y nadie más lo toca.

## Qué construir

Los cuatro endpoints de `team/CONTRATOS.md` § 4:

| Método | Ruta | Body | Respuesta |
|--------|------|------|-----------|
| POST | `/chat` | `{ session_id, message, image?: base64 }` | SSE |
| POST | `/upload` | multipart `file` | `{ image_id }` |
| GET | `/health` | — | `{ ok: true }` |
| POST | `/eval/run` | `{ set: "doradas" }` | SSE |

## Lo que ya está hecho y puedes usar

- **`tools/fake_stream.py`** — un servidor que emite los **8 tipos de evento** con
  datos falsos que siguen el contrato exacto. Constrúyele el front a esto:

  ```bash
  .venv\Scripts\python.exe -m uvicorn tools.fake_stream:app --port 8000
  ```

  ```bash
  curl -N http://localhost:8000/chat
  ```

  También hay `GET /eventos`, que devuelve los eventos de golpe sin SSE — útil para
  arrancar el panel sin pelear con el streaming.

- **`agent.events.Emitter`** — ya serializa los eventos. **No armes el JSON a mano:**
  usa `Event.to_sse()`, que produce `data: {...}\n\n` como manda el contrato.

- **`agent.loop.Agente.responder()`** — el agente ya funciona. Para conectarlo, pásale
  un `Emitter` cuyo `sink` empuje a la cola del SSE. Mira `scripts/prueba_agente.py`:
  hace exactamente eso, pero pintando en consola.

- **`evals.harness.correr()`** — recibe un `responder` inyectado. Para `/eval/run`
  no reimplementes nada: pásale el agente y un `Emitter`.

## Dos cosas que ahorran depuración

1. **CORS.** El front va en el 5173 y la API en el 8000. Sin CORS el navegador
   bloquea el SSE en silencio. `tools/fake_stream.py` ya lo tiene configurado — copia esa parte.
2. **La respuesta final NO llega en streaming desde el modelo.** El guard tiene que
   verificarla completa antes de que se vea. Los eventos `token` son la respuesta ya
   verificada, troceada. No esperes tokens durante la fase de consulta: ahí lo que
   llega es `thought`, `tool_call` y `tool_result`.
