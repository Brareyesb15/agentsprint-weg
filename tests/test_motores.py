"""Física y ahorro. Es el módulo que aguanta un Q&A de ingenieros con calculadora."""

import pytest

from agent import motores
from agent.corpus import Corpus
from agent.dominio import registrar_dominio
from agent.events import Emitter
from agent.memory import SessionMemory
from agent.tools import construir_registro


# --- polos desde rpm --------------------------------------------------------


@pytest.mark.parametrize(
    "rpm, polos",
    [(3500, 2), (1750, 4), (1765, 4), (1160, 6), (870, 8), (1780, 4)],
)
def test_deduce_los_polos_de_un_motor_real(rpm, polos):
    assert motores.polos_desde_rpm(rpm)[0] == polos


@pytest.mark.parametrize("rpm", [17500, 3700, 5000, 0, -100])
def test_rechaza_rpm_imposibles(rpm):
    """17500 rpm es el error de lectura clásico de una placa oxidada."""
    assert motores.polos_desde_rpm(rpm)[0] is None


def test_el_deslizamiento_de_1750_rpm_es_realista():
    polos, s = motores.polos_desde_rpm(1750)
    assert polos == 4
    assert 0.02 < s < 0.03  # 2,8%


# --- validación de placa ----------------------------------------------------


def test_placa_coherente():
    d = motores.validar_placa(potencia=10, unidad_potencia="hp", rpm=1750, tension=440)
    assert d.coherente is True
    assert d.polos == 4
    assert round(d.potencia_kw, 2) == 7.46


def test_placa_con_rpm_mal_leidos_se_marca_incoherente():
    d = motores.validar_placa(potencia=10, rpm=17500, tension=440)
    assert d.coherente is False
    assert "17500 rpm" in " ".join(d.problemas)


def test_tension_fuera_del_estandar_se_marca():
    d = motores.validar_placa(rpm=1750, tension=317)
    assert d.coherente is False
    assert "317 V" in " ".join(d.problemas)


def test_potencia_que_no_cuadra_con_la_corriente_se_marca():
    """10 HP a 440 V deberían ser ~11 A, no 80 A."""
    d = motores.validar_placa(potencia=10, rpm=1750, tension=440, corriente=80)
    assert d.coherente is False
    assert "√3" in " ".join(d.problemas)


def test_potencia_consistente_con_la_corriente_pasa():
    d = motores.validar_placa(potencia=10, rpm=1750, tension=440, corriente=11.5)
    assert d.coherente is True
    assert any("consistente" in n for n in d.notas)


def test_eficiencia_en_porcentaje_se_detecta():
    d = motores.validar_placa(rpm=1750, eficiencia=89)
    assert d.coherente is False
    assert "porcentaje" in " ".join(d.problemas)


# --- ahorro -----------------------------------------------------------------


def test_el_ahorro_sale_de_la_diferencia_de_eficiencias():
    r = motores.calcular_ahorro(
        potencia_kw=7.46, eficiencia_vieja=0.872, eficiencia_nueva=0.917,
        horas_dia=16, dias_ano=300, tarifa_kwh=800, carga=0.75,
    )
    # 7,46 * 0,75 * 4800 * (1/0,872 - 1/0,917) = ~1512 kWh
    assert 1450 < r.kwh_ano < 1600
    assert r.pesos_ano == pytest.approx(r.kwh_ano * 800)
    assert r.consumo_viejo_kwh > r.consumo_nuevo_kwh


def test_el_payback_sale_en_meses():
    r = motores.calcular_ahorro(
        potencia_kw=7.46, eficiencia_vieja=0.872, eficiencia_nueva=0.917,
        horas_dia=16, dias_ano=300, tarifa_kwh=800, precio_motor=3_000_000,
    )
    assert r.payback_meses is not None
    assert r.payback_meses == pytest.approx(3_000_000 / (r.pesos_ano / 12))


def test_sin_precio_no_hay_payback():
    r = motores.calcular_ahorro(
        potencia_kw=7.46, eficiencia_vieja=0.872, eficiencia_nueva=0.917,
        horas_dia=16, dias_ano=300, tarifa_kwh=800,
    )
    assert r.payback_meses is None


def test_se_niega_a_calcular_si_el_nuevo_no_es_mas_eficiente():
    with pytest.raises(ValueError, match="no hay ahorro"):
        motores.calcular_ahorro(
            potencia_kw=7.46, eficiencia_vieja=0.92, eficiencia_nueva=0.90,
            horas_dia=16, dias_ano=300, tarifa_kwh=800,
        )


def test_rechaza_eficiencias_en_porcentaje():
    with pytest.raises(ValueError, match="entre 0 y 1"):
        motores.calcular_ahorro(
            potencia_kw=7.46, eficiencia_vieja=87.2, eficiencia_nueva=91.7,
            horas_dia=16, dias_ano=300, tarifa_kwh=800,
        )


def test_la_sensibilidad_da_tres_turnos_crecientes():
    filas = motores.sensibilidad(
        potencia_kw=7.46, eficiencia_vieja=0.872, eficiencia_nueva=0.917,
        dias_ano=300, tarifa_kwh=800,
    )
    assert [f["turnos"] for f in filas] == [1, 2, 3]
    ahorros = [f["ahorro_kwh_ano"] for f in filas]
    assert ahorros == sorted(ahorros), "más turnos, más ahorro"


# --- herramientas registradas ----------------------------------------------


def _registro():
    em = Emitter()
    mem = SessionMemory(em)
    reg = registrar_dominio(construir_registro(Corpus([])), Corpus([]), mem)
    return reg, mem, em


def test_las_herramientas_quedan_registradas_y_son_deterministas():
    reg, _, _ = _registro()
    assert "registrar_placa" in reg.nombres()
    assert "calcular_ahorro" in reg.nombres()
    assert "buscar_motor_equivalente" in reg.nombres()
    deterministas, con_modelo = reg.cuentas()
    assert con_modelo == 0, "ninguna herramienta debe llamar al modelo"
    assert deterministas == 5


def test_registrar_placa_guarda_los_hechos_en_memoria():
    """El ítem 'memoria' del checklist deja de ser una clase sin usar."""
    reg, mem, em = _registro()
    salida, _ = reg.ejecutar(
        "registrar_placa",
        {"potencia": 10, "rpm": 1750, "tension": 440, "frame": "132M", "motivo": "leí la placa"},
    )
    assert salida.uncertainty is None
    assert mem.obtener("placa.polos") == 4
    assert mem.obtener("placa.frame") == "132M"
    assert any(e.type == "memory" for e in em.historial), "debe emitirse el evento memory"


def test_una_placa_incoherente_no_ensucia_la_memoria():
    reg, mem, _ = _registro()
    salida, _ = reg.ejecutar(
        "registrar_placa", {"potencia": 10, "rpm": 17500, "motivo": "leí la placa"}
    )
    assert salida.uncertainty is not None
    assert "No calcules nada" in salida.uncertainty
    assert len(mem) == 0


def test_buscar_motor_sin_catalogo_lo_dice_en_vez_de_inventar():
    reg, _, _ = _registro()
    salida, _ = reg.ejecutar(
        "buscar_motor_equivalente",
        {"potencia_hp": 10, "polos": 4, "motivo": "busco el equivalente"},
    )
    assert salida.result == []
    assert "no lo inventes" in salida.uncertainty


def test_calcular_ahorro_devuelve_claves_con_unidad():
    """El guard usa el nombre de la clave para saber qué es cada número."""
    reg, mem, _ = _registro()
    salida, _ = reg.ejecutar(
        "calcular_ahorro",
        {
            "potencia_kw": 7.46, "eficiencia_vieja": 0.872, "eficiencia_nueva": 0.917,
            "horas_dia": 16, "tarifa_kwh": 800, "precio_motor": 3_000_000,
            "motivo": "calculo el retorno",
        },
    )
    assert "ahorro_kwh_ano" in salida.result
    assert "payback_meses" in salida.result
    assert mem.obtener("tarifa_kwh") == 800


def test_con_precio_el_calculo_no_sale_marcado_incierto():
    """Iba con `uncertainty` puesta aunque el cálculo fuera perfecto, y el agente
    abría la respuesta disculpándose por el precio en vez de dar el payback."""
    reg, _, _ = _registro()
    salida, _ = reg.ejecutar("calcular_ahorro", {
        "potencia_kw": 7.457, "eficiencia_vieja": 0.875, "eficiencia_nueva": 0.92,
        "horas_dia": 16, "tarifa_kwh": 850, "precio_motor": 3_200_000, "motivo": "roi",
    })
    assert salida.uncertainty is None
    assert salida.result["payback_meses"] == 30.1
    assert "distribuidor" in salida.result["nota_precio"]


def test_sin_precio_si_avisa_que_falta():
    reg, _, _ = _registro()
    salida, _ = reg.ejecutar("calcular_ahorro", {
        "potencia_kw": 7.457, "eficiencia_vieja": 0.875, "eficiencia_nueva": 0.92,
        "horas_dia": 16, "tarifa_kwh": 850, "motivo": "roi",
    })
    assert salida.uncertainty is not None and "Pídelo" in salida.uncertainty
    assert salida.result["payback_meses"] is None


def test_las_cifras_del_roi_de_la_demo_son_las_verificadas_a_mano():
    """Números del arco de la demo, calculados a mano contra el catálogo:
    IE1 87,5% (pág. 57) -> IE3 92,0% (pág. 50), 16 h/día, 300 días, $850/kWh."""
    r = motores.calcular_ahorro(
        potencia_kw=7.457, eficiencia_vieja=0.875, eficiencia_nueva=0.92,
        horas_dia=16, dias_ano=300, tarifa_kwh=850, carga=0.75,
        precio_motor=3_200_000,
    )
    d = r.como_dict()
    assert d["consumo_viejo_kwh_ano"] == 30680.2
    assert d["consumo_nuevo_kwh_ano"] == 29179.6
    assert d["ahorro_kwh_ano"] == 1500.7
    assert d["payback_meses"] == 30.1
    assert d["co2_evitado_ton_ano"] == 0.91
