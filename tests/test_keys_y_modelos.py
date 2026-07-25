"""Tests de rotación de keys y degradación de modelo, sin tocar la API.

Se simulan los 429 porque el comportamiento que importa es el de la cuota agotada,
y esperar a que la cuota real se agote no es una forma de testear.
"""

import pytest

from agent.keys import Rotador, es_error_de_cuota
from agent.llm import Cliente


class ErrorDeCuota(Exception):
    def __init__(self) -> None:
        super().__init__(
            "429 RESOURCE_EXHAUSTED. Quota exceeded for metric: "
            "generate_content_free_tier_requests, limit: 20"
        )


def test_reconoce_el_error_de_cuota_real():
    assert es_error_de_cuota(ErrorDeCuota())
    assert not es_error_de_cuota(ValueError("prompt mal armado"))


def test_rota_de_key_cuando_la_primera_se_agota():
    usadas: list[str] = []

    def fn(key: str) -> str:
        usadas.append(key)
        if key == "k1":
            raise ErrorDeCuota()
        return "listo"

    rot = Rotador(["k1", "k2"], dormir=lambda _: None)
    assert rot.ejecutar(fn) == "listo"
    assert usadas == ["k1", "k2"]
    assert rot.reintentos == 1


def test_un_error_que_no_es_de_cuota_se_propaga_tal_cual():
    """Reintentar seis veces un prompt mal armado solo quema tiempo de depuración."""
    rot = Rotador(["k1", "k2"], dormir=lambda _: None)
    with pytest.raises(ValueError, match="prompt"):
        rot.ejecutar(lambda _k: (_ for _ in ()).throw(ValueError("prompt mal armado")))


def test_se_rinde_con_mensaje_claro_si_todas_las_keys_estan_agotadas():
    rot = Rotador(["k1", "k2"], max_intentos=3, dormir=lambda _: None)
    with pytest.raises(RuntimeError, match="cuota agotada"):
        rot.ejecutar(lambda _k: (_ for _ in ()).throw(ErrorDeCuota()))


# --- degradación de modelo ------------------------------------------------


class ClienteFalso(Cliente):
    """Cliente con el transporte reemplazado: cuenta llamadas por modelo."""

    def __init__(self, modelos, agotados):
        super().__init__(Rotador(["k1"], max_intentos=2, dormir=lambda _: None), modelos)
        self.agotados = set(agotados)
        self.intentos: list[str] = []

    def _cliente(self, key):  # noqa: D102
        cliente = self

        class Models:
            def generate_content(self, model, contents, config):
                cliente.intentos.append(model)
                if model in cliente.agotados:
                    raise ErrorDeCuota()
                return _RespuestaFalsa()

        class Envoltura:
            models = Models()

        return Envoltura()


class _RespuestaFalsa:
    candidates = []


def test_pasa_al_siguiente_modelo_cuando_el_primero_no_tiene_cuota():
    """El caso real: gemini-3.6-flash agotado (20/día) y 3-flash-preview con cuota."""
    c = ClienteFalso(
        ["gemini-3.6-flash", "gemini-3-flash-preview"],
        agotados=["gemini-3.6-flash"],
    )
    c.generar([])
    assert c.modelo_en_uso == "gemini-3-flash-preview"
    assert "gemini-3.6-flash" in c.degradaciones
    assert "cuota agotada en: gemini-3.6-flash" in c.estado()


def test_no_reintenta_el_modelo_agotado_en_la_llamada_siguiente():
    c = ClienteFalso(
        ["gemini-3.6-flash", "gemini-3-flash-preview"],
        agotados=["gemini-3.6-flash"],
    )
    c.generar([])
    c.intentos.clear()
    c.generar([])
    assert "gemini-3.6-flash" not in c.intentos, "no debe volver a quemar tiempo ahí"


def test_falla_con_mensaje_util_si_ningun_modelo_tiene_cuota():
    c = ClienteFalso(["m1", "m2"], agotados=["m1", "m2"])
    with pytest.raises(RuntimeError, match="Sin cuota en ninguno de los modelos"):
        c.generar([])
