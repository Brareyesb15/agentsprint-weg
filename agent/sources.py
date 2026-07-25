"""Forma canónica de una fuente + normalización de números y unidades.

Esto existe porque el guard de citas tiene que responder una pregunta incómoda:
¿"3,7 kW" y "5 HP" son el mismo número? Como texto no se parecen en nada.
Normalizados a vatios son 3700 y 3728,5 — o sea el mismo motor con 0,77% de
diferencia por redondeo de catálogo. Sin esto, el guard bloquearía respuestas
correctas, que en vivo es peor que no tener guard.

Nada de acá depende del reto: son unidades físicas y separadores decimales.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

# ---------------------------------------------------------------------------
# Fuente
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Source:
    """Una cita. `snippet` DEBE ser texto literal de la fuente, no un resumen:
    el guard verifica los números contra este campo."""

    doc: str
    section: str = ""
    page: int | None = None
    snippet: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "doc": self.doc,
            "section": self.section,
            "page": self.page,
            "snippet": self.snippet,
        }

    def etiqueta(self) -> str:
        """Cómo se nombra esta fuente en un texto para humanos."""
        partes = [self.doc]
        if self.section:
            partes.append(self.section)
        if self.page is not None:
            partes.append(f"pág. {self.page}")
        return ", ".join(partes)


# ---------------------------------------------------------------------------
# Unidades
# ---------------------------------------------------------------------------

# Cada familia mapea unidad -> factor hacia la unidad canónica de la familia.
# Solo se comparan números de la MISMA familia. Un número sin unidad reconocida
# se compara solo numéricamente.
FAMILIAS: dict[str, dict[str, float]] = {
    "potencia": {"w": 1.0, "kw": 1e3, "mw": 1e6, "hp": 745.699872, "cv": 735.49875},
    "tension": {"v": 1.0, "kv": 1e3, "mv": 1e-3},
    "corriente": {"a": 1.0, "ma": 1e-3, "ka": 1e3},
    "frecuencia": {"hz": 1.0, "khz": 1e3, "mhz": 1e6, "ghz": 1e9},
    "longitud": {"mm": 1e-3, "cm": 1e-2, "dm": 1e-1, "m": 1.0, "km": 1e3},
    "masa": {"g": 1e-3, "kg": 1.0, "t": 1e3},
    "presion": {"pa": 1.0, "kpa": 1e3, "mpa": 1e6, "bar": 1e5, "psi": 6894.757},
    "temperatura": {"°c": 1.0, "ºc": 1.0, "c°": 1.0},
    "rotacion": {"rpm": 1.0, "min-1": 1.0, "r/min": 1.0},
    "porcentaje": {"%": 1.0},
    "tiempo": {"ms": 1e-3, "s": 1.0, "seg": 1.0, "min": 60.0, "h": 3600.0},
    "energia": {"wh": 1.0, "kwh": 1e3, "mwh": 1e6, "j": 1 / 3600},
}

# Índice inverso unidad -> (familia, factor). Se resuelve la unidad más larga primero
# para que "kwh" no se lea como "k" + "wh", ni "ka" como "k" + "a".
_INDICE: dict[str, tuple[str, float]] = {}
for _fam, _unidades in FAMILIAS.items():
    for _u, _f in _unidades.items():
        # 'm' (metro) y 'ms' (milisegundo) etc. pueden chocar entre familias.
        # Se conserva la PRIMERA familia declarada para esa unidad y se registra
        # el choque en AMBIGUAS, que el guard trata como "unidad no confiable".
        if _u in _INDICE and _INDICE[_u][0] != _fam:
            _INDICE[_u] = ("ambigua", 1.0)
        else:
            _INDICE[_u] = (_fam, _f)

UNIDADES_CONOCIDAS = sorted(_INDICE.keys(), key=len, reverse=True)

# Palabras que, si están justo antes de un número, indican que ese número es una
# referencia al documento y no una afirmación sobre el mundo. No se verifican.
#
# OJO con lo que NO está en esta lista, y es deliberado: "v" y "p" sueltas.
# Parecen abreviaturas inocentes de "versión" y "página", pero "V" es la unidad de
# tensión. Con "v" en la lista, en "Alimentación 24 V, distancia 12 mm" el guard
# descartaba el 12 porque su token previo era "V" — o sea, quedaba ciego a
# CUALQUIER cifra que siguiera a un voltaje, que en una hoja de datos eléctrica es
# media ficha. Una abreviatura ambigua no vale perder verificaciones.
CONTEXTO_IGNORAR = {
    "página", "pagina", "páginas", "paginas", "pág", "pag", "págs", "pags", "pp",
    "page", "pages", "sección", "seccion", "secciones", "sec", "section",
    "tabla", "table", "tablas", "figura", "fig", "capítulo", "capitulo",
    "paso", "pasos", "item", "ítem", "punto", "nota", "versión", "version",
    "anexo", "apartado", "línea", "linea",
}

# Conectores que CONTINÚAN una enumeración de referencias: "páginas 50 y 51",
# "tablas 3, 4 y 5". Sin esto, el primer número se ignoraba y el segundo no —
# y el segundo, al no estar en la fuente, BLOQUEABA la respuesta completa.
# Verificado en vivo: el agente citaba "páginas 50 y 51" y el guard reportaba
# "no puedo confirmar 51", tumbando una respuesta correcta.
_CONECTORES_ENUMERACION = {"y", "e", "o", "and", "a", "-", "–", "hasta", "al"}

# Marcador de lista numerada al inicio de renglón: "1." o "2)".
_RE_MARCADOR_LISTA = re.compile(r"^\d{1,3}[.)]$")
_BULLETS = {"-", "*", "+", "•", ">", "|"}

# Las únicas palabras de una sola letra del español. Si una de estas aparece en
# minúscula justo después de un número, es una palabra, no una unidad.
_PALABRAS_DE_UNA_LETRA = {"a", "e", "o", "u", "y"}

_RE_NUMERO = re.compile(r"^[+-]?\d[\d.,]*$")
_RE_MILES_PUNTO = re.compile(r"^\d{1,3}(\.\d{3})+$")
_RE_MILES_COMA = re.compile(r"^\d{1,3}(,\d{3})+$")
_RE_CODIGO = re.compile(r"^(?=.*[A-Za-z])(?=.*\d)[A-Za-z0-9][A-Za-z0-9\-/_.]*$")


# ---------------------------------------------------------------------------
# Normalización de un número escrito
# ---------------------------------------------------------------------------


def normalizar_numero(texto: str) -> float | None:
    """Convierte un número escrito a float, resolviendo coma/punto decimal.

    Regla (documentada a propósito, porque es ambigua en la vida real):
      1. Si están AMBOS separadores, el ÚLTIMO es el decimal.
      2. Si solo hay comas y forman grupos de 3 exactos -> miles. Si no -> decimal.
      3. Si solo hay puntos y forman grupos de 3 exactos -> miles. Si no -> decimal.

    Con eso: "1.500" -> 1500 · "3,7" -> 3.7 · "1.234,56" -> 1234.56 · "3.7" -> 3.7

    Limitación conocida y aceptada: "1,500" con la intención de 1,5 (tres decimales)
    se lee como 1500. Es rarísimo en hojas de datos; el caso frecuente es el de miles.
    """
    t = texto.strip().replace(" ", "").replace(" ", "")
    if not t or not _RE_NUMERO.match(t):
        return None

    signo = -1.0 if t.startswith("-") else 1.0
    t = t.lstrip("+-")

    tiene_punto, tiene_coma = "." in t, "," in t

    if tiene_punto and tiene_coma:
        if t.rfind(",") > t.rfind("."):
            t = t.replace(".", "").replace(",", ".")
        else:
            t = t.replace(",", "")
    elif tiene_coma:
        t = t.replace(",", "") if _es_miles(t, _RE_MILES_COMA) else t.replace(",", ".")
    elif tiene_punto:
        if _es_miles(t, _RE_MILES_PUNTO):
            t = t.replace(".", "")

    try:
        return signo * float(t)
    except ValueError:
        return None


def _es_miles(t: str, patron: re.Pattern[str]) -> bool:
    """¿El separador agrupa miles y no es decimal?

    Además del patrón de grupos de 3, se exige que la parte entera no empiece con
    cero: "0,085" tiene forma de grupo de 3 pero es 85 milésimas, no 85. Confundirlo
    escala el número mil veces, que es exactamente el error que el guard debe cazar.
    """
    return bool(patron.match(t)) and not t.startswith("0")


def partir_unidad(token: str) -> tuple[str, str | None]:
    """Separa '24V' -> ('24', 'v'). Si no hay unidad reconocida devuelve (token, None)."""
    bajo = token.lower()
    for u in UNIDADES_CONOCIDAS:
        if bajo.endswith(u) and len(bajo) > len(u):
            cabeza = token[: len(token) - len(u)]
            if _RE_NUMERO.match(cabeza.strip()):
                return cabeza, u
    return token, None


def canonizar(valor: float, unidad: str | None) -> tuple[float, str | None]:
    """Lleva (valor, unidad) a la unidad canónica de su familia.

    Devuelve (valor_canonico, familia). Si la unidad es desconocida o ambigua,
    familia es None y el valor se devuelve tal cual.
    """
    if unidad is None:
        return valor, None
    fam, factor = _INDICE.get(unidad.lower(), (None, 1.0))
    if fam is None or fam == "ambigua":
        return valor, None
    return valor * factor, fam


# ---------------------------------------------------------------------------
# Extracción de afirmaciones numéricas de un texto
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Cantidad:
    texto: str            # como apareció, p.ej. "3,7 kW"
    valor: float          # ya normalizado, p.ej. 3.7
    unidad: str | None    # "kw" o None
    canonico: float       # 3700.0
    familia: str | None   # "potencia" o None

    def __str__(self) -> str:  # pragma: no cover - solo para mensajes
        return self.texto


_BASURA = " \t\n\r.,;:!?()[]{}\"'«»“”…*_`~#<>|=+"


def _limpiar(token: str) -> str:
    """Quita la puntuación y el marcado que rodean un token.

    Dos entradas de la lista tienen historia y no se deben quitar:

    - El PUNTO: "35 mA." es la forma normal de terminar una frase en una hoja de
      datos. Sin quitarlo, "mA." no se reconoce como unidad y el número queda sin
      familia (entonces 35 mA "coincidiría" con 35 de cualquier otra cosa).

    - Los ASTERISCOS de markdown: el modelo escribe "**24 V DC**" para resaltar.
      Sin quitarlos, "**24" no se lee como número, el guard no encuentra NINGUNA
      afirmación y da PASA en vacío. Verificado en vivo: el guard reportaba
      "la respuesta no afirma ningún valor numérico" sobre una respuesta que
      afirmaba dos. Era un guard decorativo.
    """
    return token.strip(_BASURA)


def _es_numero(tok: str) -> bool:
    return bool(_RE_NUMERO.match(tok))


def _inicio_util(tokens: list[str]) -> int:
    """Índice del primer token que puede ser una afirmación, saltando el marcador.

    Existe por un fallo determinista y muy visible: si el usuario pregunta "¿cómo lo
    instalo?", el modelo responde una lista numerada, y el "1." de cada renglón se
    leía como la cifra 1. Ninguno de esos números está en la fuente, así que el guard
    bloqueaba la respuesta y en pantalla se proyectaba "No puedo confirmar 1, 2, 3".
    """
    i = 0
    while i < len(tokens) and tokens[i] in _BULLETS:
        i += 1
    if i < len(tokens) and _RE_MARCADOR_LISTA.match(tokens[i]):
        i += 1
    return i


def extraer_cantidades(texto: str) -> list[Cantidad]:
    """Saca las afirmaciones numéricas de un texto en prosa.

    Trabaja por tokens (no con un regex sobre la prosa) porque así los códigos de
    producto no se confunden con números: 'IME18-12NNSZC0S' es UN token con letras
    y dígitos, se descarta entero. Un regex de números lo partiría en 18 y 12 y el
    guard intentaría verificar cifras que nunca fueron una afirmación.

    Y recorre RENGLÓN por renglón, no el texto entero de una vez, por dos razones:
    para poder saltar el marcador de las listas numeradas, y porque una referencia
    tipo "página 4" no cruza de un renglón al siguiente.
    """
    cantidades: list[Cantidad] = []
    for linea in texto.splitlines():
        cantidades.extend(_cantidades_de_linea(linea))
    return cantidades


def _cantidades_de_linea(linea: str) -> list[Cantidad]:
    cantidades: list[Cantidad] = []
    tokens = linea.split()
    inicio = _inicio_util(tokens)

    # Mientras sea True, los números son referencias al documento, no afirmaciones.
    # Se enciende con "página"/"tabla"/… y se apaga al salir de la enumeración.
    en_referencia = False

    for i in range(inicio, len(tokens)):
        tok = _limpiar(tokens[i])
        if not tok:
            continue

        previo = _limpiar(tokens[i - 1]).lower().rstrip(".") if i > inicio else ""
        if previo in CONTEXTO_IGNORAR:
            en_referencia = True
        elif previo and previo not in _CONECTORES_ENUMERACION and not _es_numero(previo):
            en_referencia = False

        if en_referencia:
            continue

        cabeza, unidad = partir_unidad(tok)

        # Código de producto / referencia: letras + dígitos y no es número+unidad.
        if unidad is None and _RE_CODIGO.match(tok):
            continue

        valor = normalizar_numero(cabeza)
        if valor is None:
            continue

        # "24 V": la unidad puede venir en el token siguiente.
        if unidad is None and i + 1 < len(tokens):
            crudo = _limpiar(tokens[i + 1])
            siguiente = crudo.lower()
            # Trampa del español: en "de 3 a 5 metros" la preposición "a" NO es
            # amperios. Pero exigir mayúscula para TODA unidad de una letra era
            # demasiado: dejaba fuera "85 g", "3 m", "30 s" — todas legítimas y en
            # minúscula por convención. Así que el filtro es una lista de las únicas
            # palabras de una letra que existen en español, y solo cuando vienen en
            # minúscula: "A" mayúscula sigue siendo amperios, "a" minúscula no.
            ambigua = (
                len(siguiente) == 1
                and crudo.islower()
                and siguiente in _PALABRAS_DE_UNA_LETRA
            )
            if siguiente in _INDICE and not ambigua:
                unidad = siguiente

        canonico, familia = canonizar(valor, unidad)
        etiqueta = f"{cabeza} {unidad}".strip() if unidad else cabeza
        cantidades.append(
            Cantidad(
                texto=etiqueta,
                valor=valor,
                unidad=unidad,
                canonico=canonico,
                familia=familia,
            )
        )

    return cantidades


def extraer_codigos(texto: str) -> list[str]:
    """Códigos/referencias tipo 'IME18-12NNSZC0S' o 'IP67'.

    El guard los reporta como aviso, no como falla: un código escrito con un guion
    de más no debería tumbar una respuesta correcta en vivo.
    """
    vistos: list[str] = []
    for bruto in texto.split():
        tok = _limpiar(bruto)
        if len(tok) < 3:
            continue
        _, unidad = partir_unidad(tok)
        if unidad is not None:
            continue
        if _RE_CODIGO.match(tok) and tok not in vistos:
            vistos.append(tok)
    return vistos


# ---------------------------------------------------------------------------
# Comparación
# ---------------------------------------------------------------------------


# Cómo se nombra cada unidad en prosa, además de su símbolo. Sirve para leer el
# encabezado de una columna: "Full Load Amps" dice que la columna son amperios.
_PALABRAS_DE_UNIDAD: dict[str, str] = {
    "amp": "a", "amps": "a", "ampere": "a", "amperes": "a", "amperio": "a", "amperios": "a",
    "volt": "v", "volts": "v", "voltio": "v", "voltios": "v", "tension": "v", "tensión": "v",
    "watt": "w", "watts": "w", "vatio": "w", "vatios": "w",
    "kilowatt": "kw", "kilowatts": "kw", "kilovatio": "kw", "kilovatios": "kw",
    "hp": "hp", "horsepower": "hp", "caballos": "hp",
    "hertz": "hz", "hercio": "hz", "hercios": "hz",
    "rpm": "rpm", "revoluciones": "rpm",
    "kg": "kg", "kilogramo": "kg", "kilogramos": "kg",
    "mm": "mm", "milimetro": "mm", "milímetro": "mm", "milimetros": "mm", "milímetros": "mm",
    "metro": "m", "metros": "m",
    "segundo": "s", "segundos": "s",
    "porciento": "%", "porcentaje": "%",
}


def unidades_mencionadas(texto: str) -> set[str]:
    """Unidades canónicas que el texto NOMBRA, por símbolo o por palabra.

    Existe por las tablas de catálogo: la columna se titula "Full Load Amps" y las
    celdas traen solo "11.4", sin la A. Sin esto, el guard trata ese 11.4 como un
    número sin unidad y se niega a respaldar una respuesta que diga "11,4 A" —
    bloqueando una respuesta correcta, que en vivo es peor que no tener guard.
    """
    encontradas: set[str] = set()
    for bruto in texto.split():
        tok = _limpiar(bruto).lower()
        if not tok:
            continue
        if tok in _INDICE and _INDICE[tok][0] != "ambigua":
            encontradas.add(tok)
        elif tok in _PALABRAS_DE_UNIDAD:
            encontradas.add(_PALABRAS_DE_UNIDAD[tok])
        else:
            _, unidad = partir_unidad(tok)
            if unidad:
                encontradas.add(unidad)
    return encontradas


def coincide(
    a: Cantidad,
    b: Cantidad,
    tolerancia: float,
    *,
    permitir_sin_unidad: bool = False,
) -> str | None:
    """¿`a` (dicho en la respuesta) está respaldado por `b` (visto en la evidencia)?

    Devuelve None si no coinciden, o cómo coincidieron:
      "exacto"      mismo número, mismas unidades (o la afirmación no lleva unidad)
      "equivalente" misma familia física, DISTINTA unidad, dentro de la tolerancia

    `permitir_sin_unidad` se activa solo para evidencia que viene de un cálculo
    determinista: ahí los números llegan pelados (`{"potencia_w": 0.84}`) y aun así
    tienen que poder respaldar una afirmación con unidad ("0,84 W").
    """
    # 1. Mismo valor y misma unidad: nada que convertir.
    if a.familia == b.familia and _cerca(a.valor, b.valor, 1e-9):
        return "exacto"

    # 2. Misma familia física en OTRA unidad: 3,7 kW vs 5 HP.
    #    La tolerancia existe para absorber el redondeo de catálogo entre unidades
    #    distintas. Aplicarla con la MISMA unidad convertía el guard en un colador:
    #    "3,77 kW" pasaba como "confirmado por conversión de unidades" contra una
    #    fuente que dice 3,7 kW. No hay conversión ninguna ahí: es otro número.
    if (
        a.familia is not None
        and a.familia == b.familia
        and a.unidad != b.unidad
        and _cerca(a.canonico, b.canonico, tolerancia)
    ):
        return "equivalente"

    # 3. Afirmación SIN unidad contra cualquier número igual. Es asimétrico a
    #    propósito: una afirmación CON unidad no se respalda con un número pelado.
    #    Si no, la fuente "Vida útil: 100 000 ciclos" (que tokeniza como 100 y 000)
    #    confirmaba "el consumo en reposo es de 0 W".
    if a.familia is None and _cerca(a.valor, b.valor, 1e-9):
        return "exacto"

    # 4. Excepción acotada: los resultados de cálculo llegan sin unidad.
    if permitir_sin_unidad and b.familia is None and _cerca(a.valor, b.valor, 1e-9):
        return "exacto"

    return None


def _cerca(x: float, y: float, tolerancia_relativa: float) -> bool:
    if x == y:
        return True
    escala = max(abs(x), abs(y))
    if escala == 0:
        return True
    return abs(x - y) / escala <= tolerancia_relativa
