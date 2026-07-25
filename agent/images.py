"""Reescalado de imágenes antes de mandarlas al modelo.

Una foto de celular sin tocar consume miles de tokens; bajada de tamaño cuesta
una fracción y se lee igual de bien. Con cuota gratis, esto es la diferencia
entre aguantar la demo y quedarse sin llamadas a mitad del pitch.

El lado máximo va en `.env` (`IMAGE_MAX_SIDE`), no escrito en el código.
"""

from __future__ import annotations

import base64
import io

from PIL import Image, ImageOps

FORMATO_SALIDA = "JPEG"
CALIDAD = 85


def reescalar(datos: bytes, lado_maximo: int = 768) -> tuple[bytes, str]:
    """Reescala manteniendo proporción y corrige la orientación EXIF.

    Lo de EXIF no es adorno: las fotos de celular vienen rotadas por metadato, y
    un modelo de visión leyendo una placa acostada falla de formas raras y difíciles
    de depurar en vivo.

    Devuelve (bytes, mime_type). Si la imagen ya es más chica, igual se recomprime
    a JPEG para normalizar el formato de entrada.
    """
    with Image.open(io.BytesIO(datos)) as img:
        img = ImageOps.exif_transpose(img)
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")

        lado = max(img.size)
        if lado > lado_maximo:
            escala = lado_maximo / lado
            nuevo = (max(1, round(img.width * escala)), max(1, round(img.height * escala)))
            img = img.resize(nuevo, Image.LANCZOS)

        buffer = io.BytesIO()
        img.save(buffer, format=FORMATO_SALIDA, quality=CALIDAD, optimize=True)
        return buffer.getvalue(), "image/jpeg"


def desde_base64(b64: str, lado_maximo: int = 768) -> tuple[bytes, str]:
    """Acepta base64 crudo o data URL (`data:image/png;base64,...`)."""
    if "," in b64 and b64.strip().startswith("data:"):
        b64 = b64.split(",", 1)[1]
    return reescalar(base64.b64decode(b64), lado_maximo)


def ahorro(original: int, final: int) -> str:
    """Frase corta para el panel de trazas. Se ve bien en la demo."""
    if original <= 0:
        return ""
    pct = 100 * (1 - final / original)
    return f"imagen reescalada: {original // 1024} KB -> {final // 1024} KB ({pct:.0f}% menos)"
