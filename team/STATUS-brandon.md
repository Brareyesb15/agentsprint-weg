# STATUS — Brandon (carril: `agent/` + integración + `team/CONTRATOS.md`)

## AHORA   <!-- se SOBREESCRIBE. Máx 6 líneas. Telegráfico. Esto es lo que leen los demás. -->
- haciendo: nada, preparación cerrada. Falta el reto.
- hecho: entorno py3.12+node+gh · CONTRATOS v1 · guard de citas + 56 tests · armazón eval (4/4) · loop probado en vivo contra Gemini
- bloqueado: NO
- necesito de otros: LAS 3 KEYS QUE FALTAN (Julián, Robinson, Jhon) — cuota real 20 req/día/modelo, con una sola key no hay demo
- ojo: CONTRATOS v1 congelado. Robinson: construye el panel contra `tools/fake_stream.py`, ya emite los 8 eventos.
- ojo: Gemini 3 exige `thought_signature` — nunca reconstruyas a mano el turno del modelo, reenvía `Respuesta.contenido`.

## BITÁCORA   <!-- append-only, una línea con hora, nunca se borra -->
- 23:13 repo local inicializado; brain de equipo y AGENTS.md
- 23:20 CONTRATOS v1 congelado: 8 eventos, firma de tools, endpoints
- 23:26 guard de citas con normalización de unidades; 33 tests verdes
- 23:28 armazón del eval corriendo 4/4 con corpus de juguete y control negativo
- 23:40 loop completo probado contra gemini-3.6-flash: visión 5/5, ANY funciona
- 23:45 FIX crítico: Gemini 3 devolvía 400 por `thought_signature` perdido
- 23:52 FIX crítico: el guard pasaba en vacío con números en negrita markdown
- 23:58 cuota real verificada: 20 req/día/modelo → implementada rotación de modelos
