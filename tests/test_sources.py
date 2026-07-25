"""Tests de la normalización. Si esto se rompe, el guard miente."""

import pytest

from agent.sources import (
    Cantidad,
    canonizar,
    coincide,
    extraer_cantidades,
    extraer_codigos,
    normalizar_numero,
)


@pytest.mark.parametrize(
    "texto, esperado",
    [
        ("24", 24.0),
        ("3,7", 3.7),          # coma decimal, español
        ("3.7", 3.7),          # punto decimal, inglés
        ("1.500", 1500.0),     # punto de miles: grupo de 3 exacto
        ("1,500", 1500.0),     # coma de miles: grupo de 3 exacto
        ("1.234.567", 1234567.0),
        ("1.234,56", 1234.56),  # ambos: el último manda
        ("1,234.56", 1234.56),
        ("0,085", 0.085),
        ("-25", -25.0),
        ("no soy un número", None),
        ("", None),
    ],
)
def test_normalizar_numero(texto, esperado):
    assert normalizar_numero(texto) == esperado


def test_canonizar_potencia():
    assert canonizar(3.7, "kw") == (3700.0, "potencia")
    valor, familia = canonizar(5, "hp")
    assert familia == "potencia"
    assert round(valor) == 3728


def test_extraer_ignora_codigos_de_producto():
    """Un regex de números partiría IME18-12NNSZC0S en 18 y 12. El tokenizador no."""
    cantidades = extraer_cantidades("La referencia IME18-12NNSZC0S y el grado IP67.")
    assert cantidades == []


def test_extraer_ignora_referencias_al_documento():
    cantidades = extraer_cantidades("Ver página 2, tabla 4 y sección 3.")
    assert cantidades == []


def test_extraer_unidad_pegada_y_separada():
    cantidades = extraer_cantidades("Alimentación 24V y consumo de 35 mA.")
    textos = [c.texto for c in cantidades]
    assert "24 v" in textos
    assert "35 ma" in textos


def test_la_preposicion_a_no_es_amperios():
    """Trampa del español: 'de 3 a 5 metros' no son 3 amperios."""
    cantidades = extraer_cantidades("El rango va de 3 a 5 metros.")
    tres = [c for c in cantidades if c.valor == 3.0][0]
    assert tres.unidad is None
    assert tres.familia is None


def test_amperios_en_mayuscula_si_se_aceptan():
    cantidades = extraer_cantidades("Consumo de 35 A en régimen continuo.")
    treinta_y_cinco = [c for c in cantidades if c.valor == 35.0][0]
    assert treinta_y_cinco.familia == "corriente"


def test_temperatura_negativa_con_grados():
    cantidades = extraer_cantidades("Rango de -25 °C a 70 °C.")
    valores = {c.valor for c in cantidades}
    assert -25.0 in valores and 70.0 in valores


def test_coincide_exacto():
    a = Cantidad("24 v", 24.0, "v", 24.0, "tension")
    b = Cantidad("24 v", 24.0, "v", 24.0, "tension")
    assert coincide(a, b, 0.02) == "exacto"


def test_coincide_equivalente_entre_unidades():
    """El caso que motiva todo el módulo: 5 HP y 3,7 kW son el mismo motor."""
    dicho = Cantidad("5 hp", 5.0, "hp", 3728.499, "potencia")
    fuente = Cantidad("3,7 kw", 3.7, "kw", 3700.0, "potencia")
    assert coincide(dicho, fuente, 0.02) == "equivalente"


def test_no_coincide_valor_distinto():
    a = Cantidad("30 v", 30.0, "v", 30.0, "tension")
    b = Cantidad("24 v", 24.0, "v", 24.0, "tension")
    assert coincide(a, b, 0.02) is None


def test_extraer_codigos():
    codigos = extraer_codigos("El ZX-100 tiene grado IP67 y pesa 0,085 kg.")
    assert "ZX-100" in codigos
    assert "IP67" in codigos
