"""Configuración desde `.env`. Los nombres son los de team/CONTRATOS.md sección 5.

Regla del proyecto: **el nombre del modelo JAMÁS se escribe en el código.**
Los modelos Gemini 3 están en preview; cambiar de modelo tiene que ser una línea
del `.env`, no una búsqueda por el repo a las 10 de la mañana.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parents[1]


@dataclass
class Config:
    api_keys: list[str] = field(default_factory=list)
    model_name: str = ""
    model_name_light: str = ""
    model_fallbacks: list[str] = field(default_factory=list)
    api_port: int = 8000
    ui_port: int = 5173
    data_dir: Path = RAIZ / "data"
    image_max_side: int = 768
    guard_tolerancia: float = 0.02

    @property
    def hay_keys(self) -> bool:
        return bool(self.api_keys)

    @property
    def cadena_de_modelos(self) -> list[str]:
        """MODEL_NAME primero, después los de respaldo, sin repetidos.

        La cuota del tier gratis es **por modelo** (verificado: 20 requests/día para
        gemini-3.6-flash), así que cuando un modelo se agota el siguiente sigue
        teniendo cuota propia. Rotar solo las keys no alcanza.
        """
        cadena = [self.model_name] + self.model_fallbacks
        vistos: list[str] = []
        for m in cadena:
            if m and m not in vistos:
                vistos.append(m)
        return vistos

    def exigir_keys(self) -> None:
        if not self.api_keys:
            raise RuntimeError(
                "No hay ninguna GOOGLE_API_KEY_1..4 en el .env. "
                "Copia .env.example a .env y pon al menos una."
            )
        if not self.model_name:
            raise RuntimeError("Falta MODEL_NAME en el .env.")


def cargar(env_file: str | Path | None = None) -> Config:
    load_dotenv(env_file or (RAIZ / ".env"), override=False)

    keys = [
        k
        for k in (os.getenv(f"GOOGLE_API_KEY_{i}", "").strip() for i in range(1, 5))
        if k
    ]
    # Compatibilidad: si alguien usó el nombre sin número, también sirve.
    suelta = os.getenv("GOOGLE_API_KEY", "").strip()
    if suelta and suelta not in keys:
        keys.append(suelta)

    data_dir = os.getenv("DATA_DIR", "").strip()
    fallbacks = [
        m.strip() for m in os.getenv("MODEL_FALLBACKS", "").split(",") if m.strip()
    ]
    return Config(
        api_keys=keys,
        model_name=os.getenv("MODEL_NAME", "").strip(),
        model_name_light=os.getenv("MODEL_NAME_LIGHT", "").strip(),
        model_fallbacks=fallbacks,
        api_port=int(os.getenv("API_PORT", "8000")),
        ui_port=int(os.getenv("UI_PORT", "5173")),
        data_dir=(RAIZ / data_dir).resolve() if data_dir else RAIZ / "data",
        image_max_side=int(os.getenv("IMAGE_MAX_SIDE", "768")),
        guard_tolerancia=float(os.getenv("GUARD_TOLERANCIA", "0.02")),
    )
