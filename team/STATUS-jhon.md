# STATUS — Jhon (carril: `pitch/` + QA de dominio)

## AHORA   <!-- se SOBREESCRIBE. Máx 6 líneas. Telegráfico. Esto es lo que leen los demás. -->
- haciendo: QA de dominio sobre recomendación de motor
- hecho: cerrado un falso positivo del guard — citaba la PÁGINA (1.712 números) y no la fila. Nuevo `agent/tablas.py` (1.432 filas del catálogo, cada una validada con física) + `buscar_motor_equivalente` elige la fila en Python, reporta `cumple` y, si nada cumple, recorre el resto del catálogo y ofrece qué restricción ceder. Guion de levantamiento de 6 pasos. 153 tests
- bloqueado: NO
- necesito de otros: **Brandon**: toqué tu carril (`dominio.py`, `tablas.py`, `guardrails.py`, `prompts.py`, `loop.py`). La Puerta 1 del guard ya NO exige consulta si el turno no afirma nada (cifra o código): sin eso, cada pregunta del guion salía como "no alcancé a consultar la documentación". Las cifras siguen bloqueadas igual
- ojo: las tablas ya NO se entregan por página por ninguna vía. `buscar_conocimiento` devuelve como mucho 3 filas (tope GLOBAL, no por página) y solo las de mejor coincidencia; `leer_documento` no vuelca tablas y redirige a `buscar_motor_equivalente`. La prosa del catálogo no cambia
- ojo: **Julián** — `data/FUENTES.md` dice que las tablas de rendimiento están en págs. 34-37; esas son las de **50 Hz** (rpm 1475-1492). Las de 60 Hz IE3, las nuestras, están en **50-51**

## BITÁCORA   <!-- append-only, una línea con hora, nunca se borra -->
- 20:1x reproducido en vivo: respuesta con cifras del motor de 0,12 kW pegadas a "10 HP" daba `verify ok=True 6/6`
- 20:3x `agent/tablas.py`: parseo de la tabla a filas, auto-validado con `HP≈kW/0,7457` y `P≈√3·V·I·cosφ·η` — 836 filas del catálogo
- 20:4x la tensión de tabulación NO es fija: 400 V (50 Hz), 440 V (IE4), 380 V (IE3 60 Hz), 220 V (IE2/IE1 60 Hz). Se lee de cada página
- 20:5x en vivo: el guard ya bloquea y obliga a reformular (12/15 → 13/13). Antes daba verde a todo
- 21:0x FALSO NEGATIVO propio, detectado en vivo: el ancla no aceptaba carcasas con barra (`225S/M`, `132M/L`) y descartaba 596 filas — el 42% del catálogo. La herramienta negaba el 60 HP IE3 que SÍ existe. Corregido, con test
- 21:1x cuando nada cumple se recorre el catálogo soltando UNA restricción (clase/polos/potencia). La frecuencia NUNCA se relaja: 50 Hz no aplica en Colombia
- 21:3x cerrado el desvío genérico: `buscar_conocimiento`/`leer_documento` ya no entregan la página de una tabla. Evidencia del turno: 1712 dígitos → 66
