"""Rotación de las 4 API keys + reintento con espera.

Por qué existe: la cuota del tier gratis de Gemini es **por proyecto** y Google ya
no publica los números (dice que los mires en tu consola de AI Studio). Cuatro keys
de cuatro proyectos dan ~4x de margen. El SDK trae reintento propio, pero depender
de un comportamiento implícito el día del evento es apostar.

Además cuenta los 429 y expone `estado()`, que se muestra en pantalla: la cola del
rate limit VISIBLE convierte la limitación en prueba de ingeniería honesta.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Callable, TypeVar

T = TypeVar("T")

# Señales de agotamiento de cuota en el mensaje de error del SDK.
_SENALES_CUOTA = ("429", "resource_exhausted", "quota", "rate limit", "too many requests")


def es_error_de_cuota(e: BaseException) -> bool:
    texto = f"{type(e).__name__} {e}".lower()
    return any(s in texto for s in _SENALES_CUOTA)


@dataclass
class Rotador:
    keys: list[str]
    espera_base: float = 1.0
    # Tope BAJO a propósito. Con 16 s, agotar los reintentos costaba 45 s de pantalla
    # congelada antes de degradar al modelo de respaldo — y la demo entera son 180 s.
    # Un 429 con quotaId "...PerDay..." no se cura esperando: se cura cambiando de
    # modelo, que es lo que hace el Cliente en cuanto esto se rinde. La espera solo
    # sirve para los límites por MINUTO, y esos ceden en pocos segundos.
    espera_maxima: float = 4.0
    max_intentos: int = 6
    dormir: Callable[[float], None] = time.sleep

    _i: int = field(default=0, init=False)
    agotadas: dict[int, int] = field(default_factory=dict, init=False)
    llamadas: int = field(default=0, init=False)
    reintentos: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        if not self.keys:
            raise ValueError("Rotador necesita al menos una key")

    def actual(self) -> str:
        return self.keys[self._i]

    def indice(self) -> int:
        return self._i

    def rotar(self) -> str:
        self._i = (self._i + 1) % len(self.keys)
        return self.actual()

    def ejecutar(self, fn: Callable[[str], T]) -> T:
        """Llama `fn(key)`. Si revienta por cuota, rota de key y reintenta con espera.

        Un error que NO es de cuota se propaga tal cual: un prompt mal armado no se
        arregla reintentando seis veces, y esconderlo cuesta minutos de depuración.
        """
        ultimo: BaseException | None = None

        for intento in range(self.max_intentos):
            self.llamadas += 1
            try:
                return fn(self.actual())
            except Exception as e:  # noqa: BLE001
                if not es_error_de_cuota(e):
                    raise
                ultimo = e
                self.agotadas[self._i] = self.agotadas.get(self._i, 0) + 1
                self.reintentos += 1
                self.rotar()
                # Dos condiciones para dormir, y las dos importan:
                #  - Con más de una key, primero se prueban todas: rotar es gratis.
                #  - NUNCA dormir después del último intento. Esa espera no la
                #    aprovecha nadie: al volver del sleep se sale del bucle igual.
                #    Eran 15 s de silencio puro frente al jurado.
                ultimo_intento = intento + 1 >= self.max_intentos
                if intento + 1 >= len(self.keys) and not ultimo_intento:
                    espera = min(self.espera_base * (2**intento), self.espera_maxima)
                    self.dormir(espera * (0.7 + 0.6 * random.random()))

        raise RuntimeError(
            f"Las {len(self.keys)} keys respondieron cuota agotada tras "
            f"{self.max_intentos} intentos. Última: {ultimo}"
        ) from ultimo

    def estado(self) -> str:
        """Línea para el panel. Se muestra a propósito durante la corrida del eval."""
        total_429 = sum(self.agotadas.values())
        return (
            f"key {self._i + 1}/{len(self.keys)} · {self.llamadas} llamadas · "
            f"{total_429} respuestas de cuota agotada (respetando el tier gratis)"
        )
