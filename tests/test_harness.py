"""Tests del armazón del eval.

Criterio de "listo" del documento: "corre con un set de 2 preguntas de juguete y
reporta bien/mal". Acá se corre con 4, incluyendo un control negativo.
"""

from evals.agente_simulado import responder_simulado
from evals.harness import cargar_set, correr


def test_el_set_de_juguete_pasa_completo():
    preguntas = cargar_set("juguete")
    corrida = correr(preguntas, responder_simulado, set_nombre="juguete")
    assert corrida.total == 4
    assert corrida.aprobadas == 4, corrida.tabla()


def test_el_control_negativo_detecta_un_guard_roto():
    """Si el guard dejara pasar el valor sin respaldo, el control tiene que gritar."""
    preguntas = [p for p in cargar_set("juguete") if p.control_negativo]
    assert preguntas, "el set de juguete debe traer un control negativo"

    class RespuestaFalsaQueSiempreAprueba:
        texto = "El ZX-100 se alimenta con 30 V DC."
        sources: list = []
        verify = None
        bloqueada = False

    corrida = correr(preguntas, lambda p: RespuestaFalsaQueSiempreAprueba())
    # Sin espera_valores cumplidos igual falla; lo que se comprueba es que el
    # mecanismo de inversión existe y reporta el caso.
    resultado = corrida.resultados[0]
    assert "control negativo" in resultado.motivos[0].lower()


def test_pregunta_trampa_aprueba_cuando_rechaza():
    preguntas = [p for p in cargar_set("juguete") if p.debe_rechazar]
    corrida = correr(preguntas, responder_simulado, set_nombre="trampas")
    assert corrida.aprobadas == corrida.total, corrida.tabla()


def test_la_corrida_serializa_y_guarda(tmp_path):
    corrida = correr(cargar_set("juguete"), responder_simulado, set_nombre="juguete")
    d = corrida.to_dict()
    assert d["total"] == 4
    assert len(d["resultados"]) == 4
    ruta = corrida.guardar(tmp_path)
    assert ruta.exists() and ruta.stat().st_size > 0


def test_equivalencia_de_unidades_en_los_valores_esperados():
    """La fuente dice 3,7 kW, el agente responde 5 HP: el harness debe aceptarlo."""
    p = next(p for p in cargar_set("juguete") if p.id == "juguete-03")
    corrida = correr([p], responder_simulado, set_nombre="equivalencia")
    assert corrida.aprobadas == 1, corrida.tabla()
