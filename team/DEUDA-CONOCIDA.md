# Deuda conocida — defectos reales que se decidió NO arreglar antes del evento

Salieron de una auditoría adversarial (62 agentes, cada hallazgo verificado
reproduciéndolo antes de aceptarlo). **Están acá porque son reales**, no porque se
duden. Se dejaron fuera por una razón explícita en cada caso.

Si algo raro pasa mañana, busca primero acá: es probable que ya esté descrito.

---

## Del guard de citas

### 1. `resultados_calculo` es un comodín: cualquier número de una herramienta valida cualquier afirmación

Si una herramienta devuelve `{"payback_meses": 14.2}`, el guard acepta *"la distancia
de detección es de 14,2 mm"* como confirmada. El número existe en la evidencia, pero
no significa lo que la respuesta dice.

**Por qué no se arregló:** el arreglo correcto es que las herramientas **declaren la
unidad de cada salida** (`{"payback": {"valor": 14.2, "unidad": "meses"}}`), y eso hay
que decidirlo cuando se escriban las herramientas de dominio, no antes.
**Qué hacer mañana:** al escribir cada herramienta de cálculo, devolver la unidad en
la clave (`potencia_w`, `payback_meses`) y, si sobra tiempo, filtrar por familia.
**Mitigación de hoy:** ya solo aplica a herramientas con `es_conocimiento=False`.

### 2. Notación no cubierta por el tokenizador → el guard no ve el número

`5e-3 A`, `24V/48V`, `±0,5 mm`, `≥12 mm`, rangos tipo `10-20 mm`. El guard reporta
"la respuesta no afirma ningún valor numérico" y da verde.
**Qué hacer:** si el corpus del reto usa alguna de esas notaciones, agregar los
símbolos a `_BASURA` en `agent/sources.py` y un test. 10 minutos.

### 3. Enteros pelados en prosa pueden bloquear una respuesta correcta

*"Encontré 2 secciones relevantes: la tensión es de 24 V"* → el `2` no está en la
fuente y bloquea todo. Años (`2026`) igual.
**Por qué no se arregló:** el arreglo (two-tier: solo bloquear cifras con unidad)
afloja el guard, y aflojarlo sin poder probar contra el modelo era peor.
**Mitigación:** el prompt ya pide respuestas directas sin relleno. Si aparece en
vivo, es un bloqueo honesto y se narra como tal.

### 4. Los códigos contradictorios avisan pero no bloquean

`IP67` en la fuente y `IP68` en la respuesta → `detail` dice
`CONTRADICE LA FUENTE: IP68` bien visible, pero `ok` sigue en `true`.
**Cambio de una palabra si lo quieren estricto:** `verificar(..., codigos_bloquean=True)`.
Se dejó en aviso porque bloquear de más en vivo es peor que avisar de más.

---

## Del cliente de Gemini

### 5. Solo los 429 activan el respaldo de modelo. Un 503 mata el turno

`es_error_de_cuota` no reconoce 503 / 500 / 504 / timeouts, y esos se relanzan tal
cual. Con el turno ya envuelto en try/except el jurado ve una respuesta honesta en
vez de un traceback, pero se pierde la pregunta.
**Arreglo:** una función `es_transitorio()` al lado de `es_error_de_cuota()` en
`agent/keys.py`, que reintente 2 veces con espera corta. **10 minutos, vale la pena
si sobra tiempo.**

### 6. Cambiar de proveedor cuesta 60-80 minutos, no 20

El aislamiento es bueno (`from google import genai` solo en 2 archivos), pero hay
tres trampas medidas: `respuesta_de_herramienta` correlaciona por **nombre** y no por
id (OpenAI y Anthropic exigen `tool_call_id`); la fase de cierre manda historial con
`tool_use` **sin declarar tools** (Gemini lo tolera, Anthropic devuelve 400); y
OpenAI manda los argumentos como string JSON, no como dict.
**Decisión:** **no se cambia de proveedor.** Billing en Gemini es 1 línea de `.env`
y 0 de código. La constante `MODO_SIN_TOOLS` existe y no se usa: es la pieza del
arreglo si algún día se migra.

---

## Del harness de evaluación

### 7. `espera_valores` es lo que de verdad prueba algo

`espera_doc` ya se comprueba contra los respaldos del guard, pero una pregunta sin
`espera_valores` aprueba con casi cualquier respuesta que cite el documento.
**Para Julián:** llenar `espera_valores` en las 12 doradas. Sin eso, el eval en vivo
demuestra menos de lo que parece.

### 8. El modo `--fake` necesita `respuesta_simulada`

Una pregunta de `doradas.json` sin ese campo falla con "respuesta vacía" en `--fake`.
Es el modo que **no gasta cuota**, así que vale llenarlo al escribir cada pregunta.

---

## De proceso, y es el riesgo número uno

### 9. El repo no está en GitHub y no tiene ni un commit

`AGENTS.md` ordena `git pull --rebase origin main` al empezar cada tarea y `git push`
al terminar. Sin remoto, los cuatro agentes de código reciben
`fatal: 'origin' does not appear to be a git repository` a las 8:05, y el mecanismo
de coordinación del equipo entero no arranca.

Además **no hay respaldo de nada**: el Desktop no está sincronizado con la nube.

**Está así porque Brandon pidió explícitamente no commitear todavía.** Es su
decisión y es legítima, pero conviene saber el costo: es lo primero que hay que
hacer, y las invitaciones dependen de que los otros tres las **acepten**, así que
mandarlas temprano no es opcional.
