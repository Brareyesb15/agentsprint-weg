"""Los 8 eventos SSE de team/CONTRATOS.md.

Nadie arma el JSON de un evento a mano: todo pasa por `Emitter`. Así el front de
Robinson nunca recibe un campo con otro nombre del que dice el contrato.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from agent.sources import Source

TIPOS = (
    "thought",
    "tool_call",
    "tool_result",
    "verify",
    "token",
    "citation",
    "memory",
    "error",
)


def ahora_ms() -> int:
    return int(time.time() * 1000)


@dataclass
class Event:
    type: str
    data: dict[str, Any]
    ts: int = field(default_factory=ahora_ms)

    def __post_init__(self) -> None:
        if self.type not in TIPOS:
            raise ValueError(
                f"tipo de evento '{self.type}' no está en el contrato. "
                f"Permitidos: {', '.join(TIPOS)}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "ts": self.ts, "data": self.data}

    def to_sse(self) -> str:
        """Una línea `data: {...}` seguida de línea en blanco, como manda el contrato."""
        return f"data: {json.dumps(self.to_dict(), ensure_ascii=False)}\n\n"


class Emitter:
    """Recolecta eventos y (opcionalmente) los empuja a un sink en vivo.

    `sink` es cualquier callable que reciba un `Event`. En la API es la cola del
    SSE; en los tests es una lista; en la consola puede ser un print.
    """

    def __init__(self, sink: Callable[[Event], None] | None = None) -> None:
        self._sink = sink
        self.historial: list[Event] = []

    # -- interno --------------------------------------------------------------

    def _emit(self, type_: str, data: dict[str, Any]) -> Event:
        ev = Event(type=type_, data=data)
        self.historial.append(ev)
        if self._sink is not None:
            self._sink(ev)
        return ev

    # -- los ocho -------------------------------------------------------------

    def thought(self, text: str) -> Event:
        return self._emit("thought", {"text": text})

    def tool_call(self, id: str, tool: str, args: dict[str, Any], motivo: str) -> Event:
        if not motivo or not motivo.strip():
            raise ValueError(
                f"la herramienta '{tool}' se llamó sin `motivo`. El contrato lo exige: "
                "es lo que convierte el panel en línea de tiempo narrada."
            )
        return self._emit(
            "tool_call", {"id": id, "tool": tool, "args": args, "motivo": motivo}
        )

    def tool_result(
        self,
        id: str,
        tool: str,
        ok: bool,
        ms: int,
        summary: str,
        sources: Iterable[Source] | None = None,
    ) -> Event:
        return self._emit(
            "tool_result",
            {
                "id": id,
                "tool": tool,
                "ok": ok,
                "ms": int(ms),
                "summary": summary,
                "sources": [s.to_dict() for s in (sources or [])],
            },
        )

    def verify(self, ok: bool, checked: int, confirmed: int, detail: str) -> Event:
        return self._emit(
            "verify",
            {"ok": ok, "checked": int(checked), "confirmed": int(confirmed), "detail": detail},
        )

    def token(self, text: str) -> Event:
        return self._emit("token", {"text": text})

    def citation(self, source: Source) -> Event:
        return self._emit("citation", source.to_dict())

    def memory(self, key: str, value: Any) -> Event:
        return self._emit("memory", {"key": key, "value": value})

    def error(self, where: str, message: str, recoverable: bool) -> Event:
        return self._emit(
            "error", {"where": where, "message": message, "recoverable": recoverable}
        )
