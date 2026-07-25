"""Agente simulado para probar el armazón del eval SIN API key.

Qué es real acá y qué no — importa para no engañarse:
  REAL      la carga del corpus, la búsqueda, la extracción de snippets literales,
            el guard de citas completo y la calificación del harness.
  SIMULADO  solo el texto que "redacta el modelo": sale del campo
            `respuesta_simulada` del set de preguntas.

O sea: esto NO prueba que Gemini funcione. Prueba que el armazón, el corpus y el
guard funcionan, que es lo que se puede verificar hoy sin key.
"""

from __future__ import annotations

from pathlib import Path

from agent.corpus import Corpus
from agent.guardrails import mensaje_degradacion, verificar
from agent.loop import RespuestaFinal
from agent.tools import BuscarArgs, construir_registro

CORPUS_JUGUETE = (
    Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "corpus_juguete"
)
"""El fixture vive en tests/, NO en data/, y es deliberado.

`DATA_DIR=./data` es lo que indexa el agente real. Con las fichas inventadas ahí
dentro, la búsqueda las mezclaba con las hojas de datos verdaderas — y como la
puntuación no tiene IDF y el desempate es alfabético, "corpus_juguete\\..." le
ganaba a "dataSheet_...". El caso feo no es el obvio: cuando un valor está en el
inventado Y en el real, la respuesta sale CORRECTA pero atribuida al documento
falso, con verify ok=True. Respuesta buena, procedencia falsa, sello verde.
"""

_corpus: Corpus | None = None
_registro = None


def _preparar():
    global _corpus, _registro
    if _corpus is None:
        _corpus = Corpus.desde_directorio(CORPUS_JUGUETE)
        _registro = construir_registro(_corpus)
    return _corpus, _registro


def responder_simulado(pregunta) -> RespuestaFinal:
    _, registro = _preparar()

    consulta = pregunta.consulta_simulada or pregunta.pregunta
    salida, _ms = registro.ejecutar(
        "buscar_conocimiento",
        {"consulta": consulta, "k": 3, "motivo": "buscar el dato antes de afirmarlo"},
    )

    hubo_consulta = True
    sources = salida.sources
    texto = pregunta.respuesta_simulada or ""

    res = verificar(texto, sources, hubo_consulta=hubo_consulta)
    bloqueada = not res.ok
    if bloqueada:
        texto = mensaje_degradacion(res)

    return RespuestaFinal(
        texto=texto, sources=sources, verify=res, bloqueada=bloqueada, rondas=1
    )
