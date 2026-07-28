"""El agente no recordaba NADA de lo hablado, y eso rompía el guion de levantamiento.

`Agente._responder` armaba el historial con un solo mensaje —el del turno actual—,
así que al llegar al paso 4 del guion preguntaba el montaje sin acordarse de los HP
que el cliente había dado en el paso 2. La continuidad dependía por completo de que
algo hubiera quedado como HECHO en `SessionMemory`, y una respuesta en lenguaje
natural ("es para una banda transportadora") no guarda ningún hecho.
"""

from agent.conversacion import TOPE_MENSAJES, Conversacion
from agent.dominio import NuevaBusquedaArgs, _nueva_busqueda
from agent.memory import SessionMemory


def test_guarda_los_turnos_en_orden():
    c = Conversacion()
    c.agregar("usuario", "necesito un motor")
    c.agregar("agente", "¿reemplazo o proyecto nuevo?")
    c.agregar("usuario", "proyecto nuevo, 10 HP")

    assert [(t.rol, t.texto) for t in c] == [
        ("usuario", "necesito un motor"),
        ("agente", "¿reemplazo o proyecto nuevo?"),
        ("usuario", "proyecto nuevo, 10 HP"),
    ]


def test_se_topa_en_15_y_se_cae_el_mas_viejo():
    """Con 20 requests/día y 3-6 llamadas por turno, arrastrar la conversación
    entera es cuota que no se recupera."""
    c = Conversacion()
    for i in range(TOPE_MENSAJES + 5):
        c.agregar("usuario", f"mensaje {i}")

    assert len(c) == TOPE_MENSAJES
    textos = [t.texto for t in c]
    assert textos[0] == "mensaje 5", "no descartó los más viejos"
    assert textos[-1] == f"mensaje {TOPE_MENSAJES + 4}"


def test_los_mensajes_vacios_no_ocupan_lugar():
    c = Conversacion()
    for basura in ["", "   ", "\n"]:
        c.agregar("usuario", basura)
    assert len(c) == 0


# --- empezar de cero con otro motor -----------------------------------------


def _con_datos():
    memoria = SessionMemory()
    memoria.guardar("placa.potencia_kw", 7.457, origen="registrar_placa")
    memoria.guardar("placa.polos", 4, origen="registrar_placa")
    conversacion = Conversacion()
    conversacion.agregar("usuario", "un motor de 10 HP")
    conversacion.agregar("agente", "¿a qué voltaje se conecta?")
    return memoria, conversacion


def test_sin_confirmar_no_borra_nada():
    """Perder los datos que el cliente ya dio, sin preguntar, es peor que preguntar
    de más: lo obliga a repetir toda la conversación."""
    memoria, conversacion = _con_datos()

    salida = _nueva_busqueda(
        NuevaBusquedaArgs(confirmado=False, motivo="dijo 'otro motor'"),
        memoria,
        conversacion,
    )

    assert salida.result["borrado"] is False
    assert len(memoria) == 2, "borró sin confirmación"
    assert len(conversacion) == 2
    assert "pregúntale" in salida.uncertainty.lower()


def test_confirmado_borra_hechos_e_historial():
    memoria, conversacion = _con_datos()

    salida = _nueva_busqueda(
        NuevaBusquedaArgs(confirmado=True, motivo="confirmó que es otra cotización"),
        memoria,
        conversacion,
    )

    assert salida.result["borrado"] is True
    assert len(memoria) == 0
    assert len(conversacion) == 0
    # Se declara QUÉ se descartó: un borrado silencioso no se puede auditar.
    assert salida.result["hechos_descartados"] == ["placa.polos", "placa.potencia_kw"]
    assert salida.result["mensajes_descartados"] == 2


def test_el_borrado_es_real_no_una_promesa_del_prompt():
    """Un 'olvida lo anterior' en el prompt no borra: los hechos se siguen inyectando
    en el sistema y el agente los sigue viendo."""
    memoria, conversacion = _con_datos()
    assert "placa.polos" in memoria.para_prompt()

    _nueva_busqueda(NuevaBusquedaArgs(confirmado=True), memoria, conversacion)

    assert "placa.polos" not in memoria.para_prompt()
