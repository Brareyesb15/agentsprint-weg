"""Guard de citas determinista. Corre ANTES de mostrar cualquier respuesta.

Por qué existe en código y no en el prompt: el hito de mayor peso exige que *todas*
las respuestas estén ancladas. Si esa regla vive en el prompt es una moneda al aire
cada turno — basta una pregunta que el modelo "cree saber" para perder el hito.
Acá es mecánico, y emite el evento `verify`, así que además se VE funcionando.

Cero llamadas al modelo. Solo regex, normalización de unidades y comparación.

Revisa dos cosas:
  1. ¿Hubo consulta al conocimiento en este turno?
  2. ¿Los números que dice la respuesta aparecen de verdad en la evidencia?

La "evidencia" son dos cosas, y la segunda es la que evita un falso negativo grave:
  - los `snippet` de las fuentes citadas, y
  - los resultados de las herramientas de cálculo del turno.
Sin lo segundo, el guard bloquearía un payback de 14 meses calculado en Python
solo porque "14" no aparece en ninguna hoja de datos — que es justo el número que
SÍ es confiable, porque no lo produjo el modelo.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from agent.sources import (
    Cantidad,
    Source,
    coincide,
    extraer_cantidades,
    extraer_codigos,
)

TOLERANCIA_POR_DEFECTO = 0.02  # 2%: cubre el redondeo de catálogo (3,7 kW vs 5 HP)


@dataclass
class VerifyResult:
    ok: bool
    checked: int
    confirmed: int
    detail: str
    faltantes: list[Cantidad] = field(default_factory=list)
    codigos_sin_respaldo: list[str] = field(default_factory=list)
    codigos_contradichos: list[str] = field(default_factory=list)
    """Códigos que CONTRADICEN la fuente: la evidencia trae otro código con el mismo
    prefijo. Es el caso "la hoja dice IP67 y la respuesta dice IP68" — un error de
    especificación, no un typo. Se reporta bien visible en `detail` aunque por
    defecto no bloquee (ver `codigos_bloquean`)."""
    hubo_consulta: bool = True
    respaldos: list[str] = field(default_factory=list)
    """Etiquetas de las fuentes que respaldaron al menos un valor.

    Sirve para que el panel muestre como cita SOLO lo que de verdad sostuvo la
    respuesta. Si la búsqueda trajo 3 fragmentos y la respuesta usó 1, pintar los
    3 invita la peor pregunta del jurado: "¿por qué cita una hoja que no usó?".
    """

    def to_event_data(self) -> dict[str, Any]:
        """Exactamente los 4 campos que team/CONTRATOS.md define para `verify`."""
        return {
            "ok": self.ok,
            "checked": self.checked,
            "confirmed": self.confirmed,
            "detail": self.detail,
        }


def verificar(
    respuesta: str,
    sources: Sequence[Source],
    resultados_calculo: Iterable[Any] = (),
    *,
    hubo_consulta: bool = True,
    exigir_consulta: bool = True,
    tolerancia: float = TOLERANCIA_POR_DEFECTO,
    codigos_bloquean: bool = False,
) -> VerifyResult:
    """Verifica una respuesta antes de emitirla.

    `hubo_consulta`   lo pasa el loop: True si se llamó al menos una herramienta
                      registrada con `es_conocimiento=True` en este turno.
    `exigir_consulta` False solo para turnos que no afirman nada del mundo
                      (un saludo, una repregunta). El loop decide.
    """
    # --- Puerta 0: ¿hay respuesta? -----------------------------------------
    # Un cierre vacío pasa de verdad: sucede cuando el modelo devuelve solo partes
    # de pensamiento sin texto, o cuando corta por SAFETY o MAX_TOKENS. Sin esta
    # puerta, el panel pintaba el check verde "verificado" y un `token` con texto
    # vacío: la peor combinación posible en pantalla, porque parece que funcionó.
    if len(respuesta.strip()) < 10:
        return VerifyResult(
            ok=False,
            checked=0,
            confirmed=0,
            detail="BLOQUEADA: el modelo no produjo una respuesta con contenido.",
            hubo_consulta=hubo_consulta,
        )

    afirmaciones = extraer_cantidades(respuesta)

    # --- Puerta 1: ¿se consultó el conocimiento? ---------------------------
    if exigir_consulta and not hubo_consulta:
        return VerifyResult(
            ok=False,
            checked=len(afirmaciones),
            confirmed=0,
            detail=(
                "BLOQUEADA: la respuesta se produjo sin consultar el conocimiento. "
                "El modelo iba a responder de memoria."
            ),
            faltantes=list(afirmaciones),
            hubo_consulta=False,
        )

    # --- Evidencia disponible ---------------------------------------------
    # Cada pieza de evidencia sabe si vino de una fuente citada o de un cálculo.
    # La diferencia importa: los números de un cálculo llegan sin unidad y hay que
    # dejarlos respaldar afirmaciones con unidad; los de una fuente, no.
    evidencia: list[tuple[Cantidad, str, bool]] = []
    for s in sources:
        for c in extraer_cantidades(s.snippet):
            evidencia.append((c, s.etiqueta(), False))

    for r in resultados_calculo:
        for c in extraer_cantidades(_a_texto(r)):
            evidencia.append((c, "cálculo determinista", True))

    # La evidencia para los CÓDIGOS incluye los metadatos de la cita, no solo el
    # snippet: cuando la respuesta escribe "según ficha_ZX-100.md, Sección 1", ese
    # nombre de archivo ES la cita, no una afirmación sin respaldo. Sin esto el
    # panel avisaba "referencia no vista en la fuente" sobre la fuente misma.
    texto_evidencia = " ".join(
        f"{s.doc} {s.section} {s.snippet}" for s in sources
    ).lower()
    texto_evidencia += " " + " ".join(_a_texto(r) for r in resultados_calculo).lower()

    # --- Puerta 2: cada número dicho tiene que estar en la evidencia -------
    confirmadas: list[tuple[Cantidad, str, str]] = []
    faltantes: list[Cantidad] = []

    for a in afirmaciones:
        hallazgo = None
        for b, origen, es_calculo in evidencia:
            modo = coincide(a, b, tolerancia, permitir_sin_unidad=es_calculo)
            if modo is not None:
                hallazgo = (a, origen, modo)
                break
        if hallazgo:
            confirmadas.append(hallazgo)
        else:
            faltantes.append(a)

    # --- Códigos y referencias --------------------------------------------
    sueltos = [c for c in extraer_codigos(respuesta) if c.lower() not in texto_evidencia]
    contradichos, codigos_sueltos = _clasificar_codigos(sueltos, texto_evidencia)

    ok = not faltantes and not (contradichos and codigos_bloquean)
    return VerifyResult(
        ok=ok,
        checked=len(afirmaciones),
        confirmed=len(confirmadas),
        detail=_redactar_detalle(
            confirmadas, faltantes, codigos_sueltos, contradichos, sources
        ),
        faltantes=faltantes,
        codigos_sin_respaldo=codigos_sueltos,
        codigos_contradichos=contradichos,
        hubo_consulta=hubo_consulta,
        respaldos=sorted({origen for _, origen, _ in confirmadas}),
    )


def mensaje_degradacion(res: VerifyResult) -> str:
    """Degradación honesta: qué decir cuando el guard bloquea.

    Nunca inventar, nunca callar. Se nombra el valor exacto que no se pudo confirmar.
    """
    if not res.hubo_consulta:
        return (
            "No puedo responder eso todavía: no alcancé a consultar la documentación "
            "en este turno, y no voy a afirmar nada sin fuente."
        )
    if res.faltantes:
        valores = ", ".join(f.texto for f in res.faltantes)
        return (
            f"No puedo confirmar {valores} en las fuentes que tengo. "
            "Prefiero decírtelo antes que darte un dato que no está en la documentación."
        )
    return "No puedo confirmar la respuesta contra las fuentes disponibles."


# ---------------------------------------------------------------------------
# internos
# ---------------------------------------------------------------------------


def _clasificar_codigos(
    sueltos: list[str], texto_evidencia: str
) -> tuple[list[str], list[str]]:
    """Separa códigos que CONTRADICEN la fuente de los que solo no se vieron.

    Contradice: la evidencia trae otro código con el mismo prefijo alfabético.
    "IP67" en la fuente y "IP68" en la respuesta es un error de especificación —
    exactamente lo que los jueces auditan.
    No visto: el prefijo no aparece en ninguna parte. Puede venir de la pregunta o
    ser un typo, así que solo se avisa.
    """
    contradichos, avisos = [], []
    for c in sueltos:
        m = re.match(r"^[A-Za-z]{2,}", c)
        if m and m.group().lower() in texto_evidencia:
            contradichos.append(c)
        else:
            avisos.append(c)
    return contradichos, avisos


def _a_texto(x: Any) -> str:
    if isinstance(x, str):
        return x
    if isinstance(x, dict):
        return " ".join(f"{k} {_a_texto(v)}" for k, v in x.items())
    if isinstance(x, (list, tuple, set)):
        return " ".join(_a_texto(v) for v in x)
    return str(x)


def _redactar_detalle(
    confirmadas: list[tuple[Cantidad, str, str]],
    faltantes: list[Cantidad],
    codigos: list[str],
    contradichos: list[str],
    sources: Sequence[Source],
) -> str:
    total = len(confirmadas) + len(faltantes)
    partes: list[str] = []

    if total == 0:
        partes.append("la respuesta no afirma ningún valor numérico")
    else:
        docs = sorted({origen for _, origen, _ in confirmadas})
        donde = f" en {', '.join(docs)}" if docs else ""
        partes.append(f"{len(confirmadas)}/{total} valores confirmados{donde}")

    equivalentes = [c for c in confirmadas if c[2] == "equivalente"]
    if equivalentes:
        detalle = "; ".join(f"{c[0].texto} (por conversión de unidades)" for c in equivalentes)
        partes.append(f"coincidencias por equivalencia: {detalle}")

    if faltantes:
        partes.append(
            "SIN RESPALDO: " + ", ".join(f.texto for f in faltantes)
        )

    if contradichos:
        partes.append("CONTRADICE LA FUENTE: " + ", ".join(contradichos))

    if codigos:
        partes.append("aviso, referencias no vistas en la fuente: " + ", ".join(codigos))

    if not faltantes and total > 0 and not sources:
        partes.append("aviso: sin fuentes citadas, todo salió de cálculo determinista")

    return " · ".join(partes)
