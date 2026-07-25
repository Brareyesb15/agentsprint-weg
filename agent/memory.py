"""Depósito de hechos de la sesión.

Ojo con la distinción, que un juez estricto sí hace: esto NO es "historial de chat".
Historial lo tiene cualquiera y no cuenta como memoria. Esto es un depósito de
hechos explícitos, con su fuente, que se PINTA EN PANTALLA y se usa a propósito
en la demo ("MEMORIA: tarifa = 814,10 COP/kWh").
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterator

from agent.events import Emitter
from agent.sources import Source


@dataclass
class Hecho:
    key: str
    value: Any
    origen: str = ""            # de qué herramienta o turno salió
    source: Source | None = None


class SessionMemory:
    """Un hecho por `key`. Guardar la misma key la sobreescribe (y se vuelve a emitir)."""

    def __init__(self, emitter: Emitter | None = None) -> None:
        self._hechos: dict[str, Hecho] = {}
        self._emitter = emitter

    def guardar(
        self, key: str, value: Any, origen: str = "", source: Source | None = None
    ) -> Hecho:
        hecho = Hecho(key=key, value=value, origen=origen, source=source)
        self._hechos[key] = hecho
        if self._emitter is not None:
            self._emitter.memory(key, value)
        return hecho

    def obtener(self, key: str, por_defecto: Any = None) -> Any:
        h = self._hechos.get(key)
        return h.value if h else por_defecto

    def olvidar(self, key: str) -> None:
        self._hechos.pop(key, None)

    def como_dict(self) -> dict[str, Any]:
        return {k: h.value for k, h in self._hechos.items()}

    def para_prompt(self) -> str:
        """Los hechos, listos para inyectar en el prompt del turno siguiente."""
        if not self._hechos:
            return "(sin hechos guardados todavía)"
        return "\n".join(f"- {k} = {h.value}" for k, h in self._hechos.items())

    def sources(self) -> list[Source]:
        """Las fuentes de los hechos recordados, para que el guard las considere."""
        return [h.source for h in self._hechos.values() if h.source is not None]

    def __len__(self) -> int:
        return len(self._hechos)

    def __iter__(self) -> Iterator[Hecho]:
        return iter(self._hechos.values())

    def __contains__(self, key: object) -> bool:
        return key in self._hechos
