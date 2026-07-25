"""Física de motores de inducción y cálculo de ahorro. CERO llamadas al modelo.

Este módulo es la tesis del proyecto hecha código: **lo que se puede calcular no se
le pregunta a un modelo**. Frente a cinco ingenieros con calculadora, "casi siempre
acierta" es perder. Acá todo es aritmética verificable.

Dos trabajos:

1. **Validar lo que la visión leyó de la placa.** Una placa oxidada se lee mal: un
   "1750" puede salir "17500". El validador no confía: cruza los RPM contra las
   velocidades síncronas a 60 Hz, el voltaje contra el set estándar colombiano, y la
   potencia contra P ≈ √3·V·I·cosφ·η. Si algo no cuadra, el agente REPREGUNTA en vez
   de calcular sobre un dato malo.

2. **Calcular el ahorro de cambiar un motor IE1 viejo por uno IE3.**

Nada de esto usa IA, y ese es el punto.
"""

from __future__ import annotations

from dataclasses import dataclass, field

HP_A_KW = 0.7457
FRECUENCIA_HZ = 60  # Colombia

# Velocidad síncrona = 120 · f / polos. A 60 Hz:
SINCRONAS: dict[int, int] = {2: 3600, 4: 1800, 6: 1200, 8: 900, 10: 720, 12: 600}

# Un motor de inducción SIEMPRE gira por debajo de la síncrona (si no, es un
# generador). El deslizamiento normal de un motor industrial va de 1% a 5%.
DESLIZAMIENTO_MIN = 0.002
DESLIZAMIENTO_MAX = 0.08

# Tensiones estándar en Colombia (60 Hz), incluyendo las duales de placa.
TENSIONES_ESTANDAR = {208, 220, 230, 240, 380, 400, 440, 460, 480, 575}

# Factor de emisión para proyectos de eficiencia energética en Colombia.
# OJO: es el de PROYECTOS (UPME), no el de inventarios corporativos de GEI (~0,220).
# Confírmalo en el documento de la UPME antes de proyectarlo en el pitch.
CO2_TON_POR_MWH = 0.607


# ---------------------------------------------------------------------------
# Placa
# ---------------------------------------------------------------------------


@dataclass
class Diagnostico:
    """Resultado de validar una placa. `coherente=False` obliga a repreguntar."""

    coherente: bool
    polos: int | None = None
    deslizamiento: float | None = None
    potencia_kw: float | None = None
    problemas: list[str] = field(default_factory=list)
    notas: list[str] = field(default_factory=list)

    def resumen(self) -> str:
        if self.coherente:
            base = f"placa coherente: {self.polos} polos"
            if self.deslizamiento is not None:
                base += f", deslizamiento {self.deslizamiento * 100:.1f}%"
            return base + ("; " + "; ".join(self.notas) if self.notas else "")
        return "placa INCOHERENTE: " + "; ".join(self.problemas)


def polos_desde_rpm(rpm: float) -> tuple[int | None, float | None]:
    """Deduce los polos a partir de los RPM de placa, a 60 Hz.

    Devuelve (polos, deslizamiento). Si ningún número de polos da un deslizamiento
    plausible, devuelve (None, None) — y eso es una señal de lectura mala, no un
    motor raro. Ejemplo: 1750 rpm -> síncrona 1800 -> 4 polos, 2,8% de deslizamiento.
    """
    if rpm <= 0:
        return None, None
    mejor: tuple[int, float] | None = None
    for polos, sincrona in SINCRONAS.items():
        if rpm > sincrona:  # por encima de la síncrona no es un motor
            continue
        s = (sincrona - rpm) / sincrona
        if DESLIZAMIENTO_MIN <= s <= DESLIZAMIENTO_MAX:
            if mejor is None or s < mejor[1]:
                mejor = (polos, s)
    return mejor if mejor else (None, None)


def potencia_a_kw(valor: float, unidad: str) -> float:
    u = unidad.strip().lower()
    if u in {"hp", "cv"}:
        return valor * HP_A_KW
    if u == "w":
        return valor / 1000.0
    return valor  # kW


def validar_placa(
    potencia: float | None = None,
    unidad_potencia: str = "hp",
    rpm: float | None = None,
    tension: float | None = None,
    corriente: float | None = None,
    factor_potencia: float = 0.85,
    eficiencia: float | None = None,
) -> Diagnostico:
    """Cruza los datos de la placa entre sí. Treinta líneas que compran mucho.

    Es el guardrail más demostrable del proyecto y el que a un ingeniero le encanta,
    porque **no es IA: es física**.
    """
    problemas: list[str] = []
    notas: list[str] = []

    # --- RPM contra velocidades síncronas -------------------------------
    polos = deslizamiento = None
    if rpm is not None:
        polos, deslizamiento = polos_desde_rpm(rpm)
        if polos is None:
            cercanas = ", ".join(str(v) for v in sorted(SINCRONAS.values()))
            problemas.append(
                f"{rpm:g} rpm no corresponde a ningún motor de inducción a 60 Hz "
                f"(las síncronas son {cercanas}); revisa la lectura de la placa"
            )

    # --- Tensión contra el set estándar ---------------------------------
    if tension is not None:
        if not any(abs(tension - v) <= 0.05 * v for v in TENSIONES_ESTANDAR):
            problemas.append(
                f"{tension:g} V no es una tensión estándar a 60 Hz; "
                "puede ser una lectura parcial de una placa de doble tensión"
            )

    # --- Potencia declarada contra la eléctrica --------------------------
    potencia_kw = None
    if potencia is not None:
        potencia_kw = potencia_a_kw(potencia, unidad_potencia)
        if potencia_kw <= 0:
            problemas.append("la potencia leída es cero o negativa")

        if tension and corriente:
            eff = eficiencia if eficiencia else 0.9
            electrica_kw = (3**0.5) * tension * corriente * factor_potencia * eff / 1000
            if electrica_kw > 0:
                desvio = abs(electrica_kw - potencia_kw) / potencia_kw
                if desvio > 0.25:
                    problemas.append(
                        f"la potencia de placa ({potencia_kw:.2f} kW) no cuadra con "
                        f"√3·V·I·cosφ·η ({electrica_kw:.2f} kW): {desvio * 100:.0f}% de "
                        "diferencia. Falta un dato o hay una cifra mal leída"
                    )
                else:
                    notas.append(
                        f"potencia consistente con la corriente ({desvio * 100:.0f}% de desvío)"
                    )

    if eficiencia is not None and not (0.5 <= eficiencia <= 1.0):
        problemas.append(
            f"eficiencia de {eficiencia:g} fuera de rango; ¿venía en porcentaje?"
        )

    return Diagnostico(
        coherente=not problemas,
        polos=polos,
        deslizamiento=deslizamiento,
        potencia_kw=potencia_kw,
        problemas=problemas,
        notas=notas,
    )


# ---------------------------------------------------------------------------
# Ahorro
# ---------------------------------------------------------------------------


@dataclass
class Ahorro:
    kwh_ano: float
    pesos_ano: float
    payback_meses: float | None
    co2_ton_ano: float
    consumo_viejo_kwh: float
    consumo_nuevo_kwh: float

    def como_dict(self) -> dict[str, float | None]:
        """Claves CON la unidad en el nombre, a propósito: el guard de citas usa el
        nombre de la clave para saber qué representa cada número."""
        return {
            "ahorro_kwh_ano": round(self.kwh_ano, 1),
            "ahorro_pesos_ano": round(self.pesos_ano, 0),
            "payback_meses": round(self.payback_meses, 1) if self.payback_meses else None,
            "co2_evitado_ton_ano": round(self.co2_ton_ano, 2),
            "consumo_viejo_kwh_ano": round(self.consumo_viejo_kwh, 1),
            "consumo_nuevo_kwh_ano": round(self.consumo_nuevo_kwh, 1),
        }


def calcular_ahorro(
    potencia_kw: float,
    eficiencia_vieja: float,
    eficiencia_nueva: float,
    horas_dia: float,
    dias_ano: float,
    tarifa_kwh: float,
    carga: float = 0.75,
    precio_motor: float | None = None,
) -> Ahorro:
    """Ahorro anual de reemplazar un motor por uno más eficiente.

    La cuenta que importa: la energía que consume un motor es la potencia ÚTIL en el
    eje dividida por su eficiencia. Un motor menos eficiente no entrega menos: come
    más para entregar lo mismo. De ahí sale el ahorro.

        consumo = (kW nominales × carga / eficiencia) × horas × días

    `carga` es el factor de carga real (0,75 = trabajando al 75% de su capacidad),
    que es lo típico en planta. Si se asume 1,0 se sobreestima el ahorro, y frente a
    un ingeniero eso se nota.
    """
    for nombre, eff in (("vieja", eficiencia_vieja), ("nueva", eficiencia_nueva)):
        if not 0 < eff <= 1:
            raise ValueError(f"la eficiencia {nombre} debe ir entre 0 y 1, llegó {eff}")
    if eficiencia_nueva <= eficiencia_vieja:
        raise ValueError(
            "el motor nuevo no es más eficiente que el viejo: no hay ahorro que calcular"
        )

    horas_ano = horas_dia * dias_ano
    util_kw = potencia_kw * carga
    viejo = util_kw / eficiencia_vieja * horas_ano
    nuevo = util_kw / eficiencia_nueva * horas_ano
    kwh = viejo - nuevo
    pesos = kwh * tarifa_kwh

    payback = None
    if precio_motor and pesos > 0:
        payback = precio_motor / (pesos / 12)

    return Ahorro(
        kwh_ano=kwh,
        pesos_ano=pesos,
        payback_meses=payback,
        co2_ton_ano=kwh / 1000 * CO2_TON_POR_MWH,
        consumo_viejo_kwh=viejo,
        consumo_nuevo_kwh=nuevo,
    )


def sensibilidad(turnos: tuple[int, ...] = (1, 2, 3), **kwargs) -> list[dict]:
    """El mismo cálculo a 1, 2 y 3 turnos. Un ahorro sin sensibilidad es un número
    suelto; con sensibilidad es un análisis, y aguanta la pregunta "¿y si opera menos?"."""
    salida = []
    for t in turnos:
        a = calcular_ahorro(horas_dia=8 * t, **kwargs)
        salida.append({"turnos": t, "horas_dia": 8 * t, **a.como_dict()})
    return salida
