# FUENTES — manifiesto del corpus

Una fila por archivo de `data/`. **Sin fila, el archivo no se usa.**
Regla: los documentos se descargan y se commitean. Nunca se depende de una URL en vivo
(confirmado con WEG: sus enlaces llevan un hash que caduca y ya devolvió 404).

| Archivo | URL de origen | Fecha de descarga | Qué aporta | ¿Verificado a mano? |
|---------|---------------|-------------------|------------|---------------------|
| `WEG-WMO-w22-motor-electrico-trifasico-50024297-brochure-sp.pdf` | centro de descargas de WEG (doc. 50024297) | 2026-07-25 | **el corpus principal.** 72 páginas en español, línea W22 baja tensión, 60 Hz, IE3. Tablas de rendimiento por carcasa en las págs. 34–37 | sí, verificado con los 5 checks de abajo |

### Cómo se verificó (repetible para cualquier catálogo nuevo)

| Check | Resultado |
|---|---|
| Texto seleccionable (no escaneado) | ✅ 268.543 caracteres extraíbles |
| **rpm de 60 Hz** (1750 / 1760 / 1765) | ✅ 65 apariciones · y 41 menciones de "60 Hz" |
| Tabla de rendimiento | ✅ valores 88,0 / 89,1 / 90,3 / 91,5 junto a `132S`, pág. 34 |
| Carcasas (`132S`, `132M`, `112M`, `160L`) | ✅ 358 |
| Clase de eficiencia `IE3` / Premium | ✅ 53 |

> ⚠️ **El check que descarta un catálogo al instante:** si solo aparecen rpm de
> **1450 / 1470 / 1500**, es un catálogo **europeo de 50 Hz** y no sirve — ninguna
> placa colombiana va a coincidir con esas velocidades, el agente no encuentra nada
> y parece un bug del código cuando es el PDF.

### Descartado

`US100-Standard-Catalog-MV-Motors...pdf` — motores de **media tensión** (2,3–13,8 kV),
alternadores y reductores, **en inglés**. No es el caso de uso (nuestro relato es un
motor de 10 HP en baja tensión) y mientras estuvo en `data/` competía en la búsqueda
y ensuciaba las citas. Quedó fuera del índice, en `data-descartado/` (no versionado).

> ⚠ **Nada inventado dentro de `data/`.** Las fichas de juguete `ficha_ZX-100.md`
> y `ficha_ZX-200.md` viven en `tests/fixtures/corpus_juguete/`, fuera de este
> directorio, y es a propósito: `DATA_DIR=./data` es lo que indexa el agente real.
> Con las fichas falsas acá dentro, la búsqueda las mezclaba con las hojas de datos
> verdaderas, y como la puntuación no usa IDF y el desempate es alfabético,
> `corpus_juguete\...` le ganaba a `dataSheet_...`. El caso peligroso no es el
> obvio: si un valor está en el documento falso **y** en el real, la respuesta sale
> correcta pero **atribuida al documento inventado**, con `verify ok=True`.
> Respuesta buena, procedencia falsa, sello verde — justo lo que auditan los jueces.

## Formatos que el corpus acepta

`Corpus.desde_directorio` indexa **`.md` y `.pdf`**, recursivamente.

- De un **markdown** sale un fragmento por cada encabezado `## `.
- De un **PDF** sale un fragmento **por página, con su número de página**, así que
  la cita queda como "hoja de datos X, Datos técnicos, pág. 2" — que es exactamente
  la granularidad que premia la rúbrica.
- Si un PDF tiene páginas **sin texto extraíble**, el corpus lo avisa al cargar
  (`corpus.avisos`): ese PDF es de imágenes y necesita visión u OCR. Caso real y
  verificado con las fichas individuales de Pfannenberg.

Para comprobar qué se indexó de verdad antes de confiar en el agente:

```bash
.venv\Scripts\python.exe scripts/inspeccionar_corpus.py
```

---

## Sesgo de recolección mientras el reto sea desconocido

**Primero lo general, después lo específico.** Un catálogo general y una guía de
selección/especificación sirven para *cualquier* reto sobre esa marca. Las tablas
de un solo caso de uso solo sirven si el reto cae ahí.

## Candidatos verificados el 24-jul-2026 (de AgentSprint-TODO-PREPARAR.md)

**🟢 SICK** — una hoja de datos por producto, en español, PDF directo, sin bloqueo.
Patrón: `dataSheet_<referencia>_<n° artículo>_es.pdf`.
Centro de descargas: `https://www.sick.com/es/es/descargas/s/downloads`
*Por qué es la mejor:* un archivo por producto = cita quirúrgica ("hoja de datos
IME18-12NNSZC0S, página 2"), que es exactamente lo que premia la rúbrica.

**🟢 Banner Engineering** — página de catálogos en español con enlaces directos,
tamaño y fecha, sin login: `https://www.bannerengineering.com/mx/es/support/catalogs.html`
*Contra:* catálogos grandes, especificaciones en tablas (más difíciles de extraer).

**🟡 Pfannenberg** — catálogo en español OK, pero la ficha individual parece ser
imagen (metadatos de Photoshop) → obliga a visión/OCR.

**🔴 WEG** — bloqueo de Akamai confirmado dos veces (403 / Access Denied) y enlaces
con hash que caduca. Si se elige, la recolección es con navegador humano y el mismo día.

**🔴 Balluff · Pepperl+Fuchs** — 403 a clientes automáticos.

## Checklist al agregar un documento real

- [ ] El archivo está en `data/` y commiteado (no en la carpeta de descargas de alguien)
- [ ] Tiene fila en la tabla de arriba con URL y fecha
- [ ] Alguien lo abrió y confirmó que el texto se puede extraer (no es imagen)
- [ ] Si es imagen, se anotó acá que requiere OCR
