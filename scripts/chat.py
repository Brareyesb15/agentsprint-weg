"""Habla con el agente desde la consola y MIRA lo que hace, paso a paso.

Es la forma más rápida de ver si funciona, y el plan B de la demo si la UI falla.

    .venv\\Scripts\\python.exe scripts/chat.py "¿rendimiento del W22 IE3 de 10 HP?"
    .venv\\Scripts\\python.exe scripts/chat.py "¿qué motor WEG lo reemplaza?" data/placa.png

Sin argumentos entra en modo conversación: escribe, Enter, y sigue preguntando
sobre lo mismo (la memoria de sesión se mantiene). `salir` para terminar.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from agent.events import Emitter, Event  # noqa: E402
from evals.agente_real import construir   # noqa: E402

C = {
    "thought": "\033[90m", "tool_call": "\033[93m", "tool_result": "\033[92m",
    "verify": "\033[96m", "citation": "\033[95m", "memory": "\033[94m",
    "error": "\033[91m",
}
R = "\033[0m"
_t0 = time.time()


def pintar(ev: Event) -> None:
    d, c = ev.data, C.get(ev.type, "")
    if ev.type == "token":
        print(d["text"], end="", flush=True)
        return
    marca = f"{time.time() - _t0:5.1f}s"
    if ev.type == "tool_call":
        linea = f"{d['tool']}({_corto(d['args'], 70)})  · {d['motivo']}"
    elif ev.type == "tool_result":
        linea = f"{d['tool']} {'ok' if d['ok'] else 'FALLO'} {d['ms']}ms · {d['summary']}"
    elif ev.type == "verify":
        linea = f"{'PASA' if d['ok'] else 'BLOQUEA'} · {d['detail']}"
    elif ev.type == "citation":
        linea = f"{d['doc'][:34]} pág.{d['page']} · {d['section'][:44]}"
    elif ev.type == "memory":
        linea = f"{d['key']} = {d['value']}"
    elif ev.type == "error":
        linea = f"[{d['where']}] {d['message']}"
    else:
        linea = _corto(d.get("text", ""), 130)
    print(f"{c}{marca}  {ev.type:12} {linea}{R}")


def _corto(x, n: int) -> str:
    s = str(x).replace("\n", " ")
    return s if len(s) <= n else s[:n] + "…"


def main() -> int:
    global _t0
    args = sys.argv[1:]
    pregunta = args[0] if args else None
    ruta_img = Path(args[1]) if len(args) > 1 else None

    imagen = None
    if ruta_img:
        if not ruta_img.exists():
            print(f"no encuentro la imagen: {ruta_img}")
            return 1
        imagen = ruta_img.read_bytes()
        print(f"imagen: {ruta_img.name} ({len(imagen) // 1024} KB)")

    emitter = Emitter(sink=pintar)
    agente = construir(emitter)
    det, mod = agente.registro.cuentas()
    print(
        f"herramientas: {det} deterministas, {mod} con modelo · "
        f"modelo: {agente.cliente.modelo_en_uso}\n"
    )

    def turno(texto: str, img: bytes | None = None) -> None:
        global _t0
        _t0 = time.time()
        print(f"\n\033[1m> {texto}\033[0m\n")
        r = agente.responder(texto, imagen=img)
        print(f"\n\n  [{time.time() - _t0:.1f}s · {agente.cliente.modelo_en_uso}"
              f"{' · BLOQUEADA' if r.bloqueada else ''}]")

    if pregunta:
        turno(pregunta, imagen)
        if len(args) <= 2:
            return 0

    print("modo conversación — 'salir' para terminar")
    while True:
        try:
            texto = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            return 0
        if texto.lower() in {"salir", "exit", "quit", ""}:
            return 0
        turno(texto)


if __name__ == "__main__":
    raise SystemExit(main())
