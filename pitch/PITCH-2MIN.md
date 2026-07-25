# Pitch de 2 minutos — para Jhon

**La frase que los cuatro decimos igual:**
> Nuestro agente ayuda al vendedor de un distribuidor WEG a responder, en 60 segundos
> y con la fuente citada, qué motor reemplaza al de la foto y cuánto ahorra al año.

**El flujo en una línea:**
```
foto de la placa → física la valida → catálogo W22 la cruza (cita con página)
→ pregunta lo que no sabe (horas, tarifa, precio) → Python calcula el ahorro
→ verificador revisa cada cifra contra la fuente → respuesta con citas
```

---

## EL SPEECH (2:00 — ensayado, no leído)

**[0:00 — el problema, con el número de los jueces]**

Cuando un motor se quema en una planta, la línea se para. Y la decisión de qué
comprar no la toma un ingeniero con tiempo: la toma un jefe de mantenimiento
apurado, que le toma una foto a una placa oxidada de hace veinte años y se la manda
por WhatsApp a su distribuidor. Ahí empieza la espera. Del otro lado, un vendedor
tiene que descifrar esa foto, cruzarla contra un catálogo de cientos de páginas y
armar una cotización. Eso son **diez a quince minutos de verificación manual por
consulta** — y la cotización que no sale el mismo día, la gana otro.

**[0:35 — la demo, narrada encima del panel]**

Nosotros le dimos ese trabajo a un agente. Miren: le mando la foto de esta placa.

El agente la lee — pero **no se la cree**. La valida con física: 1750 RPM a 60 Hz
son 4 polos; la corriente cuadra con la potencia. Si hubiera leído 17.500, no
calcula: repregunta. Eso no es inteligencia artificial, son treinta líneas de física.

Con la placa validada, busca en el catálogo oficial de WEG y encuentra el
reemplazo: W22 IE3. Y ahí está la cita — **página 51, la tabla real**. La placa
vieja no trae la eficiencia, y el agente **no se la inventa**: la toma de la norma.

Ahora le pregunto cuánto se ahorra. Fíjense: **me pide lo que no puede saber** —
horas de operación, tarifa, precio del distribuidor. Se los doy… y ahí está: pesos
por año, y el motor **se paga solo en tantos meses**.

**[1:20 — por qué se le puede creer]**

Antes de mostrar cada respuesta, un verificador compara **cada cifra contra su
fuente** — ahí lo ven: nueve de nueve valores confirmados. Y de nuestras cinco
herramientas, **las cinco son código determinista**: el modelo no hace ni una
cuenta, solo lee la foto y redacta. Porque el modelo que le manda a tu cliente el
motor equivocado suena exactamente igual al que le manda el correcto. El nuestro,
si no puede confirmar un dato, **lo dice** — pregúntenle algo que no esté en el
catálogo y lo van a ver rechazar.

**[1:45 — el cierre]**

Hoy esa foto espera hasta el lunes. Con esto, el vendedor responde en sesenta
segundos, con la página del catálogo en la mano y un argumento de venta que antes
no tenía: *"este motor se paga solo"*. El distribuidor cotiza el mismo día, cierra
más, y vende el motor de mejor margen. Eso es lo que construimos esta mañana.

---

## Dónde generamos valor (si preguntan, en este orden)

| Para quién | Valor |
|---|---|
| **Vendedor del distribuidor** (usuario) | de 10–15 min por consulta a 60 segundos, sin parar lo que está haciendo |
| **Distribuidor** (el que paga) | la cotización sale el mismo día = venta que no se pierde; y el ROI le vende el IE3, que es el ticket más alto |
| **Planta** (beneficiario final) | deja de quemar energía en un IE1; decisión con fuentes, no con afán |
| **La marca WEG** | su catálogo deja de ser un PDF de 72 páginas y se vuelve un experto que responde |

## Reglas de oro en tarima

1. **La foto es la ENTRADA (15 segundos), no el clímax.** Los jueces YA venden
   foto→cotización. El clímax es el cierre económico, que ellos no hacen.
2. **NO decir** "rebobinar pierde 1–2 puntos de eficiencia" — es falso (EASA/AEMT:
   −0,1 promedio). El argumento es el salto **IE1 → IE3**.
3. **NO mencionar MCP** ni nada que no esté corriendo.
4. Si preguntan por el precio: *"WEG vende por canal; el precio lo pone el
   distribuidor. Por eso el agente lo pide en vez de inventarlo."*
5. Si algo falla en vivo: el rechazo honesto ES el producto. Se narra como virtud:
   *"prefiere callar antes que afirmar sin fuente"*.
