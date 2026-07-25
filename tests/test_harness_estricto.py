"""Las debilidades del harness que la auditoría encontró.

Importan porque el eval se corre EN VIVO frente al jurado: un harness que aprueba
lo que no debe es peor que no llevar eval.
"""

from evals.harness import Pregunta, _parece_rechazo, correr


class Resp:
    """Lo mínimo que el harness consume de un RespuestaFinal."""

    def __init__(self, texto, sources=(), verify=None, bloqueada=False):
        self.texto, self.sources, self.verify, self.bloqueada = texto, list(sources), verify, bloqueada


class Verify:
    def __init__(self, ok, detail="", respaldos=()):
        self.ok, self.detail, self.respaldos = ok, detail, list(respaldos)


# --- detección de rechazo en el español que Gemini escribe de verdad -------


def test_reconoce_los_rechazos_reales_de_gemini():
    """Una lista de frases literales fallaba en 12 de 14 casos reales."""
    reales = [
        "La documentación proporcionada no especifica el precio del ZX-100.",
        "El precio no está en la **documentación** proporcionada.",
        "No se indica el costo en las hojas de datos.",
        "Ese dato no aparece en el catálogo.",
        "No consta esa información.",
        "No dispongo de ese dato.",
        "No puedo confirmar ese valor.",
        "Eso queda fuera del alcance de la documentación.",
        "No encontré nada al respecto.",
        "La ficha no menciona el precio.",
        "No hay información de precios.",
        "No se detalla ese parámetro.",
    ]
    fallan = [t for t in reales if not _parece_rechazo(t)]
    assert not fallan, f"no detectó estos rechazos: {fallan}"


def test_no_confunde_una_afirmacion_con_un_rechazo():
    for t in ["Se alimenta con 24 V DC.", "El grado de protección es IP67."]:
        assert not _parece_rechazo(t), t


# --- una muletilla no salva una alucinación --------------------------------


def test_la_trampa_falla_si_dice_el_valor_prohibido_con_muletilla():
    p = Pregunta(
        id="t1",
        pregunta="¿cuánto cuesta?",
        debe_rechazar=True,
        no_debe_decir=["1.200.000"],
    )
    resp = Resp(
        "El ZX-100 cuesta 1.200.000 COP, aunque no puedo confirmar la vigencia.",
        verify=Verify(True),
    )
    r = correr([p], lambda _p: resp).resultados[0]
    assert r.aprobada is False, r.motivos
    assert "valores prohibidos" in " ".join(r.motivos)


def test_la_trampa_aprueba_con_un_rechazo_limpio():
    p = Pregunta(id="t2", pregunta="¿cuánto cuesta?", debe_rechazar=True,
                 no_debe_decir=["1.200.000"])
    r = correr([p], lambda _p: Resp("El precio no está en la documentación.",
                                    verify=Verify(True))).resultados[0]
    assert r.aprobada is True, r.motivos


# --- espera_doc contra los respaldos, no contra lo que trajo la búsqueda ---


def test_espera_doc_se_comprueba_contra_lo_que_sostuvo_la_respuesta():
    """Antes daba verde si la BÚSQUEDA trajo el documento, aunque la respuesta se
    apoyara en otro."""
    p = Pregunta(id="t3", pregunta="¿tensión?", espera_doc="ficha_ZX-200")
    resp = Resp(
        "Se alimenta con 24 V, según ficha_ZX-100.md.",
        verify=Verify(True, respaldos=["ficha_ZX-100.md, Datos, pág. 1"]),
    )
    r = correr([p], lambda _p: resp).resultados[0]
    assert r.aprobada is False
    assert "no se apoyó en" in " ".join(r.motivos)


# --- el control negativo controla algo -------------------------------------


def test_el_control_negativo_no_aprueba_si_el_guard_esta_muerto():
    """Con el guard desactivado la pregunta seguía fallando por otro motivo y el
    control aprobaba igual: no controlaba nada."""
    p = Pregunta(
        id="t4", pregunta="¿tensión?", espera_valores=["24 V"],
        control_negativo=True,
    )
    # Guard muerto: verify.ok = True aunque la respuesta afirme 30 V.
    r = correr([p], lambda _p: Resp("Son 30 V.", verify=Verify(True))).resultados[0]
    assert r.aprobada is False, r.motivos
    assert "CONTROL NEGATIVO APROBÓ" in " ".join(r.motivos)


def test_el_control_negativo_aprueba_cuando_el_guard_bloquea():
    p = Pregunta(
        id="t5", pregunta="¿tensión?", espera_valores=["24 V"],
        control_negativo=True,
    )
    r = correr(
        [p],
        lambda _p: Resp("Son 30 V.", verify=Verify(False, "SIN RESPALDO: 30 v"), bloqueada=True),
    ).resultados[0]
    assert r.aprobada is True, r.motivos
