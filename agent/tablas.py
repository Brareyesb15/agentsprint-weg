"""Parseo de las tablas de datos eléctricos del catálogo. CERO llamadas al modelo.

Existe por un agujero real del guard de citas, medido el 28-jul-2026:

    El snippet que recibía el guard NO era la fila del motor, era la PÁGINA entera.
    La página 50 del brochure W22 son 8.035 caracteres con 1.712 números, porque
    PyMuPDF extrae la tabla por columnas y `Corpus.lineas_relevantes` cae en su
    fallback de "devolver la página" cuando las líneas que hacen match son los
    encabezados (que es siempre, en una tabla).

    Con eso, el guard confirmaba cada cifra contra un pozo de 1.712 números y una
    tolerancia del 2%. Una respuesta que decía "10 HP, 4 polos, 3,3 A, 66 %, 30 kg"
    —cifras del motor de 0,12 kW, el más chico de la tabla— daba `6/6 confirmados`.
    El check verde decía "verificado" sobre una recomendación absurda.

La cura es atar cada número a SU fila. Acá se parsea la tabla a filas para que el
guard verifique contra ~20 números del motor citado, no contra la página entera.

**El parseo es auto-verificable, y ese es el punto.** No se confía en contar
columnas: cada fila candidata tiene que pasar dos pruebas de física antes de
aceptarse (`HP ≈ kW/0,7457` y `P ≈ √3·V·I·cosφ·η`). Si una fila no las pasa, se
descarta y el llamador cae al comportamiento viejo. Falla cerrado: prefiere no
parsear a parsear mal, porque una fila mal alineada es exactamente el error que
este módulo existe para impedir.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from agent.motores import DESLIZAMIENTO_MAX, DESLIZAMIENTO_MIN, HP_A_KW
from agent.sources import Source

# La tabla trae 20 columnas por motor, en este orden. Deducido de los encabezados
# y CONFIRMADO con física en las 90 filas del catálogo (ver `tests/test_tablas.py`).
COLUMNAS = (
    "kw", "hp", "carcasa", "par_nominal_kgfm", "il_in", "tl_tn", "tb_tn", "j_kgm2",
    "t_rotor_trabado_caliente_s", "t_rotor_trabado_frio_s", "peso_kg", "ruido_db",
    "rpm", "rend_50", "rend_75", "rend_100", "fp_50", "fp_75", "fp_100", "in_a",
)

# La tensión de tabulación NO es constante: cada tabla declara la suya en el
# encabezado, y son cuatro distintas en este mismo catálogo (medido el 28-jul-2026):
#   400 V  las tablas de 50 Hz (págs. 34-47)
#   440 V  IE4 60 Hz (pág. 48)
#   380 V  IE3 60 Hz (págs. 50-51)   <- el caso de Colombia
#   220 V  IE2 e IE1 60 Hz (págs. 52-58)
# Hardcodearla en 380 hacía que la prueba eléctrica fallara en todas las tablas de
# 220 V y ese grupo entero quedaba sin parsear. Se lee de la página.
_TENSION = re.compile(r"^(\d{3})\s*V$")
_LINEAS_DE_ENCABEZADO = 45

_ROMANOS = {"II": 2, "IV": 4, "VI": 6, "VIII": 8, "X": 10, "XII": 12}
_MARCADOR_POLOS = re.compile(r"(II|IV|VI|VIII|X|XII)\s*Polos", re.IGNORECASE)
# Las carcasas grandes se publican como un par: `225S/M`, `132M/L`, `355M/L`. Sin
# admitir la barra, el ancla no reconocía el arranque de esas filas y la herramienta
# respondía "no existe" sobre motores que SÍ están en el catálogo — un falso negativo
# peor que el falso positivo original, porque le niega al usuario un producto real.
# Detectado el 28-jul-2026: el 60 HP / 4 polos IE3 (carcasa 225S/M, pág. 50).
_CARCASA = re.compile(r"^[A-Z]{0,2}\d{2,3}[A-Z]{0,2}(/[A-Z]{1,2})?$")
_CLASE = re.compile(r"IE[1-4]", re.IGNORECASE)
_NUMERO = re.compile(r"\d{1,3}(\.\d{3})*(,\d+)?|\d+(,\d+)?")


def tension_de_la_tabla(lineas: list[str]) -> int | None:
    """La tensión a la que esta tabla tabula la corriente, según su propio encabezado."""
    for linea in lineas[:_LINEAS_DE_ENCABEZADO]:
        m = _TENSION.fullmatch(linea)
        if m:
            return int(m.group(1))
    return None

# Holguras de las dos pruebas de física. No son "tolerancias de comparación" sino
# el margen del redondeo de catálogo: 3,7 kW se publica como 5 HP (4,96 exactos).
_HOLGURA_HP = 0.07
_HOLGURA_ELECTRICA = 0.06


def a_numero(texto: str) -> float | None:
    """'7,5' -> 7.5 · '1.250' -> 1250.0 · 'L90S' -> None. Coma decimal, punto de millar."""
    t = texto.strip()
    if not _NUMERO.fullmatch(t):
        return None
    return float(t.replace(".", "").replace(",", "."))


@dataclass(frozen=True)
class FilaMotor:
    """Un motor del catálogo, con sus 20 valores atados entre sí.

    Los valores se guardan como el TEXTO literal de la página, no como float: el
    snippet que lee el guard tiene que llevar las cifras tal como están impresas
    ("7,5", no "7.5"), o la comparación se vuelve otra fuente de falsos negativos.
    """

    doc: str
    section: str
    page: int | None
    polos: int
    tension_v: int
    valores: dict[str, str]

    @property
    def kw(self) -> float | None:
        return a_numero(self.valores["kw"])

    @property
    def hp(self) -> float | None:
        return a_numero(self.valores["hp"])

    @property
    def carcasa(self) -> str:
        return self.valores["carcasa"]

    @property
    def rend_100(self) -> float | None:
        return a_numero(self.valores["rend_100"])

    @property
    def clase_eficiencia(self) -> str | None:
        """IE1..IE4 leídos del título de la tabla. None si el título no la nombra.

        Se lee del título y no se adivina: si la tabla no declara clase, la fila no
        puede afirmar que es IE3, y `seleccionar` la descarta cuando se pide una
        clase. Ofrecer un IE2 a quien pidió IE3 es el mismo defecto de origen —
        recomendar algo que no cumple lo pedido— con otro disfraz.
        """
        m = _CLASE.search(self.section)
        return m.group().upper() if m else None

    @property
    def frecuencia_hz(self) -> int | None:
        """50 o 60 Hz, DEDUCIDOS de los rpm y los polos de esta fila.

        No se toma del título: la pág. 34 es una tabla de 50 Hz titulada
        "16. Datos Eléctricos", sin la frecuencia por ningún lado, y colarla en una
        recomendación para Colombia es justo el error que el filtro debe impedir.
        Los rpm no mienten: a 4 polos, 60 Hz da ~1750-1800 y 50 Hz ~1450-1500.
        """
        rpm = a_numero(self.valores["rpm"])
        if not rpm or not self.polos:
            return None
        for hz in (50, 60):
            sincrona = 120 * hz / self.polos
            deslizamiento = (sincrona - rpm) / sincrona
            if DESLIZAMIENTO_MIN <= deslizamiento <= DESLIZAMIENTO_MAX:
                return hz
        return None

    def descripcion(self) -> str:
        v = self.valores
        return f"{v['kw']} kW ({v['hp']} HP), {self.polos} polos, carcasa {v['carcasa']}"

    def como_snippet(self) -> str:
        """La fila entera en una línea, con las unidades nombradas.

        Va con unidades porque el guard usa `unidades_mencionadas()` sobre el snippet
        para decidir si un número pelado de tabla puede respaldar una afirmación con
        unidad. Las cifras son LITERALES de la página; lo único agregado son las
        etiquetas de columna, que en el PDF viven en el encabezado y no en la celda.
        """
        v = self.valores
        return (
            f"{self.section} · {self.polos} polos · "
            f"potencia {v['kw']} kW ({v['hp']} HP) · carcasa {v['carcasa']} · "
            f"{v['rpm']} RPM · corriente nominal {v['in_a']} A a {self.tension_v} V · "
            f"rendimiento {v['rend_50']} % a media carga, {v['rend_75']} % a 3/4 y "
            f"{v['rend_100']} % a plena carga · "
            f"factor de potencia {v['fp_50']}, {v['fp_75']}, {v['fp_100']} · "
            f"par nominal {v['par_nominal_kgfm']} kgfm · "
            f"Il/In {v['il_in']} · Tl/Tn {v['tl_tn']} · Tb/Tn {v['tb_tn']} · "
            f"momento de inercia {v['j_kgm2']} kgm2 · "
            f"rotor trabado {v['t_rotor_trabado_caliente_s']} s en caliente y "
            f"{v['t_rotor_trabado_frio_s']} s en frío · "
            f"peso {v['peso_kg']} kg · ruido {v['ruido_db']} dB"
        )

    def como_source(self) -> Source:
        return Source(
            doc=self.doc, section=self.section, page=self.page, snippet=self.como_snippet()
        )

    def como_dict(self) -> dict[str, object]:
        return {
            "doc": self.doc,
            "seccion": self.section,
            "pagina": self.page,
            "polos": self.polos,
            "tension_v": self.tension_v,
            **self.valores,
        }


def _fila_es_coherente(campos: dict[str, str], tension_v: int) -> bool:
    """Las dos pruebas de física que autorizan a creerle al alineamiento de columnas.

    1. HP contra kW: son la misma potencia en dos unidades, tienen que cuadrar.
    2. La potencia contra la corriente: P = √3·V·I·cosφ·η. Si la fila está corrida,
       `in_a` cae en otra columna y esta prueba se dispara. Es la que de verdad
       ancla el final de la fila, que es donde el desfase se acumula.
    """
    kw = a_numero(campos["kw"])
    hp = a_numero(campos["hp"])
    if not kw or not hp or kw <= 0 or hp <= 0:
        return False
    if abs(kw / HP_A_KW - hp) / hp > _HOLGURA_HP:
        return False

    ina = a_numero(campos["in_a"])
    rend = a_numero(campos["rend_100"])
    fp = a_numero(campos["fp_100"])
    if not ina or not rend or not fp:
        return False
    if not (0 < fp <= 1) or not (0 < rend <= 100):
        return False

    electrica_kw = 3**0.5 * tension_v * ina * fp * (rend / 100) / 1000
    return abs(electrica_kw - kw) / kw <= _HOLGURA_ELECTRICA


def parsear_filas(texto: str, doc: str, section: str, page: int | None) -> list[FilaMotor]:
    """Saca las filas de motor de una página de tabla. Lista vacía si no es una.

    El texto llega como lo extrae PyMuPDF: una celda por renglón, recorriendo la
    tabla por columnas. Los grupos de polos vienen marcados ("IV Polos") y dentro
    de cada grupo las filas son 20 renglones consecutivos.

    No se cuentan bloques de 20 a ciegas: se busca un ANCLA (kW, HP y carcasa
    plausibles) y se valida la fila completa con física. Si no valida, se avanza un
    renglón y se reintenta. Así una celda de más o de menos desincroniza una fila,
    no la tabla entera — que es lo que pasaba contando en bloques fijos.
    """
    lineas = [l.strip() for l in texto.splitlines() if l.strip()]
    marcadores = [i for i, l in enumerate(lineas) if _MARCADOR_POLOS.fullmatch(l)]
    if not marcadores:
        return []

    # Sin tensión declarada no se puede correr la prueba eléctrica, y sin esa prueba
    # el alineamiento de columnas no está verificado. Se prefiere no parsear.
    tension = tension_de_la_tabla(lineas)
    if tension is None:
        return []

    filas: list[FilaMotor] = []
    for orden, inicio in enumerate(marcadores):
        polos = _ROMANOS[lineas[inicio].split()[0].upper()]
        fin = marcadores[orden + 1] if orden + 1 < len(marcadores) else len(lineas)

        i = inicio + 1
        while i + len(COLUMNAS) <= fin:
            if not _CARCASA.match(lineas[i + 2]):
                i += 1
                continue
            campos = dict(zip(COLUMNAS, lineas[i : i + len(COLUMNAS)]))
            if _fila_es_coherente(campos, tension):
                filas.append(
                    FilaMotor(
                        doc=doc,
                        section=section,
                        page=page,
                        polos=polos,
                        tension_v=tension,
                        valores=campos,
                    )
                )
                i += len(COLUMNAS)
            else:
                i += 1
    return filas


def seleccionar(
    filas: list[FilaMotor],
    *,
    potencia_hp: float | None = None,
    polos: int | None = None,
    carcasa: str | None = None,
    clase_eficiencia: str | None = None,
    frecuencia_hz: int | None = None,
    tolerancia_potencia: float = 0.03,
) -> tuple[list[FilaMotor], list[str]]:
    """Filtra las filas por los criterios pedidos. Devuelve (las que cumplen, qué se exigió).

    Determinista y sin modelo: elegir la fila ES el cálculo, y el cálculo no se le
    pregunta al modelo. Antes de esto el modelo leía la tabla y elegía él, y nada
    comprobaba que lo elegido cumpliera lo pedido.
    """
    exigido: list[str] = []
    candidatas = list(filas)

    # La frecuencia y la clase van PRIMERO y descartan la fila que no las declara.
    # Una fila que no puede probar que es 60 Hz o que es IE3 no sirve para sostener
    # una recomendación que dice serlo.
    if frecuencia_hz is not None:
        exigido.append(f"{frecuencia_hz} Hz")
        candidatas = [f for f in candidatas if f.frecuencia_hz == frecuencia_hz]

    if clase_eficiencia:
        objetivo_clase = clase_eficiencia.strip().upper()
        exigido.append(objetivo_clase)
        candidatas = [f for f in candidatas if f.clase_eficiencia == objetivo_clase]

    if polos is not None:
        exigido.append(f"{polos} polos")
        candidatas = [f for f in candidatas if f.polos == polos]

    if potencia_hp is not None:
        exigido.append(f"{potencia_hp:g} HP")
        candidatas = [
            f
            for f in candidatas
            if f.hp and abs(f.hp - potencia_hp) / potencia_hp <= tolerancia_potencia
        ]

    if carcasa:
        exigido.append(f"carcasa {carcasa}")
        objetivo = carcasa.strip().upper()
        candidatas = [f for f in candidatas if f.carcasa.upper() == objetivo]

    return candidatas, exigido


def filas_del_corpus(corpus) -> list[FilaMotor]:
    """Todas las filas de motor del corpus, parseadas una sola vez.

    La búsqueda léxica solo sirve para decidir qué páginas leer, y cuando NADA
    cumple hay que poder mirar el catálogo entero — la alternativa suele estar en
    una tabla que la consulta ni rozó (se pide IE3 y la opción vive en IE2).
    Parsear las 72 páginas cuesta ~37 ms, así que el caché es por comodidad, no
    por necesidad: se guarda en el corpus, que se construye una vez al arrancar.
    """
    cache = getattr(corpus, "_filas_de_tabla", None)
    if cache is None:
        cache = [
            fila
            for frag in corpus.fragmentos
            for fila in parsear_filas(frag.texto, frag.doc, frag.section, frag.page)
        ]
        corpus._filas_de_tabla = cache
    return cache


# Cuántas filas se entregan COMO MÁXIMO en un turno por la vía genérica, sumando
# todas las páginas. El tope es global a propósito: uno por página no sirve de nada
# porque el guard une la evidencia de todas las fuentes — medido, 5 páginas × 3 filas
# devolvían 980 dígitos y la mezcla de motores volvía a validar.
TOPE_FILAS = 3


def filas_puntuadas(
    texto: str, doc: str, section: str, page: int | None, consulta: str
) -> list[tuple[int, FilaMotor]]:
    """Las filas de esta página que la consulta realmente menciona, con su puntaje.

    El puntaje se devuelve para que el llamador pueda ordenar y cortar SUMANDO
    TODAS LAS PÁGINAS. Cortar por página deja pasar demasiadas filas juntas.

    Existe para tapar el desvío por las herramientas genéricas: `buscar_conocimiento`
    y `leer_documento` devolvían la PÁGINA de la tabla como snippet, así que el
    modelo podía esquivar `buscar_motor_equivalente` y recuperar el pozo de 1.712
    números — el falso positivo original, alcanzable por otro camino. Visto en vivo
    el 28-jul-2026: `32/32 verificado` con evidencia de página.

    **El tope no es cosmético: es el arreglo.** El guard une la evidencia de TODAS
    las fuentes del turno, así que devolver la tabla partida en 48 filas dejaría el
    pozo igual de grande. Se entregan pocas filas o ninguna.
    """
    filas = parsear_filas(texto, doc, section, page)
    if not filas:
        return []

    numeros = [n for n in (a_numero(t) for t in consulta.replace(",", ", ").split()) if n]
    texto_consulta = consulta.lower()

    def puntaje(fila: FilaMotor) -> int:
        golpes = 0
        for campo in ("kw", "hp", "rpm"):
            valor = a_numero(fila.valores[campo])
            if valor and any(abs(valor - n) <= abs(valor) * 0.01 for n in numeros):
                golpes += 1
        if fila.carcasa.lower() in texto_consulta:
            golpes += 1
        if f"{fila.polos} polo" in texto_consulta:
            golpes += 1
        # La frecuencia desempata, y el empate era real: la misma potencia y los
        # mismos polos existen en la tabla de 50 Hz y en la de 60 Hz, así que sin
        # esto una fila europea podía ganarle a la del país por orden de llegada.
        if fila.frecuencia_hz and f"{fila.frecuencia_hz} hz" in texto_consulta:
            golpes += 1
        return golpes

    return [(p, f) for p, f in ((puntaje(f), f) for f in filas) if p > 0]


AVISO_TABLA = (
    "esta página es una tabla de datos eléctricos con decenas de motores y no te la "
    "entrego entera: sus cifras pertenecen a filas distintas y atribuírselas a un "
    "motor sería inventar. Para elegir o citar un motor usa `buscar_motor_equivalente`, "
    "que devuelve la fila del motor que cumple los criterios."
)


def alternativas(
    filas: list[FilaMotor],
    *,
    potencia_hp: float | None = None,
    polos: int | None = None,
    carcasa: str | None = None,
    clase_eficiencia: str | None = None,
    frecuencia_hz: int | None = None,
    maximo: int = 3,
) -> list[tuple[str, str, list[FilaMotor]]]:
    """Qué aparece en el resto del catálogo si se suelta UNA sola restricción.

    Devuelve tuplas `(criterio, qué cambiaría, filas)`. Sirve para no dejar al
    usuario en un "no existe" sin salida: se le muestra qué tendría que ceder y se
    le pregunta, en vez de elegir por él.

    **La frecuencia NUNCA se relaja.** Un motor de 50 Hz no le sirve a ninguna placa
    colombiana: ofrecerlo como alternativa no es flexibilidad, es el error que el
    filtro duro de `_buscar_motor` existe para impedir. Se suelta la clase, los
    polos, la potencia o la carcasa — nunca la red eléctrica del país.
    """
    fijos = {"clase_eficiencia": clase_eficiencia, "frecuencia_hz": frecuencia_hz}
    pedidos = {"potencia_hp": potencia_hp, "polos": polos, "carcasa": carcasa}
    etiquetas = {
        "clase_eficiencia": "clase de eficiencia",
        "polos": "número de polos",
        "potencia_hp": "potencia",
        "carcasa": "carcasa",
    }

    salida: list[tuple[str, str, list[FilaMotor]]] = []
    relajables = [k for k, v in {**fijos, **pedidos}.items() if v and k != "frecuencia_hz"]

    for suelto in relajables:
        criterios = {**fijos, **pedidos, suelto: None}
        encontradas, _ = seleccionar(filas, **criterios)
        if not encontradas:
            continue

        # Al soltar la potencia quedan cientos de filas: se ordenan por cercanía,
        # que es lo que un ingeniero mira (el escalón de arriba y el de abajo).
        if suelto == "potencia_hp" and potencia_hp:
            encontradas = sorted(encontradas, key=lambda f: abs((f.hp or 0) - potencia_hp))

        elegidas = encontradas[:maximo]
        # Se deduplica CONSERVANDO el orden, que ya viene cargado de sentido: por
        # cercanía cuando se soltó la potencia, y por orden de catálogo (de más a
        # menos eficiente) cuando se soltó la clase. Un `sorted()` alfabético lo
        # rompía y mostraba "10 HP, 15 HP, 7,5 HP".
        vistas: list[str] = []
        for fila in elegidas:
            visible = _valor_visible(fila, suelto)
            if visible not in vistas:
                vistas.append(visible)
        salida.append((etiquetas[suelto], ", ".join(vistas), elegidas))

    return salida


def _valor_visible(fila: FilaMotor, criterio: str) -> str:
    """Cómo se nombra, para el usuario, el valor que tomaría el criterio relajado."""
    if criterio == "clase_eficiencia":
        return fila.clase_eficiencia or "sin clase declarada"
    if criterio == "polos":
        return f"{fila.polos} polos"
    if criterio == "potencia_hp":
        return f"{fila.valores['hp']} HP"
    return f"carcasa {fila.carcasa}"


def mas_cercana(filas: list[FilaMotor], potencia_hp: float, polos: int | None) -> FilaMotor | None:
    """La fila más próxima en potencia, para poder decir "no hay X, lo más cerca es Y".

    Sin esto, "no cumple" es un callejón sin salida. Con esto el agente puede ofrecer
    el escalón real del catálogo, que es lo que haría un ingeniero.
    """
    pool = [f for f in filas if polos is None or f.polos == polos]
    pool = [f for f in pool if f.hp]
    if not pool:
        return None
    return min(pool, key=lambda f: abs(f.hp - potencia_hp))
