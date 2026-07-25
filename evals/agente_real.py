"""Arma el agente de verdad (Gemini + corpus real) para correr el eval.

Requiere `.env` con al menos una GOOGLE_API_KEY_n y MODEL_NAME.
"""

from __future__ import annotations

from agent import config as cfg_mod
from agent.corpus import Corpus
from agent.events import Emitter
from agent.keys import Rotador
from agent.llm import Cliente
from agent.loop import Agente, RespuestaFinal
from agent.memory import SessionMemory
from agent.tools import construir_registro

_agente: Agente | None = None


def construir(emitter: Emitter | None = None) -> Agente:
    cfg = cfg_mod.cargar()
    cfg.exigir_keys()
    corpus = Corpus.desde_directorio(cfg.data_dir)
    if not corpus.fragmentos:
        raise RuntimeError(
            f"El corpus de {cfg.data_dir} está vacío. Sin documentos, el guard "
            "va a bloquear todas las respuestas — y tendrá razón."
        )
    em = emitter or Emitter()
    return Agente(
        cliente=Cliente(Rotador(cfg.api_keys), cfg.cadena_de_modelos),
        registro=construir_registro(corpus),
        emitter=em,
        memoria=SessionMemory(em),
        tolerancia=cfg.guard_tolerancia,
    )


def responder_real(pregunta) -> RespuestaFinal:
    global _agente
    if _agente is None:
        _agente = construir()
    return _agente.responder(pregunta.pregunta)
