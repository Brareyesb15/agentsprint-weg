"""El agujero por el que una recomendación absurda salía con el sello "verificado".

Medido el 28-jul-2026 sobre el catálogo real: el guard recibía como evidencia la
PÁGINA entera de la tabla (1.712 números) en vez de la fila del motor, así que
confirmaba cualquier cifra que existiera en cualquier fila. Una respuesta que
juntaba "10 HP" con la corriente, el rendimiento y el peso del motor de 0,12 kW
—el más chico del catálogo— daba `ok=True, 6/6 confirmados`.

El primer test de este archivo es ese caso exacto. Si vuelve a pasar, volvió el bug.

La tabla de abajo es un recorte LITERAL de la pág. 50 del brochure W22 (dos filas
de 4 polos con su encabezado). Se usa un recorte y no el PDF de 29 MB para que la
suite siga corriendo en segundos, pero las cifras no están inventadas: son las que
trae el catálogo, y la prueba eléctrica del parser las valida.
"""

from agent.dominio import BuscarMotorArgs, _buscar_motor
from agent.guardrails import verificar
from agent.tablas import parsear_filas, seleccionar

# Encabezado + dos filas de "IV Polos", tal como PyMuPDF extrae la tabla:
# una celda por renglón, recorriendo por columnas.
PAGINA = "\n".join(
    [
        "www.weg.net",
        "Motor Eléctrico Trifásico - W22",
        "50",
        "W22 - IE3 Premium Efficiency - 60 Hz",
        "Potencia",
        "Carcasa",
        "380 V",
        "RPM",
        "Rendimiento",
        "Factor de potencia",
        "kW",
        "HP",
        "IV Polos",
        # 7,5 kW / 10 HP / 132S
        "7,5", "10", "132S", "4,14", "8,2", "2,3", "3,5", "0,0563", "13", "29",
        "72,0", "58", "1765", "90,8", "91,6", "92,0", "0,66", "0,78", "0,84", "14,7",
        # 18,5 kW / 25 HP / 160L
        "18,5", "25", "160L", "10,2", "7,8", "2,4", "3,0", "0,1710", "11", "24",
        "148,0", "62", "1775", "92,4", "93,0", "93,0", "0,72", "0,82", "0,86", "35,4",
    ]
)


def _filas():
    return parsear_filas(PAGINA, "brochure.pdf", "W22 - IE3 Premium Efficiency - 60 Hz", 50)


# --- el bug original --------------------------------------------------------


def test_cifras_de_otro_motor_ya_no_se_confirman():
    """EL test de este archivo. Antes: ok=True 6/6. La fila ata cada número a SU motor."""
    fila = next(f for f in _filas() if f.hp == 10)

    mezcla = (
        "Recomiendo el W22 IE3 de 10 HP, 4 polos, con corriente nominal de 35,4 A, "
        "rendimiento de 93,0 % y peso de 148,0 kg."
    )  # 35,4 A · 93,0 % · 148,0 kg son del motor de 25 HP, no del de 10 HP

    res = verificar(mezcla, [fila.como_source()], hubo_consulta=True)
    assert res.ok is False, f"el guard volvió a tragarse la mezcla de filas: {res.detail}"


def test_la_respuesta_correcta_de_esa_fila_sigue_pasando():
    """El arreglo no sirve si además bloquea lo correcto: eso sería cambiar un falso
    positivo por un falso negativo, que en vivo es igual de malo."""
    fila = next(f for f in _filas() if f.hp == 10)

    buena = (
        "El W22 IE3 de 10 HP (7,5 kW), 4 polos, carcasa 132S, gira a 1765 RPM con "
        "corriente nominal de 14,7 A y rendimiento de 92,0 % a plena carga. Pesa 72,0 kg."
    )

    res = verificar(buena, [fila.como_source()], hubo_consulta=True)
    assert res.ok is True, res.detail
    assert res.confirmed == res.checked


# --- el parser --------------------------------------------------------------


def test_parsea_las_filas_con_sus_valores_atados():
    filas = _filas()
    assert len(filas) == 2

    diez = next(f for f in filas if f.hp == 10)
    assert diez.valores["kw"] == "7,5"
    assert diez.carcasa == "132S"
    assert diez.valores["in_a"] == "14,7"
    assert diez.valores["peso_kg"] == "72,0"
    assert diez.polos == 4
    assert diez.tension_v == 380


def test_la_frecuencia_sale_de_los_rpm_no_del_titulo():
    """La pág. 34 del catálogo real es una tabla de 50 Hz titulada "16. Datos
    Eléctricos": el título no la delata, los rpm sí."""
    for fila in _filas():
        assert fila.frecuencia_hz == 60  # 1765 y 1775 rpm a 4 polos

    a_50_hz = PAGINA.replace("1765", "1465").replace("1775", "1475")
    filas = parsear_filas(a_50_hz, "brochure.pdf", "16. Datos Eléctricos", 34)
    assert [f.frecuencia_hz for f in filas] == [50, 50]


def test_las_carcasas_con_barra_tambien_se_parsean():
    """`225S/M`, `132M/L`, `355M/L`: las carcasas grandes se publican como un par.

    Un ancla que no las reconociera descartaba el 42% del catálogo en silencio (836
    filas de 1.432) y hacía que la herramienta dijera "no existe" sobre motores
    reales — p.ej. el 60 HP / 4 polos IE3, carcasa 225S/M de la pág. 50.
    """
    con_barra = PAGINA.replace("160L", "225S/M")
    filas = parsear_filas(con_barra, "brochure.pdf", "seccion", 50)
    assert [f.carcasa for f in filas] == ["132S", "225S/M"]


def test_sin_tension_declarada_no_se_parsea():
    """Sin la tensión no se puede correr P = √3·V·I·cosφ·η, y sin esa prueba el
    alineamiento de columnas no está verificado. Falla cerrado."""
    sin_tension = PAGINA.replace("380 V", "Tensión")
    assert parsear_filas(sin_tension, "brochure.pdf", "seccion", 50) == []


def test_una_celda_corrida_no_desincroniza_toda_la_tabla():
    """Contando bloques fijos de 20, una celda de más arrastraba el error hasta el
    final de la página. El ancla + la prueba eléctrica resincronizan."""
    con_basura = PAGINA.replace("IV Polos\n", "IV Polos\n(*)\n")
    filas = parsear_filas(con_basura, "brochure.pdf", "seccion", 50)
    # El ancla salta la celda intrusa y encuentra el arranque real, así que no se
    # pierde ninguna fila: la resincronización es por fila, no por página.
    assert [f.hp for f in filas] == [10, 25]


# --- la comprobación de lo que se pidió -------------------------------------


def test_no_ofrece_otra_clase_de_eficiencia():
    """Pedir IE3 y recibir un IE2 es el mismo defecto de origen con otro disfraz."""
    filas = _filas()
    candidatas, exigido = seleccionar(filas, clase_eficiencia="IE2")
    assert candidatas == []
    assert "IE2" in exigido

    candidatas, _ = seleccionar(filas, clase_eficiencia="IE3")
    assert len(candidatas) == 2


def test_no_ofrece_otra_frecuencia():
    filas = _filas()
    assert seleccionar(filas, frecuencia_hz=50)[0] == []
    assert len(seleccionar(filas, frecuencia_hz=60)[0]) == 2


def test_lo_pedido_queda_registrado_en_el_resultado():
    """`solicitado` es lo que hacía falta para poder comparar entrada contra salida:
    antes la herramienta no devolvía en ninguna parte qué se le había pedido."""
    filas = _filas()
    _, exigido = seleccionar(filas, potencia_hp=10, polos=4, clase_eficiencia="IE3")
    assert exigido == ["IE3", "4 polos", "10 HP"]


class _Frag:
    def __init__(self, texto, section, page):
        self.doc, self.section, self.page, self.texto = "brochure.pdf", section, page, texto

    def como_source(self, snippet=None):
        from agent.sources import Source

        return Source(self.doc, self.section, self.page, snippet or self.texto)


class _CorpusDeUnaPagina:
    """Lo mínimo que `_buscar_motor` consume del corpus.

    `fragmentos` es lo que recorre `filas_del_corpus` para poder ofrecer
    alternativas de OTRAS tablas cuando nada cumple.
    """

    def __init__(self, *paginas):
        self.fragmentos = list(paginas) or [
            _Frag(PAGINA, "W22 - IE3 Premium Efficiency - 60 Hz", 50)
        ]

    def buscar(self, consulta, k=14):
        return [(self.fragmentos[0], 1.0)]

    def leer(self, doc, section=None):
        return [f for f in self.fragmentos if section in (None, f.section)]

    def lineas_relevantes(self, frag, consulta, maximo=3):
        return frag.texto


# La MISMA tabla declarada IE1. Solo cambia el título: las cifras se dejan intactas
# a propósito, porque si se tocaran ya no pasarían la prueba eléctrica del parser y
# el test estaría comprobando datos inventados en vez del comportamiento real.
SECCION_IE1 = "W22 - IE1 Standard Efficiency - 60 Hz"
PAGINA_IE1 = PAGINA.replace("W22 - IE3 Premium Efficiency - 60 Hz", SECCION_IE1)


def test_lo_que_no_esta_en_el_catalogo_se_declara_como_tal():
    """12 HP no existe en la tabla. Antes se ofrecía el vecino como si cumpliera."""
    salida = _buscar_motor(
        BuscarMotorArgs(potencia_hp=12, polos=4, clase_eficiencia="IE3"),
        _CorpusDeUnaPagina(),
    )
    assert salida.result["cumple"] is False
    assert "NINGÚN motor" in salida.uncertainty
    # Los vecinos se ofrecen como ALTERNATIVA declarada, nunca como si cumplieran.
    caminos = {c["si_cambias"]: c["a"] for c in salida.result["alternativas"]}
    assert caminos["potencia"].startswith("10 HP")  # el más cercano primero


# --- cuando nada cumple, se recorre el resto del catálogo --------------------


def test_busca_en_las_otras_tablas_y_pregunta_cual_restriccion_cede():
    """Pedir 25 HP en IE2 no da nada, pero 25 HP sí existe en IE3 y en IE1.

    Antes el camino terminaba en "no existe" (o peor, en el vecino de potencia).
    Ahora se recorren las demás tablas y se le devuelve la decisión al usuario.
    """
    corpus = _CorpusDeUnaPagina(
        _Frag(PAGINA, "W22 - IE3 Premium Efficiency - 60 Hz", 50),
        _Frag(PAGINA_IE1, SECCION_IE1, 57),
    )
    salida = _buscar_motor(
        BuscarMotorArgs(potencia_hp=25, polos=4, clase_eficiencia="IE2"), corpus
    )

    assert salida.result["cumple"] is False
    caminos = {c["si_cambias"]: c["a"] for c in salida.result["alternativas"]}
    assert "clase de eficiencia" in caminos
    assert "IE3" in caminos["clase de eficiencia"]
    assert "IE1" in caminos["clase de eficiencia"]
    assert "PREGÚNTALE" in salida.uncertainty
    # Cada alternativa se cita con su fila, no con la página.
    assert salida.sources and all("potencia" in s.snippet for s in salida.sources)


def test_la_frecuencia_no_se_ofrece_como_alternativa():
    """Relajar la clase o los polos es ayudar; relajar la frecuencia es recomendar
    un motor de 50 Hz para una red de 60 Hz. Esa restricción no se toca nunca."""
    a_50_hz = PAGINA.replace("1765", "1465").replace("1775", "1475")
    corpus = _CorpusDeUnaPagina(_Frag(a_50_hz, "W22 - IE3 Premium Efficiency - 50 Hz", 36))

    salida = _buscar_motor(
        BuscarMotorArgs(potencia_hp=25, polos=4, clase_eficiencia="IE3"), corpus
    )
    assert salida.result["cumple"] is False
    assert salida.result["alternativas"] == []
    assert "no está en el catálogo" in salida.uncertainty


def test_lo_que_si_esta_se_devuelve_con_su_fila():
    salida = _buscar_motor(
        BuscarMotorArgs(potencia_hp=25, polos=4, clase_eficiencia="IE3"),
        _CorpusDeUnaPagina(),
    )
    assert salida.result["cumple"] is True
    assert [m["hp"] for m in salida.result["motores"]] == ["25"]
    assert salida.uncertainty is None
    # La evidencia es la fila, no la página: ese es todo el arreglo.
    assert "148,0 kg" in salida.sources[0].snippet
    assert "72,0" not in salida.sources[0].snippet


# --- el desvío por las herramientas genéricas -------------------------------
# `buscar_motor_equivalente` quedó atado a la fila, pero el modelo podía esquivarlo
# llamando a `buscar_conocimiento` / `leer_documento`, que devolvían la PÁGINA y con
# ella el pozo de 1.712 números. Visto en vivo el 28-jul-2026: `32/32 verificado`
# con evidencia de página. Estos tests cierran esa puerta.


def _registro_de_una_pagina():
    from agent.tools import construir_registro

    return construir_registro(_CorpusDeUnaPagina())


def test_buscar_conocimiento_no_entrega_la_tabla_entera():
    from agent.tools import BuscarArgs

    salida = _registro_de_una_pagina().obtener("buscar_conocimiento").fn(
        BuscarArgs(consulta="motor de 10 HP 4 polos", k=5)
    )
    # Sale la fila pedida, no la página: la de 25 HP no viaja como evidencia.
    assert salida.sources
    assert all("10 HP" in s.snippet for s in salida.sources)
    assert "tabla de datos eléctricos" in salida.uncertainty


def test_leer_documento_no_vuelca_una_tabla():
    from agent.tools import LeerArgs

    salida = _registro_de_una_pagina().obtener("leer_documento").fn(
        LeerArgs(doc="brochure.pdf", section="W22 - IE3 Premium Efficiency - 60 Hz")
    )
    assert salida.sources == [], "volcó la tabla entera como evidencia"
    assert "buscar_motor_equivalente" in salida.uncertainty


def test_el_tope_de_filas_es_global_no_por_pagina():
    """Con el tope por página, 5 páginas devolvían 15 filas y el pozo seguía siendo
    enorme: 980 dígitos. El guard une la evidencia de TODAS las fuentes."""
    from agent.tools import BuscarArgs

    corpus = _CorpusDeUnaPagina(
        _Frag(PAGINA, "W22 - IE3 Premium Efficiency - 60 Hz", 50),
        _Frag(PAGINA_IE1, SECCION_IE1, 57),
    )
    corpus.buscar = lambda consulta, k=14: [(f, 1.0) for f in corpus.fragmentos]

    from agent.tools import construir_registro

    salida = construir_registro(corpus).obtener("buscar_conocimiento").fn(
        BuscarArgs(consulta="10 HP 25 HP 4 polos 7,5 kW 18,5 kW", k=5)
    )
    from agent.tablas import TOPE_FILAS

    assert len(salida.sources) <= TOPE_FILAS
