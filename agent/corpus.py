"""Carga e indexado del corpus de `data/`, por secciones.

Por qué búsqueda por palabras y no base vectorial: las especificaciones son números
y reglas. "3,7 kW" y "5 HP" no se parecen como texto pero son lo mismo, así que la
similitud semántica es la primitiva equivocada para el paso crítico. Los jueces
tampoco construyen un buscador semántico: construyen un grafo de conocimiento con reglas.

Se indexa por SECCIÓN (los `## ` del markdown) porque la cita tiene que poder decir
"documento X, sección Y" — una cita a nivel de archivo completo no sirve para la rúbrica.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from agent.sources import Source

_RE_PALABRA = re.compile(r"[a-z0-9°%/\-]+")
# Palabras que aparecen en todo y no discriminan nada.
_VACIAS = {
    "el", "la", "los", "las", "un", "una", "unos", "unas", "de", "del", "al",
    "y", "o", "u", "e", "en", "con", "sin", "para", "por", "que", "es", "son",
    "se", "su", "sus", "lo", "a", "cual", "cuanto", "cuanta", "como", "donde",
    "the", "of", "and", "for", "to", "in",
}


def _sin_tildes(t: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn"
    )


def tokenizar(texto: str) -> list[str]:
    return [
        p for p in _RE_PALABRA.findall(_sin_tildes(texto.lower())) if p not in _VACIAS
    ]


def _titulo_de_pagina(texto: str, maximo: int = 70) -> str:
    """Heurística de encabezado: la primera línea corta y con letras de la página.

    Sirve para que la cita diga "hoja de datos X, Datos técnicos, pág. 2" en vez de
    "hoja de datos X, pág. 2". Si no encuentra nada razonable devuelve cadena vacía,
    y `Source.etiqueta()` simplemente omite la sección.
    """
    for linea in texto.splitlines():
        l = linea.strip()
        if 3 <= len(l) <= maximo and any(c.isalpha() for c in l):
            return l
    return ""


@dataclass
class Fragmento:
    doc: str
    section: str
    page: int | None
    texto: str

    def como_source(self, snippet: str | None = None) -> Source:
        return Source(
            doc=self.doc,
            section=self.section,
            page=self.page,
            snippet=snippet if snippet is not None else self.texto,
        )


class Corpus:
    """Índice en memoria del corpus. Se construye una vez al arrancar."""

    def __init__(self, fragmentos: list[Fragmento]) -> None:
        self.fragmentos = fragmentos
        self.avisos: list[str] = []
        # El NOMBRE del documento entra al índice a propósito: si alguien pregunta
        # por "ZX-100", las secciones del archivo de ese producto tienen que ganarle
        # a una mención de pasada en el archivo de otro producto.
        self._tokens = [
            set(tokenizar(f"{f.doc} {f.section} {f.texto}")) for f in fragmentos
        ]

    # -- construcción ------------------------------------------------------

    @classmethod
    def desde_directorio(cls, directorio: str | Path) -> "Corpus":
        """Indexa `.md` y `.pdf` del directorio, recursivamente.

        El PDF NO es opcional: el corpus real de una marca son hojas de datos en
        PDF. Si esto solo leyera markdown, poner las hojas de SICK en `data/` daría
        cero fragmentos, la búsqueda devolvería vacío y el guard bloquearía el 100%
        de las respuestas con un número — falla ruidosa, pero a las 8:40 de la mañana.

        Del PDF sale un fragmento POR PÁGINA con su número de página, porque la cita
        que premia la rúbrica es "hoja de datos X, página 2", no "archivo X".
        """
        raiz = Path(directorio)
        fragmentos: list[Fragmento] = []
        avisos: list[str] = []

        archivos = sorted(
            [p for p in raiz.rglob("*") if p.suffix.lower() in {".md", ".pdf"}]
        )
        for archivo in archivos:
            if archivo.name.upper() in {"FUENTES.MD", "README.MD"}:
                continue
            if archivo.suffix.lower() == ".pdf":
                frags, aviso = cls._partir_pdf(archivo)
                fragmentos.extend(frags)
                if aviso:
                    avisos.append(aviso)
            else:
                fragmentos.extend(cls._partir(archivo))

        corpus = cls(fragmentos)
        corpus.avisos = avisos
        return corpus

    @staticmethod
    def _partir_pdf(archivo: Path) -> tuple[list[Fragmento], str | None]:
        """Un fragmento por página. Devuelve (fragmentos, aviso).

        El aviso avisa de páginas sin texto extraíble: eso significa que la hoja de
        datos es una IMAGEN y necesita visión/OCR. Es un caso real y verificado
        (las fichas individuales de Pfannenberg traen metadatos de Photoshop).
        Mejor saberlo al cargar el corpus que descubrirlo cuando el agente diga
        que no encuentra nada.
        """
        try:
            import fitz  # pymupdf
        except ImportError:  # pragma: no cover
            return [], f"{archivo.name}: pymupdf no está instalado, PDF ignorado"

        fragmentos: list[Fragmento] = []
        sin_texto = 0
        try:
            with fitz.open(archivo) as doc:
                for n, pagina in enumerate(doc, start=1):
                    texto = (pagina.get_text() or "").strip()
                    if len(texto) < 20:
                        sin_texto += 1
                        continue
                    fragmentos.append(
                        Fragmento(
                            doc=archivo.name,
                            section=_titulo_de_pagina(texto),
                            page=n,
                            texto=texto,
                        )
                    )
        except Exception as e:  # noqa: BLE001 - un PDF corrupto no debe tumbar el arranque
            return [], f"{archivo.name}: no se pudo leer ({type(e).__name__}: {e})"

        aviso = None
        if sin_texto:
            aviso = (
                f"{archivo.name}: {sin_texto} página(s) sin texto extraíble. "
                "Probablemente sea un PDF de imágenes: requiere visión u OCR."
            )
        return fragmentos, aviso

    @staticmethod
    def _partir(archivo: Path) -> list[Fragmento]:
        """Parte un markdown en fragmentos por encabezado `## `."""
        texto = archivo.read_text(encoding="utf-8")
        fragmentos: list[Fragmento] = []
        seccion_actual = "(encabezado)"
        buffer: list[str] = []

        def cerrar() -> None:
            cuerpo = "\n".join(buffer).strip()
            if cuerpo:
                fragmentos.append(
                    Fragmento(
                        doc=archivo.name,
                        section=seccion_actual,
                        page=None,
                        texto=cuerpo,
                    )
                )

        for linea in texto.splitlines():
            if linea.startswith("## "):
                cerrar()
                seccion_actual = linea[3:].strip()
                buffer = []
            else:
                buffer.append(linea)
        cerrar()
        return fragmentos

    # -- consulta ----------------------------------------------------------

    def buscar(self, consulta: str, k: int = 3) -> list[tuple[Fragmento, float]]:
        terminos = set(tokenizar(consulta))
        if not terminos:
            return []
        puntuados: list[tuple[Fragmento, float]] = []
        for frag, tokens in zip(self.fragmentos, self._tokens):
            comunes = terminos & tokens
            if not comunes:
                continue
            puntuados.append((frag, len(comunes) / len(terminos)))
        puntuados.sort(key=lambda p: p[1], reverse=True)
        return puntuados[:k]

    def leer(self, doc: str, section: str | None = None) -> list[Fragmento]:
        return [
            f
            for f in self.fragmentos
            if f.doc.lower() == doc.lower()
            and (section is None or section.lower() in f.section.lower())
        ]

    def lineas_relevantes(self, frag: Fragmento, consulta: str, maximo: int = 3) -> str:
        """Devuelve las líneas del fragmento que responden la consulta.

        El snippet tiene que ser texto LITERAL (el guard lo verifica contra él),
        así que se seleccionan líneas enteras del original — nunca se reescriben.
        """
        terminos = set(tokenizar(consulta))
        candidatas: list[tuple[int, str]] = []
        for linea in frag.texto.splitlines():
            if not linea.strip() or linea.strip().startswith(">"):
                continue
            golpes = len(terminos & set(tokenizar(linea)))
            if golpes:
                candidatas.append((golpes, linea.strip()))
        if not candidatas:
            return frag.texto.strip()
        candidatas.sort(key=lambda c: c[0], reverse=True)
        return "\n".join(l for _, l in candidatas[:maximo])
