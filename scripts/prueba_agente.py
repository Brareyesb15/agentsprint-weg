"""Prueba del agente COMPLETO contra el modelo real, sobre el corpus de juguete.

Esto es lo que `scripts/prueba_entorno.py` no cubre: que el loop, el registro de
herramientas, el guard y los eventos funcionen JUNTOS con Gemini de verdad.

    .venv\\Scripts\\python.exe scripts/prueba_agente.py

Se prueban dos turnos a propósito:
  1. Una pregunta cuyo dato SÍ está en el corpus  -> debe responder con cita.
  2. Una pregunta cuyo dato NO está               -> debe rechazar, no inventar.
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from agent import config as cfg_mod           # noqa: E402
from agent.corpus import Corpus               # noqa: E402
from agent.events import Emitter, Event       # noqa: E402
from agent.keys import Rotador                # noqa: E402
from agent.llm import Cliente                 # noqa: E402
from agent.loop import Agente                 # noqa: E402
from agent.memory import SessionMemory        # noqa: E402
from agent.tools import construir_registro    # noqa: E402

COLOR = {
    "thought": "\033[90m", "tool_call": "\033[93m", "tool_result": "\033[92m",
    "verify": "\033[96m", "citation": "\033[95m", "memory": "\033[94m",
    "error": "\033[91m", "token": "\033[0m",
}
RESET = "\033[0m"


def pintar(ev: Event) -> None:
    """Hace de panel de trazas en consola: los mismos 8 eventos que verá el front."""
    c = COLOR.get(ev.type, "")
    d = ev.data
    if ev.type == "token":
        print(d["text"], end="", flush=True)
        return
    if ev.type == "tool_call":
        linea = f"{d['tool']}({_corto(d['args'])})  motivo: {d['motivo']}"
    elif ev.type == "tool_result":
        linea = f"{d['tool']} -> {'ok' if d['ok'] else 'FALLO'} en {d['ms']} ms · {d['summary']}"
    elif ev.type == "verify":
        linea = f"{'PASA' if d['ok'] else 'BLOQUEA'} · {d['detail']}"
    elif ev.type == "citation":
        linea = f"{d['doc']} / {d['section']} :: {_corto(d['snippet'], 80)}"
    elif ev.type == "memory":
        linea = f"{d['key']} = {d['value']}"
    elif ev.type == "error":
        linea = f"[{d['where']}] {d['message']}"
    else:
        linea = _corto(d.get("text", ""), 140)
    print(f"{c}  {ev.type:12} {linea}{RESET}")


def _corto(x, n: int = 100) -> str:
    s = str(x).replace("\n", " ")
    return s if len(s) <= n else s[:n] + "..."


def main() -> int:
    cfg = cfg_mod.cargar()
    try:
        cfg.exigir_keys()
    except RuntimeError as e:
        print(f"[FALLA] {e}")
        return 1

    corpus = Corpus.desde_directorio(cfg.data_dir)
    print(f"corpus: {len(corpus.fragmentos)} fragmentos de {cfg.data_dir}")
    if not corpus.fragmentos:
        print("[FALLA] corpus vacío")
        return 1

    registro = construir_registro(corpus)
    det, mod = registro.cuentas()
    print(f"herramientas: {registro.nombres()}  ({det} deterministas, {mod} con modelo)")
    print(f"cadena de modelos: {cfg.cadena_de_modelos}   keys: {len(cfg.api_keys)}\n")

    emitter = Emitter(sink=pintar)
    rotador = Rotador(cfg.api_keys)
    cliente = Cliente(rotador, cfg.cadena_de_modelos)
    agente = Agente(
        cliente=cliente,
        registro=registro,
        emitter=emitter,
        memoria=SessionMemory(emitter),
        tolerancia=cfg.guard_tolerancia,
    )

    casos = [
        ("¿Con qué tensión se alimenta el ZX-100 y cuánto consume?", False),
        ("¿Cuánto cuesta el ZX-100 en pesos colombianos?", True),
    ]

    fallas = 0
    for pregunta, debe_rechazar in casos:
        print("=" * 74)
        print(f"PREGUNTA: {pregunta}")
        print("=" * 74)
        resp = agente.responder(pregunta)
        print("\n")

        if debe_rechazar:
            if resp.bloqueada or "no est" in resp.texto.lower() or "no tengo" in resp.texto.lower():
                print("  >> CORRECTO: no inventó un precio que no está en el corpus.\n")
            else:
                print(f"  >> FALLA: debía rechazar y afirmó: {resp.texto[:160]}\n")
                fallas += 1
        else:
            if resp.verify and resp.verify.ok and resp.sources:
                print(f"  >> CORRECTO: {resp.verify.detail}\n")
            else:
                print(f"  >> FALLA: verify={resp.verify and resp.verify.detail!r}\n")
                fallas += 1

    print("=" * 74)
    print(f"estado: {cliente.estado()}")
    print("VEREDICTO:", "agente LISTO" if fallas == 0 else f"{fallas} caso(s) con falla")
    return 0 if fallas == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
