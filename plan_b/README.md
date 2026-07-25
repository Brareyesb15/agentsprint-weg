# `plan_b/` — respaldo desechable. NO es el carril de nadie.

**Robinson: esto NO reemplaza tu trabajo y no debes construir sobre esto.**

Lo escribió Brandon porque a media mañana el agente ya funcionaba y no había forma de
mostrarlo. Es un seguro contra el peor escenario: llegar al pitch sin pantalla.

## La regla

- **Tu `api/main.py` + `ui/index.html` son los oficiales.** En cuanto existan y
  funcionen, **este directorio se borra** y nadie lo extraña.
- **Corre en el puerto 8010**, no en el 8000, justamente para que puedas tener tu
  servidor arriba al mismo tiempo sin pelearte el puerto.
- **No lo edites.** Si le falta algo, es señal de que ese algo va en el tuyo.

## Para qué te sirve igual

Como **referencia funcionando**. Levántalo, úsalo, y roba lo que quieras:

```bash
.venv\Scripts\python.exe -m uvicorn plan_b.servidor:app --port 8010
```

Luego abre http://localhost:8010

Tres cosas de ahí que te ahorran tiempo y ya están resueltas:

1. **`plan_b/servidor.py`** muestra cómo conectar el agente a SSE. El detalle que
   importa: `Agente.responder()` es **síncrono y bloqueante**, así que corre en un
   hilo y empuja los eventos a una `queue`; el generador async la drena con
   `asyncio.to_thread`. Si lo llamas directo, el front no ve nada hasta el final y la
   espera se siente como un cuelgue.
2. **El `StaticFiles` montado al final** del archivo. Servir el HTML desde el mismo
   origen elimina el CORS por completo — no hay middleware que configurar.
3. **El lector de streaming en `index.html`**, con el `buf = partes.pop()` que evita
   el `JSON.parse` roto cuando un chunk trae medio evento.

## Qué le falta a propósito

Lo mínimo para que la demo exista, nada más:

- Sin `/upload` — la imagen va en base64 dentro de `/chat`.
- Sin `/eval/run`.
- Sin modo presentación.
- Estilo funcional, no diseñado. **Ahí es donde tú ganas.**
