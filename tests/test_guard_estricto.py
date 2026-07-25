"""Los agujeros del guard que la auditoría encontró y que se cerraron de madrugada.

Cada test reproduce un FALSO NEGATIVO real: el guard daba verde a una cifra que no
estaba en la fuente. Son los que convertían el hito de grounding en decorado.
"""

from agent.guardrails import verificar
from agent.sources import extraer_cantidades
from agent.sources import Source

FUENTE = Source(
    doc="ficha.md",
    section="Datos",
    page=1,
    snippet="El actuador recomendado es de 3,7 kW. Vida útil: 100 000 ciclos. Peso: 0,085 kg.",
)


# --- respuesta vacía --------------------------------------------------------


def test_respuesta_vacia_se_bloquea():
    """Pasa de verdad: el modelo devuelve solo partes de pensamiento, o corta por
    SAFETY / MAX_TOKENS. Antes salía check verde y un token con texto vacío."""
    for vacia in ["", "   ", "\n\n", "Claro."]:
        res = verificar(vacia, [FUENTE])
        assert res.ok is False, f"no bloqueó: {vacia!r}"
        assert "no produjo una respuesta" in res.detail


# --- tolerancia mal aplicada -----------------------------------------------


def test_la_tolerancia_no_aplica_con_la_misma_unidad():
    """La fuente dice 3,7 kW. "3,77 kW" está a 1,9%: entraba en la tolerancia y se
    reportaba como "confirmado por conversión de unidades". No hay conversión: es
    otro número."""
    res = verificar("El actuador es de 3,77 kW.", [FUENTE])
    assert res.ok is False, res.detail
    assert "3,77 kw" in res.detail.lower()


def test_la_conversion_entre_unidades_distintas_sigue_funcionando():
    """El caso legítimo que motiva la tolerancia: 5 HP y 3,7 kW son el mismo actuador."""
    res = verificar("El actuador es de 5 HP.", [FUENTE])
    assert res.ok is True, res.detail
    assert "equivalencia" in res.detail


# --- número pelado respaldando una afirmación con unidad -------------------


def test_un_numero_sin_unidad_no_respalda_una_afirmacion_con_unidad():
    """"100 000 ciclos" tokeniza como 100 y 000. Ese 0 confirmaba "0 W"."""
    res = verificar("El consumo en reposo es de 0 W.", [FUENTE])
    assert res.ok is False, res.detail


def test_una_afirmacion_sin_unidad_si_se_respalda():
    res = verificar("La vida útil es de 100 000 ciclos de conmutación.", [FUENTE])
    assert res.ok is True, res.detail


def test_el_calculo_determinista_sigue_respaldando_afirmaciones_con_unidad():
    """Excepción acotada: un cálculo devuelve {"potencia_w": 0.84}, sin unidad, y
    tiene que poder respaldar "0,84 W" — es el número MÁS confiable que hay."""
    res = verificar(
        "La potencia disipada es de 0,84 W.",
        [FUENTE],
        resultados_calculo=[{"potencia_w": 0.84}],
    )
    assert res.ok is True, res.detail


# --- unidades de una letra en minúscula ------------------------------------


def test_las_unidades_de_una_letra_en_minuscula_se_reconocen():
    """"85 g", "3 m", "30 s" son legítimas y van en minúscula por convención.
    Exigir mayúscula las dejaba sin familia y bloqueaba respuestas correctas."""
    for texto, valor, familia in [
        ("El sensor pesa 85 g.", 85.0, "masa"),
        ("El cable mide 3 m.", 3.0, "longitud"),
        ("Responde en 30 s.", 30.0, "tiempo"),
    ]:
        c = [x for x in extraer_cantidades(texto) if x.valor == valor][0]
        assert c.familia == familia, f"{texto} -> {c.familia}"


def test_la_conversion_de_masa_ahora_funciona():
    """La fuente dice 0,085 kg; la respuesta dice 85 g. Es el mismo peso."""
    res = verificar("El sensor pesa 85 g.", [FUENTE])
    assert res.ok is True, res.detail


def test_las_palabras_de_una_letra_siguen_sin_ser_unidades():
    for texto in ["Van de 3 a 5 metros.", "Hay 4 o 5 modelos.", "Trae 2 y 3 salidas."]:
        c = extraer_cantidades(texto)[0]
        assert c.familia is None, f"{texto} -> leyó unidad {c.unidad!r}"


# --- el punto decimal de los floats de Python -------------------------------


def test_el_float_de_una_herramienta_no_se_lee_como_millares():
    """`{"potencia_kw": 7.457}` se leía como 7457: el guard se equivocaba por un
    factor de MIL justo en lo que existe para atrapar, y bloqueaba la respuesta
    correcta "7,457 kW". En un documento español "7.457" sí son millares, así que
    la diferencia la hace el origen del número, no su forma."""
    from agent.sources import normalizar_numero

    assert normalizar_numero("7.457") == 7457.0, "en prosa española son millares"
    assert normalizar_numero("7.457", decimal_punto=True) == 7.457


def test_los_datos_de_la_placa_se_confirman():
    """El caso que bloqueaba la demo: el agente repite lo que leyó en la foto y el
    guard no tenía con qué respaldarlo."""
    placa = Source(
        doc="placa del motor (foto del usuario)",
        snippet="10 HP, 4 polos, 1750 rpm, 220 V, 26,2 A, carcasa 132S",
    )
    res = verificar(
        "El motor de la placa es de 7,457 kW (10 HP), 4 polos, 1750 rpm, 220 V y 26,2 A.",
        [placa],
        resultados_calculo=[
            {"potencia_kw": 7.457, "polos": 4, "rpm": 1750.0,
             "tension_v": 220.0, "corriente_a": 26.2}
        ],
    )
    assert res.ok is True, res.detail
    assert res.confirmed == res.checked
