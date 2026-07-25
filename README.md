# AgentSprint — agente técnico con citas verificadas

Agente que responde preguntas técnicas sobre productos **solo** con lo que está en
la documentación oficial, y **verifica cada cifra contra su fuente antes de mostrarla**.

> El reto concreto lo entregan los organizadores el sábado 25-jul a las 8:00 AM.
> Lo que está en este repo es todo lo que no depende del reto. Los espacios a llenar
> están marcados en `team/CONTRATOS.md` sección 7 y en `PLAN.md`.

---

## Correr en dos comandos

```bash
.venv\Scripts\python.exe -m pytest tests/ -q
```

```bash
.venv\Scripts\python.exe -m evals.harness --set juguete --fake
```

El primero corre los 99 tests. El segundo corre el eval sobre un corpus de juguete
**sin necesidad de API key** (corpus, búsqueda y guard son reales; solo el texto del
modelo está simulado).

Con `.env` configurado, la prueba de verdad:

```bash
.venv\Scripts\python.exe scripts/prueba_entorno.py
```

```bash
.venv\Scripts\python.exe scripts/prueba_agente.py
```

Panel de trazas contra eventos falsos (para el front, sin agente):

```bash
.venv\Scripts\python.exe -m uvicorn tools.fake_stream:app --port 8000
```

## Puesta en marcha desde cero

```bash
copy .env.example .env
```

Luego se pega la key de Gemini en `GOOGLE_API_KEY_1` (se crea en
https://aistudio.google.com/apikey). El `.env` está en `.gitignore` y **nunca** se commitea.

---

## Cómo funciona

```
pregunta (+ foto opcional)
        |
        v
  [ reescalado de imagen ]      una foto de celular sin tocar cuesta miles de tokens
        |
        v
  FASE CONSULTA  tool_config = ANY  -> el modelo está OBLIGADO a usar herramientas
        |                              no puede responder de memoria
        |  buscar_conocimiento -> fragmentos + cita (doc, sección, snippet literal)
        |  leer_documento      -> sección completa
        |  <herramientas de dominio: se agregan el sábado>
        v
  FASE CIERRE    sin herramientas   -> redacta usando SOLO lo recolectado
        |
        v
  +---------------------------------------------------------------+
  |  GUARD DE CITAS  (determinista, cero llamadas al modelo)      |
  |  1. ¿hubo consulta al conocimiento en este turno?             |
  |  2. ¿cada cifra dicha aparece en la evidencia citada?         |
  |     - normaliza coma/punto decimal y separador de miles       |
  |     - convierte unidades: 3,7 kW y 5 HP son el mismo valor    |
  |     - acepta cifras que vinieron de cálculo determinista      |
  |  falla -> un reintento -> si no, degradación honesta          |
  +---------------------------------------------------------------+
        |
        v
  eventos SSE: verify -> citation -> token   (en ese orden a propósito:
                                              se ve que se verificó ANTES)
```

**La respuesta final no se transmite token por token desde el modelo**, y es
deliberado: el guard tiene que verificarla completa antes de que el usuario la vea.
Medio segundo más de espera a cambio de que ninguna cifra sin respaldo llegue a pantalla.

## Estructura

| Carpeta | Qué hay | Dueño |
|---------|---------|-------|
| `agent/` | loop, herramientas, guard, memoria, eventos, cliente de Gemini | Brandon |
| `api/` | FastAPI + SSE + upload | Robinson |
| `ui/` | React: chat, chips de cita, panel de trazas | Robinson |
| `data/` | corpus + `FUENTES.md` (manifiesto con URL y fecha) | Julián |
| `evals/` | armazón + preguntas doradas | Julián |
| `team/` | contratos de interfaz + estado por persona | Brandon (contratos) |
| `scripts/` | pruebas reales de entorno y de agente | — |
| `tools/` | andamios de desarrollo (emisor de eventos falsos) | — |

`AGENTS.md` es el protocolo obligatorio para cualquier agente de código en este repo.

## Los 5 ítems del checklist técnico, y dónde verlos funcionando

| Ítem | Dónde | Estado |
|------|-------|--------|
| Orquestación | `agent/loop.py`, con el `motivo` de cada acción en el panel | listo |
| Grounding | `agent/guardrails.py` + evento `verify` + chips de cita | listo |
| Memoria | `agent/memory.py`, depósito de hechos que se pinta en pantalla | ⚠ la clase funciona pero **ninguna herramienta la escribe todavía**. El ítem no cuenta hasta que una herramienta de dominio guarde un hecho — 5 min el sábado |
| Guardrails | guard de citas + rechazo honesto + validaciones de dominio | guard listo; validaciones de dominio el sábado |
| Evaluación | `evals/harness.py` corriendo en vivo | armazón listo; las 12 preguntas el sábado |

Deuda conocida y decidida a propósito: [team/DEUDA-CONOCIDA.md](team/DEUDA-CONOCIDA.md).

## Decisiones técnicas (para no debatirlas el sábado)

- **Modelo:** Gemini Flash del tier gratis, con visión. El nombre va en `.env`, jamás en el código.
- **Loop:** escrito a mano. Cero frameworks de orquestación nuevos.
- **Un solo agente.** Sin sub-agentes: multiplican las formas de fallar en vivo.
- **Sin base vectorial.** Las especificaciones son números y reglas; la similitud
  semántica es la primitiva equivocada para el paso crítico. Búsqueda por palabras
  sobre secciones, más herramientas deterministas.
- **Lo calculable no se le pregunta al modelo.** Va en Python.
- **Sin MCP** salvo que sobre tiempo, y jamás se menciona en el pitch sin haberlo hecho.

## Lo que se verificó de verdad (24-jul-2026, no leído en documentación)

- `google-genai 2.14.0`: `client.interactions` existe, y `tool_config` con
  `function_calling_config` funciona en `generate_content`. `FunctionCallingConfigMode`
  tiene **cuatro** modos: `AUTO`, `ANY`, `NONE` y `VALIDATED`.
- `gemini-3.6-flash` responde texto, lee una placa sintética **5/5 campos**, y hace
  function calling en `AUTO` y en `ANY` entregando el `motivo`.
- **Gemini 3 exige `thought_signature`**: si se reconstruye a mano el turno del
  modelo para devolverle el resultado de una herramienta, la API responde
  `400 INVALID_ARGUMENT`. Hay que reenviar el `Content` original tal cual.
- **La cuota del tier gratis es 20 requests/día por proyecto y por modelo.**
  Ver `PLAN.md` § riesgos: es el riesgo operativo número uno del sábado.
