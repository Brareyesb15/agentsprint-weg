"""Regresiones de los defectos que encontró la auditoría de la madrugada.

Cada test de acá corresponde a un defecto CONFIRMADO reproduciéndolo. Si alguno se
pone rojo, volvió un fallo que ya nos costó encontrar una vez.
"""

from enum import Enum

import pytest
from pydantic import BaseModel, Field
from typing import Literal

from agent.corpus import Corpus
from agent.guardrails import verificar
from agent.keys import Rotador
from agent.sources import Source, extraer_cantidades
from agent.tools import Tool, ToolOutput

FUENTE = Source(
    doc="ficha.md",
    section="Datos eléctricos",
    page=1,
    snippet="Tensión de alimentación: 24 V DC. Distancia de detección: 12 mm.",
)


# --------------------------------------------------------------------------
# 1. El marcador de lista numerada no es una afirmación
# --------------------------------------------------------------------------


def test_marcador_de_lista_no_cuenta_como_cifra():
    """Pregunta "¿cómo lo instalo?" -> el modelo responde en pasos numerados.
    Antes, el "1." de cada renglón se leía como la cifra 1, ninguna estaba en la
    fuente, y en pantalla se proyectaba "No puedo confirmar 1, 2, 3"."""
    respuesta = "1. Conecta el sensor.\n2. Ajusta la distancia.\n3. Verifica el LED."
    assert extraer_cantidades(respuesta) == []


@pytest.mark.parametrize("marca", ["1.", "2)", "10.", "- 1.", "* 2)"])
def test_variantes_de_marcador(marca):
    assert extraer_cantidades(f"{marca} Conecta el equipo.") == []


def test_respuesta_en_pasos_no_se_bloquea():
    respuesta = (
        "Para instalarlo:\n"
        "1. Alimenta el sensor con 24 V DC.\n"
        "2. Ajusta la distancia a 12 mm.\n"
    )
    res = verificar(respuesta, [FUENTE])
    assert res.ok is True, res.detail
    assert res.checked == 2, "debe ver 24 V y 12 mm, y NADA más"


def test_un_numero_de_verdad_al_inicio_de_renglon_si_se_verifica():
    """El salto es solo del MARCADOR: '1.5 kW' al inicio de renglón sigue contando."""
    cantidades = extraer_cantidades("3,7 kW es la potencia nominal.")
    assert any(c.valor == 3.7 for c in cantidades)


# --------------------------------------------------------------------------
# 2. La "V" de voltios ya no ciega al guard
# --------------------------------------------------------------------------


def test_la_v_de_voltios_no_esconde_el_numero_siguiente():
    """CONTEXTO_IGNORAR tenía "v" por "versión". Consecuencia: en una hoja de datos
    eléctrica, CUALQUIER cifra que siguiera a un voltaje quedaba sin verificar."""
    cantidades = extraer_cantidades("Alimentación 24 V, distancia 12 mm.")
    valores = {c.valor for c in cantidades}
    assert 24.0 in valores
    assert 12.0 in valores, "el 12 quedaba invisible por venir después de la V"


def test_valor_falso_despues_de_un_voltaje_si_se_bloquea():
    res = verificar("Alimentación 24 V, distancia 99 mm.", [FUENTE])
    assert res.ok is False
    assert "99 mm" in res.detail


def test_las_referencias_al_documento_siguen_ignorandose():
    """Quitar "v" y "p" no debe romper lo que sí funcionaba."""
    assert extraer_cantidades("Ver página 2, tabla 4, sección 3.") == []
    assert extraer_cantidades("Según la versión 3 del catálogo.") == []


# --------------------------------------------------------------------------
# 3. El corpus indexa PDF, con número de página
# --------------------------------------------------------------------------


def _pdf_de_prueba(destino):
    fitz = pytest.importorskip("fitz")
    doc = fitz.open()
    p1 = doc.new_page()
    p1.insert_text((72, 90), "Datos electricos")
    p1.insert_text((72, 120), "Tension de alimentacion: 24 V DC")
    p2 = doc.new_page()
    p2.insert_text((72, 90), "Datos mecanicos")
    p2.insert_text((72, 120), "Distancia de deteccion: 12 mm")
    doc.save(str(destino))
    doc.close()


def test_el_corpus_indexa_pdf_con_pagina(tmp_path):
    """Sin esto, poner las hojas de datos reales en data/ daba 0 fragmentos y el
    guard bloqueaba el 100% de las respuestas con un número."""
    _pdf_de_prueba(tmp_path / "dataSheet_XY_es.pdf")
    corpus = Corpus.desde_directorio(tmp_path)

    assert len(corpus.fragmentos) == 2, "un fragmento por página"
    paginas = sorted(f.page for f in corpus.fragmentos)
    assert paginas == [1, 2], "el número de página tiene que llegar hasta la cita"


def test_la_cita_de_un_pdf_menciona_la_pagina(tmp_path):
    _pdf_de_prueba(tmp_path / "dataSheet_XY_es.pdf")
    corpus = Corpus.desde_directorio(tmp_path)
    golpes = corpus.buscar("distancia de deteccion", k=1)
    assert golpes, "la búsqueda tiene que encontrar texto dentro del PDF"
    frag, _ = golpes[0]
    etiqueta = frag.como_source().etiqueta()
    assert "dataSheet_XY_es.pdf" in etiqueta
    assert "pág. 2" in etiqueta, f"la cita debe llevar la página: {etiqueta}"


def test_pdf_sin_texto_extraible_avisa(tmp_path):
    """Caso real: las fichas individuales de Pfannenberg son imágenes."""
    fitz = pytest.importorskip("fitz")
    doc = fitz.open()
    doc.new_page()  # página en blanco: nada que extraer
    doc.save(str(tmp_path / "solo_imagen.pdf"))
    doc.close()

    corpus = Corpus.desde_directorio(tmp_path)
    assert corpus.fragmentos == []
    assert corpus.avisos, "tiene que avisar que el PDF no tiene texto"
    assert "visión u OCR" in corpus.avisos[0]


def test_el_corpus_sigue_indexando_markdown(tmp_path):
    (tmp_path / "ficha.md").write_text(
        "# Título\n\n## Sección 1\n\nTensión: 24 V DC.\n", encoding="utf-8"
    )
    corpus = Corpus.desde_directorio(tmp_path)
    assert any(f.section == "Sección 1" for f in corpus.fragmentos)


# --------------------------------------------------------------------------
# 4. Declaraciones de herramientas: $ref resuelto, const preservado
# --------------------------------------------------------------------------


class Familia(str, Enum):
    INDUCTIVO = "inductivo"
    CAPACITIVO = "capacitivo"


class Medida(BaseModel):
    valor: float
    unidad: str


class ArgsRicos(BaseModel):
    """Una herramienta de dominio realista: Enum + modelo anidado + Literal."""

    familia: Familia = Field(description="tipo de sensor")
    medida: Medida
    modo: Literal["estricto"] = "estricto"


def _declaracion_de(modelo) -> dict:
    return Tool(
        nombre="t", descripcion="d", args_model=modelo, fn=lambda a: ToolOutput(None)
    ).declaracion()


def test_no_quedan_refs_colgados_en_la_declaracion():
    """Antes: se borraba $defs y quedaba {"$ref": "#/$defs/Medida"} apuntando al
    vacío -> 400 de esquema inválido en la primera tool de dominio, en vivo."""
    d = _declaracion_de(ArgsRicos)
    texto = repr(d)
    assert "$ref" not in texto, f"quedó un $ref colgado: {d}"
    assert "$defs" not in texto


def test_el_modelo_anidado_queda_inline_y_completo():
    d = _declaracion_de(ArgsRicos)
    medida = d["parameters"]["properties"]["medida"]
    assert medida.get("type") == "object"
    assert set(medida.get("properties", {})) == {"valor", "unidad"}


def test_el_enum_sobrevive():
    d = _declaracion_de(ArgsRicos)
    familia = d["parameters"]["properties"]["familia"]
    assert sorted(familia.get("enum", [])) == ["capacitivo", "inductivo"]


def test_el_literal_se_traduce_a_enum_en_vez_de_perderse():
    """Borrar `const` dejaba un string libre: el modelo mandaba cualquier cosa,
    Pydantic la rechazaba y se quemaba una llamada de cuota para nada."""
    d = _declaracion_de(ArgsRicos)
    modo = d["parameters"]["properties"]["modo"]
    assert modo.get("enum") == ["estricto"], modo


def test_el_motivo_sigue_siendo_obligatorio():
    d = _declaracion_de(ArgsRicos)
    assert "motivo" in d["parameters"]["properties"]
    assert "motivo" in d["parameters"]["required"]


# --------------------------------------------------------------------------
# 5. No dormir después del último intento
# --------------------------------------------------------------------------


class ErrorDeCuota(Exception):
    def __init__(self) -> None:
        super().__init__("429 RESOURCE_EXHAUSTED quota exceeded limit: 20")


def test_no_duerme_despues_del_ultimo_intento():
    """Esa espera final no la aprovechaba nadie: al volver del sleep se salía del
    bucle igual. Eran ~15 s de pantalla congelada frente al jurado."""
    dormidas: list[float] = []
    rot = Rotador(["k1"], max_intentos=3, dormir=dormidas.append)
    with pytest.raises(RuntimeError):
        rot.ejecutar(lambda _k: (_ for _ in ()).throw(ErrorDeCuota()))
    assert len(dormidas) == 2, f"3 intentos -> 2 esperas, no 3. Fueron {dormidas}"


def test_la_espera_total_es_corta():
    """Un 429 por cuota DIARIA no se cura esperando: se cura cambiando de modelo."""
    dormidas: list[float] = []
    rot = Rotador(["k1", "k2"], max_intentos=6, dormir=dormidas.append)
    with pytest.raises(RuntimeError):
        rot.ejecutar(lambda _k: (_ for _ in ()).throw(ErrorDeCuota()))
    # Cota con la cuenta hecha, no a ojo: espera_maxima=4 s y el jitter llega a 1,3x,
    # con 4 esperas efectivas (6 intentos, 2 keys) -> techo 1,3*(2+4+4+4) = 18,2 s.
    # Un límite de 15 s quedaba DENTRO del rango de jitter y el test parpadeaba.
    assert sum(dormidas) < 19, f"antes eran ~45 s. Ahora {sum(dormidas):.1f} s"


# --------------------------------------------------------------------------
# 6. El resumen que se proyecta es legible
# --------------------------------------------------------------------------


def test_el_resumen_no_es_un_repr_de_python():
    salida = ToolOutput(
        result=[
            {"doc": "dataSheet_XY_es.pdf", "section": "Datos eléctricos", "texto": "…"},
            {"doc": "dataSheet_XY_es.pdf", "section": "Datos mecánicos", "texto": "…"},
        ],
        sources=[FUENTE],
    )
    r = salida.resumen()
    assert "{" not in r and "'" not in r, f"parece un repr(): {r}"
    assert "2 fragmento(s)" in r
    assert "1 fuente" in r


def test_el_resumen_corta_en_frontera_de_palabra():
    salida = ToolOutput(result="palabra " * 40)
    r = salida.resumen()
    # El sufijo de fuentes va DESPUÉS del corte, así que "…" queda en el medio.
    cuerpo = r.split(" · ")[0]
    assert cuerpo.endswith("…"), r
    assert cuerpo.rstrip("…").endswith("palabra"), f"cortó a media palabra: {cuerpo!r}"


def test_el_resumen_de_una_incertidumbre_lo_dice():
    salida = ToolOutput(result=None, uncertainty="no hay nada en el corpus sobre 'precio'")
    assert salida.resumen().startswith("sin dato firme:")
