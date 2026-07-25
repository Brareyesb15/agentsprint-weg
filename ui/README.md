# `ui/` — carril de ROBINSON

Está vacío a propósito: es tu carril y nadie más lo toca.

React + Vite (Streamlit queda como reserva, sin votación).
**Cero tiempo en hosting:** corriendo en el portátil es suficiente.

## El panel de trazas es la mejor inversión del proyecto

Hace tres trabajos con un solo desarrollo:

1. Es la **evidencia del checklist técnico**, que pide componentes *funcionando*, no nombrados.
2. Es la **prueba de que nada está simulado**, que es lo que castiga la nota de código.
3. Es el **espectáculo de la demo**: convierte los segundos de espera en algo narrable.

Bonus: *"full traceability"* es lenguaje del propio producto de los jueces.

## Criterio de "listo"

- Pinta los **8 tipos de evento** con datos falsos de `tools/fake_stream.py`.
- Tiene **modo presentación**: pantalla completa, tarjetas grandes, legibles a 3 metros.
  Es el modo con el que se corre el eval frente al jurado.

## Qué mostrar de cada evento

| Evento | Qué se ve |
|--------|-----------|
| `thought` | texto en gris, chico, es contexto |
| `tool_call` | nombre de la herramienta **y el `motivo` bien visible** — el `motivo` es lo que convierte el panel en historia narrada |
| `tool_result` | ok/falla, los `ms`, el `summary`, y cuántas fuentes trajo |
| `verify` | **lo más importante de la pantalla.** Verde con "4/4 valores confirmados en ...", rojo con el `detail` cuando bloquea |
| `token` | se concatena en la burbuja de respuesta. No asumas que cada token es una palabra |
| `citation` | chip clicable: `doc · sección · pág`. Al abrirlo, el `snippet` literal |
| `memory` | franja aparte, tipo "MEMORIA: clave = valor". Se usa a propósito en la demo |
| `error` | rojo, con `recoverable` visible |

## Dos advertencias

- Empareja `tool_call` con `tool_result` **por el campo `id`**, no por orden de
  llegada: puede haber varias herramientas en vuelo.
- `verify.checked` y `verify.confirmed` son **enteros**, para que puedas pintar "4/4".
  El orden en que llegan los eventos es a propósito: `verify` → `citation` → `token`,
  para que se vea que se verificó **antes** de que apareciera la respuesta.
