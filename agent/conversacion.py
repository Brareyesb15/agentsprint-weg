"""Historial corto de la conversación. Sin modelo, sin dependencias del SDK.

Ojo con la distinción que hace `agent/memory.py`: `SessionMemory` es el depósito de
HECHOS (tarifa = 814,10 COP/kWh) y se pinta en pantalla; esto es otra cosa, el
historial de lo que se dijo. Hacían falta los dos y solo existía el primero.

**Por qué se agregó (medido el 28-jul-2026):** `Agente._responder` armaba el
historial con UN solo mensaje, el del turno actual. El agente no recordaba nada de
lo hablado: en el guion de levantamiento llegaba al paso 4 sin acordarse de los HP
que el cliente había dado en el paso 2. La continuidad dependía por completo de que
un hecho hubiera quedado guardado, y las respuestas del cliente en lenguaje natural
("es para una banda transportadora") no guardan ningún hecho.

Se topa en 15 mensajes a propósito: con cuota de 20 requests/día y 3-6 llamadas por
turno, arrastrar la conversación entera es cuota que no se recupera. 15 cubre de
sobra los 6 pasos del guion.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Iterator, Literal

TOPE_MENSAJES = 15

Rol = Literal["usuario", "agente"]


@dataclass(frozen=True)
class Turno:
    rol: Rol
    texto: str


class Conversacion:
    """Los últimos `tope` mensajes. Cuando se llena, se cae el más viejo.

    Guarda solo TEXTO. Las fotos de placa no se arrastran: una imagen reescalada son
    miles de tokens en cada turno posterior, y lo que importa de la placa ya quedó
    como hechos en `SessionMemory` cuando `registrar_placa` la validó.
    """

    def __init__(self, tope: int = TOPE_MENSAJES) -> None:
        self._mensajes: deque[Turno] = deque(maxlen=tope)

    def agregar(self, rol: Rol, texto: str) -> None:
        if texto and texto.strip():
            self._mensajes.append(Turno(rol=rol, texto=texto.strip()))

    def reiniciar(self) -> int:
        """Vacía el historial. Devuelve cuántos mensajes se descartaron."""
        cuantos = len(self._mensajes)
        self._mensajes.clear()
        return cuantos

    def __len__(self) -> int:
        return len(self._mensajes)

    def __iter__(self) -> Iterator[Turno]:
        return iter(self._mensajes)
