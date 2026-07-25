# PLAN del sábado — 8:00 AM a 12:00 M · EAFIT

Build de ~3,5 h. Cada bloque tiene **criterio de aceptación**: no se avanza sobre
algo que no funciona. Los `<espacios>` se llenan con el reto en la mano.

---

## 8:00 – 8:10 · Arranque (no se codea)

Preguntas al organizador, en este orden:

1. ¿El reto es común para todos los equipos o distinto por marca?
2. ¿La marca que escogimos se mantiene, o el reto la impone?
3. ¿Se puede llevar código pre-escrito, o solo entorno y datos?
4. ¿A qué hora exacta son los pitches?

## 8:10 – 8:35 · Los primeros 25 minutos (playbook, sin debatir)

El equipo que pierde es el que se pone a discutir. En orden:

1. **Completar la frase en voz alta:** *"Nuestro agente ayuda a ___ a hacer ___."*
   Nadie sigue hasta que los cuatro la digan igual.
2. **¿Cuál es el UN dato o la UNA decisión que el agente tiene que producir sin
   equivocarse?** Eso es el corazón; el resto es adorno.
3. **¿Qué documento contiene ese dato?** Si la respuesta es "ninguno de los que
   trajimos", eso es lo primero que consigue Julián — antes de escribir código.
4. **¿Ese dato se calcula o se busca?** Se calcula → función de Python, nunca el
   modelo. Se busca → herramienta de conocimiento que devuelve la cita.
5. **Escribir las herramientas en `team/CONTRATOS.md` § 7** con nombre, argumentos
   y retorno. **Recién ahí empieza el código.**

Normalmente salen 3 o 4 herramientas: una que recibe la entrada del mundo real, una
que busca y cita, una que calcula, y una que produce el entregable.

**Criterio de aceptación:** § 7 de CONTRATOS lleno y los cuatro dijeron la frase igual.

## 8:35 – 9:15 · Corpus real + herramientas de dominio

- **Julián + Jhon:** documentos a `data/`, fila por archivo en `data/FUENTES.md`.
  Sesgo: **primero lo general** (catálogo, guía de selección), después lo específico.
- **Brandon:** las herramientas de dominio en `agent/tools.py`, con la firma del
  contrato (`result` / `sources` / `uncertainty`, banderas `es_conocimiento` y `usa_modelo`).
- **Robinson:** conectar el panel (ya construido contra `tools/fake_stream.py`) al
  backend real.

**Criterio de aceptación:** `scripts/prueba_agente.py` responde UNA pregunta del
dominio real con `verify ok=True` y cita correcta.

## 9:15 – 10:15 · Camino crítico completo

Flujo entero: entrada → consulta → cálculo → respuesta verificada → panel.

**Criterio de aceptación:** una pregunta del dominio entra por la UI y sale con
chips de cita y el evento `verify` visible. Si a las 10:15 esto no pasa, se aplica
la lista de corte (abajo) sin votación.

## 10:15 – 11:00 · Preguntas doradas + eval

- **Julián:** 12 preguntas en `evals/sets/doradas.json`. Mezcla obligatoria: ~8 de
  dato concreto, ~2 de razonamiento, **~2 trampas** con `debe_rechazar: true`.
- Correr `python -m evals.harness --set doradas --guardar`.
- De las que pasen 10/10, elegir **3 para mostrar en vivo**.

**Criterio de aceptación:** una corrida completa guardada en `evals/runs/` con hora.

## 11:00 – 11:30 · Ensayo cronometrado

- Cronometrar el flujo completo. Narrar **encima** del panel de trazas.
- Ensayar el **rechazo provocado**: pedirle en vivo algo que no está en el corpus.
- Máximo un reintento en vivo antes de bajar de escalón.

**Criterio de aceptación:** la demo cabe en el tiempo asignado, dos veces seguidas.

## 11:30 – 12:00 · Pitch

Estructura: **problema con un número → demo en vivo → cómo funciona (una diapositiva)
→ por qué importa.**

Munición verificada:
- ReshapeX cuantifica el dolor en **10–15 minutos de verificación manual de
  especificaciones por consulta**. Ese número, dicho en el pitch, es hablarles con
  su propia métrica.
- La historia real de Jhon: el CRM de turismo sin grounding que costó un cliente.
- **`N` de `M` herramientas son código determinista** (el número exacto lo da
  `registro.cuentas()`). "Lo que se puede calcular no se le pregunta a un modelo."

**Corrección obligatoria:** la frase "rebobinar un motor pierde 1 o 2 puntos de
eficiencia" **es falsa**. El estudio EASA/AEMT midió de −0,5% a +0,3%, promedio
**−0,1 punto**, y llama míticas las caídas de 1 a 5%. Matiz para el Q&A: en talleres
sin control de proceso, los motores de 75–150 HP sí perdieron ~0,6%. Si el reto es
de motores, el argumento correcto es el salto **IE1 → IE3**, no el rebobinado.

---

# Lista de corte

**Si vamos tarde, se corta EN ESTE ORDEN, sin votación:**

1. El entregable en PDF → se muestra en markdown en el chat.
2. La memoria con resumen → queda el depósito simple de hechos.
3. Pulido de UI.

**NUNCA se corta:** las citas en cada respuesta (el guard), los cálculos en código
determinista, el panel de trazas, la demo en vivo, los commits limpios.

**Si vamos adelantados, en este orden:** envolver una herramienta como servidor MCP ·
el rechazo elegante mostrado en vivo · ceder el teclado a un juez para que intente romperlo.

---

# Riesgos y su plan

## 1. Cuota de Gemini — RIESGO NÚMERO UNO, y el número real es peor de lo esperado

**Verificado el 24-jul-2026 con una key real, leyendo el error de la API:**

```
quotaId: GenerateRequestsPerDayPerProjectPerModel-FreeTier
model: gemini-3.6-flash        quotaValue: 20
```

**20 requests por día, por proyecto, por modelo.** No 1.500. Los documentos del
equipo tenían números de otra época.

Lo que se midió con esa misma key:

| Modelo | Cuota |
|--------|-------|
| `gemini-3.6-flash` | 20/día (se agotó en una sola sesión de pruebas) |
| `gemini-3-flash-preview` | cuota **propia**, seguía disponible con la otra agotada |
| `gemini-2.0-flash` | límite **0** — no está en el tier gratis |
| `gemini-2.5-flash`, `-lite` | 404 con esta key |

**Un turno del agente gasta entre 3 y 6 llamadas** → 20/día son **unas 4 preguntas**.

Plan, en orden de importancia:

1. **Las 4 keys, de 4 proyectos distintos.** Hoy solo hay una llena en el `.env`.
   Sin las otras tres no hay demo. Esto es lo primero de mañana.
2. **Rotación de modelos ya implementada** (`MODEL_FALLBACKS` en el `.env`): cuando
   un modelo se agota, el cliente pasa al siguiente solo. 4 keys × 3 modelos ≈ 240
   requests/día ≈ 40–60 preguntas. Eso sí alcanza.
3. **Cargar ~$5 de billing en UN proyecto** como seguro. Es la única forma de salir
   del límite de 20/día. Con 4 keys gratis apretadas, esto compra tranquilidad.
4. **No quemar cuota probando.** El eval en modo `--fake` no gasta ni una llamada.
   Úsenlo para todo lo que no requiera el modelo.
5. El estado de cuota se muestra en pantalla a propósito: la cola del rate limit
   visible convierte la limitación en prueba de ingeniería honesta.

## 2. Otros riesgos

- **Enlaces de documentos que caducan** (confirmado en WEG): el corpus se descarga a
  `data/` y se commitea. Nunca se depende de una URL en vivo.
- **El coding agent falla:** login verificado en LA máquina del evento y por hotspot;
  un segundo coding agent logueado; Robinson puede tomar el pegamento crítico.
- **Wifi de EAFIT:** 2+ hotspots probados, dependencias en caché local (ya instaladas
  en `.venv`, no hace falta descargar nada el sábado).
- **La entrada de la demo falla** (foto borrosa): ingreso manual como *feature*, no
  como excusa.
- **Latencia se come el pitch:** cronometrar el flujo completo; narrar encima del panel.

---

# Espacios a llenar mañana

- [ ] La frase: "Nuestro agente ayuda a ___ a hacer ___."
- [ ] `team/CONTRATOS.md` § 7: herramientas de dominio
- [ ] `data/` + `data/FUENTES.md`: el corpus real
- [ ] `evals/sets/doradas.json`: 12 preguntas
- [ ] Las 3 keys que faltan en el `.env`
- [ ] Nombre de cada persona en su `team/STATUS-*.md` y su carril en `AGENTS.md`
