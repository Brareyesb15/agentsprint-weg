"""Regresión del bug más peligroso que apareció en la prueba en vivo.

El modelo escribe "**24 V DC**" con negritas de markdown. Antes del fix, el
tokenizador no reconocía "**24" como número, el guard no encontraba NINGUNA
afirmación y emitía `verify ok=True · "la respuesta no afirma ningún valor
numérico"` sobre una respuesta que afirmaba dos valores.

O sea: el guard daba luz verde a todo lo que viniera en negrita. Era decorativo.
Si estos tests se ponen rojos, el guard volvió a ser decorativo.
"""

import pytest

from agent.guardrails import verificar
from agent.sources import extraer_cantidades
from agent.sources import Source

FUENTE = Source(
    doc="ficha_ZX-100.md",
    section="Sección 1 — Datos eléctricos",
    page=1,
    snippet="Tensión de alimentación: 24 V DC. Consumo máximo: 35 mA.",
)


@pytest.mark.parametrize(
    "texto",
    [
        "Se alimenta con **24 V** DC.",
        "Se alimenta con *24 V* DC.",
        "Se alimenta con `24 V` DC.",
        "Se alimenta con __24 V__ DC.",
        "Se alimenta con ~~24 V~~ DC.",
        "| Tensión | 24 V |",
        "Tensión = 24 V",
    ],
)
def test_el_marcado_no_esconde_los_numeros(texto):
    cantidades = extraer_cantidades(texto)
    assert any(c.valor == 24.0 for c in cantidades), f"no vio el 24 en: {texto!r}"


def test_respuesta_en_markdown_se_verifica_de_verdad():
    respuesta = (
        "El sensor ZX-100 se alimenta con una tensión de **24 V DC** y tiene un "
        "consumo máximo de **35 mA**.\n\n**Fuente:** `ficha_ZX-100.md`, Sección 1."
    )
    res = verificar(respuesta, [FUENTE])
    assert res.checked == 2, f"el guard debe VER las dos cifras, vio {res.checked}"
    assert res.confirmed == 2
    assert res.ok is True


def test_markdown_con_valor_falso_si_se_bloquea():
    """El caso que importa: negrita + número inventado. Antes pasaba."""
    respuesta = "El sensor se alimenta con **30 V DC**."
    res = verificar(respuesta, [FUENTE])
    assert res.checked == 1
    assert res.ok is False
    assert "30 v" in res.detail


def test_el_nombre_del_documento_citado_no_se_avisa_como_referencia_suelta():
    """La respuesta nombra su propia fuente: eso es citar bien, no una afirmación."""
    respuesta = "Se alimenta con **24 V**, según `ficha_ZX-100.md`, Sección 1."
    res = verificar(respuesta, [FUENTE])
    assert res.ok is True
    assert res.codigos_sin_respaldo == []
    assert "aviso" not in res.detail


def test_respaldos_solo_lista_las_fuentes_que_sirvieron():
    otra = Source(
        doc="ficha_ZX-200.md",
        section="Sección 1 — Datos eléctricos",
        page=1,
        snippet="Distancia de detección nominal: 20 mm.",
    )
    res = verificar("Se alimenta con **24 V**.", [FUENTE, otra])
    assert res.ok is True
    assert res.respaldos == [FUENTE.etiqueta()]
    assert otra.etiqueta() not in res.respaldos
