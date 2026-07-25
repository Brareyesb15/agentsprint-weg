"""Tests del guard de citas.

El criterio de "listo" del documento de preparación es literal:
"funciona sobre un corpus de juguete (dos archivos inventados) y bloquea
correctamente un número que no está en la fuente".
"""

from pathlib import Path

import pytest

from agent.guardrails import mensaje_degradacion, verificar
from agent.sources import Source

CORPUS = Path(__file__).parent / "fixtures" / "corpus_juguete"


@pytest.fixture
def fuente_zx100() -> Source:
    """Snippet LITERAL del corpus de juguete, como exige el contrato."""
    texto = (CORPUS / "ficha_ZX-100.md").read_text(encoding="utf-8")
    linea = next(l for l in texto.splitlines() if "Tensión de alimentación" in l)
    return Source(
        doc="ficha_ZX-100.md", section="Sección 1 — Datos eléctricos", page=1, snippet=linea
    )


@pytest.fixture
def fuente_potencia() -> Source:
    texto = (CORPUS / "ficha_ZX-100.md").read_text(encoding="utf-8")
    linea = next(l for l in texto.splitlines() if "actuador recomendado" in l)
    return Source(
        doc="ficha_ZX-100.md", section="Sección 3", page=2, snippet=linea
    )


# --- el caso que tiene que pasar -------------------------------------------


def test_pasa_cuando_el_numero_esta_en_la_fuente(fuente_zx100):
    res = verificar("El ZX-100 se alimenta con 24 V DC.", [fuente_zx100])
    assert res.ok is True
    assert res.checked == 1
    assert res.confirmed == 1
    assert "1/1 valores confirmados" in res.detail


# --- el caso que tiene que BLOQUEAR (criterio de aceptación) ---------------


def test_bloquea_numero_que_no_esta_en_la_fuente(fuente_zx100):
    res = verificar("El ZX-100 se alimenta con 30 V DC.", [fuente_zx100])
    assert res.ok is False
    assert res.confirmed == 0
    assert "SIN RESPALDO" in res.detail
    assert "30 v" in res.detail
    assert "30 v" in mensaje_degradacion(res)


def test_bloquea_cuando_no_hubo_consulta_al_conocimiento():
    """Gemini Flash a veces responde de memoria sin llamar herramientas.
    Basta una respuesta así frente al juez para perder el hito de grounding."""
    res = verificar("El ZX-100 se alimenta con 24 V.", [], hubo_consulta=False)
    assert res.ok is False
    assert "sin consultar el conocimiento" in res.detail
    assert "no alcancé a consultar" in mensaje_degradacion(res)


def test_bloquea_uno_de_varios(fuente_zx100):
    res = verificar(
        "Se alimenta con 24 V y consume 999 mA.", [fuente_zx100]
    )
    assert res.ok is False
    assert res.checked == 2
    assert res.confirmed == 1
    assert "999 ma" in res.detail


# --- equivalencia de unidades ---------------------------------------------


def test_acepta_equivalencia_entre_unidades(fuente_potencia):
    """La fuente dice 3,7 kW; la respuesta dice 5 HP. Es el mismo actuador."""
    res = verificar("El actuador compatible es de 5 HP.", [fuente_potencia])
    assert res.ok is True
    assert "equivalencia" in res.detail


# --- números calculados ---------------------------------------------------


def test_acepta_numero_venido_de_calculo_determinista(fuente_zx100):
    """Un payback calculado en Python no aparece en ninguna hoja de datos.
    Si el guard lo bloqueara, bloquearía justo el número MÁS confiable."""
    res = verificar(
        "Se alimenta con 24 V y el retorno es de 14 meses.",
        [fuente_zx100],
        resultados_calculo=[{"payback_meses": 14}],
    )
    assert res.ok is True
    assert res.confirmed == 2


# --- códigos: aviso, no bloqueo ------------------------------------------


def test_codigo_contradictorio_se_ve_pero_no_bloquea_por_defecto(fuente_zx100):
    """La fuente es del ZX-100 y la respuesta dice ZX-999: es una contradicción, no
    un typo, y el panel la muestra. Pero por defecto NO tumba la respuesta: en vivo,
    bloquear de más es peor que avisar de más."""
    res = verificar("El ZX-999 se alimenta con 24 V.", [fuente_zx100])
    assert res.ok is True
    assert res.codigos_contradichos == ["ZX-999"]
    assert "CONTRADICE LA FUENTE: ZX-999" in res.detail


def test_modo_estricto_si_bloquea_el_codigo_contradictorio(fuente_zx100):
    """Una palabra de diferencia, por si el equipo prefiere el modo severo en la demo."""
    res = verificar(
        "El ZX-999 se alimenta con 24 V.", [fuente_zx100], codigos_bloquean=True
    )
    assert res.ok is False


def test_codigo_de_otra_familia_solo_avisa(fuente_zx100):
    """Si el prefijo no aparece en ninguna parte, puede venir de la pregunta: aviso."""
    res = verificar("El AB-500 se alimenta con 24 V.", [fuente_zx100])
    assert res.ok is True
    assert res.codigos_contradichos == []
    assert "aviso" in res.detail


# --- respuestas sin afirmaciones -----------------------------------------


def test_respuesta_sin_numeros_pasa(fuente_zx100):
    res = verificar("No tengo esa información en la documentación.", [fuente_zx100])
    assert res.ok is True
    assert res.checked == 0
    assert "no afirma ningún valor" in res.detail


def test_turno_conversacional_no_exige_consulta():
    res = verificar("Hola, ¿en qué te ayudo?", [], hubo_consulta=False, exigir_consulta=False)
    assert res.ok is True


# --- forma del evento ----------------------------------------------------


def test_to_event_data_respeta_el_contrato(fuente_zx100):
    res = verificar("Se alimenta con 24 V.", [fuente_zx100])
    data = res.to_event_data()
    assert set(data.keys()) == {"ok", "checked", "confirmed", "detail"}
    assert isinstance(data["checked"], int)
    assert isinstance(data["confirmed"], int)
    assert isinstance(data["detail"], str)
