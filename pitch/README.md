# `pitch/` — carril de JHON

Está vacío a propósito: es tu carril y nadie más lo toca.
Acá van el guion, las diapositivas y las respuestas del Q&A.

## Estructura del pitch (esta parte NO depende del reto)

**problema con un número → demo en vivo → cómo funciona (UNA diapositiva) → por qué importa**

## Munición ya verificada

- **El número del problema:** ReshapeX —los jueces— cuantifica el dolor en
  **10–15 minutos de verificación manual de especificaciones por consulta**. Decir
  ese número es hablarles con su propia métrica.
- **Tu historia real:** el CRM de turismo sin grounding que costó un cliente. Sirve
  con cualquier reto y es lo único del pitch que nadie puede copiar.
- **El dato técnico que aguanta el Q&A:** `N` de `M` herramientas son código
  determinista, no el modelo. El número exacto lo da `registro.cuentas()`.
  *"Lo que se puede calcular no se le pregunta a un modelo. El modelo no hace la cuenta."*
- **Frase de venta de los jueces**, útil para enmarcar: *el modelo que manda el
  producto equivocado suena exactamente igual al que manda el correcto.*

## ⚠ Corrección obligatoria — verificada, no la digas mal

La frase **"rebobinar un motor pierde 1 o 2 puntos de eficiencia" es FALSA.**

El estudio EASA/AEMT midió cambios de **−0,5% a +0,3%, promedio −0,1 punto**, y
llama explícitamente **míticas** las caídas de 1 a 5%. Con buenas prácticas queda
dentro de ±0,2%.

Si lo dices y un juez conoce el estudio, quedas refutado en vivo — y el pitch
entero trata sobre no afirmar cosas sin fuente.

- **Matiz para el Q&A:** en talleres **sin control de proceso**, los motores
  grandes de 75–150 HP sí perdieron ~0,6% en promedio.
- **El argumento correcto**, si el reto termina siendo de motores: el salto de
  clase de eficiencia **IE1 → IE3**, que sobrevive incluso si el rebobinado fuera
  perfecto.

## Qué NO decir

- **MCP**, si no se implementó. Mencionarlo sin tenerlo es regalarle al jurado la
  pregunta que te desnuda. Solo se dice si alcanzó el tiempo y está corriendo.
- **"Foto → cotización" como si fuera novedoso.** Es literalmente el producto de
  ReshapeX; lo venden con WhatsApp. La foto es la ENTRADA de la demo (15 segundos),
  no el clímax.
- Cualquier cifra que no puedas señalar en un documento.

## Las 10 preguntas probables del jurado

Escríbelas acá con su respuesta de una línea. Arranques seguros:

1. ¿De dónde salió ese número? *(la respuesta correcta: se señala el documento en pantalla)*
2. ¿Y si el modelo se equivoca en el cálculo? *(el modelo no calcula: lo hace Python)*
3. ¿Qué pasa si le preguntan algo que no está en la documentación? *(muéstralo en vivo)*
4. ¿Cómo saben que no está alucinando? *(el evento `verify`, en pantalla, cifra por cifra)*
5. ¿Esto escala a un catálogo de 10.000 referencias?
6. ¿Cuánto cuesta operarlo?
7. ¿Por qué no usaron una base vectorial?
8. ¿Qué pasa cuando el fabricante actualiza el catálogo?
9. ¿Quién es el usuario exacto y cómo llega a él?
10. ¿Qué harían con dos semanas más?

## Tu otro trabajo: QA de dominio

Eres el que rompe el agente antes de que lo rompa un juez. Preguntas capciosas,
unidades mezcladas, referencias que no existen, datos que se contradicen entre
documentos. Cada cosa que encuentres va como pregunta a `evals/sets/doradas.json`.
