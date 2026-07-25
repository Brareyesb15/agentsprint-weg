"""Herramientas de dominio: motores WEG. Se registran sobre el registro base.

Reparto a propósito — es el dato del pitch:

    registrar_placa           NO usa el modelo (valida con física)
    calcular_ahorro           NO usa el modelo (aritmética)
    buscar_motor_equivalente  NO usa el modelo (búsqueda + cita)
    buscar_conocimiento       NO usa el modelo   } del registro base
    leer_documento            NO usa el modelo   }

Lo único que hace el modelo es LEER la foto y REDACTAR. Todo lo que se puede
equivocar con consecuencias —una cuenta, un cruce de catálogo, una validación—
es Python. "El modelo no hace la cuenta" es literalmente cierto acá.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from agent import motores
from agent.corpus import Corpus
from agent.memory import SessionMemory
from agent.tools import Registro, Tool, ToolOutput
from agent.sources import Source


# ---------------------------------------------------------------------------
# 1. Registrar y validar la placa
# ---------------------------------------------------------------------------


class PlacaArgs(BaseModel):
    """Lo que el modelo LEYÓ en la foto. Él hace de OCR; la física la revisa Python."""

    potencia: float | None = Field(None, description="Potencia de placa, el número solo")
    unidad_potencia: str = Field("hp", description="hp, kw o w")
    rpm: float | None = Field(None, description="RPM nominales de placa")
    tension: float | None = Field(None, description="Tensión en voltios. Si es dual (220/440), la menor")
    corriente: float | None = Field(None, description="Corriente nominal en amperios")
    eficiencia: float | None = Field(None, description="Rendimiento de placa como fracción (0,89), si aparece")
    frame: str | None = Field(None, description="Carcasa, p.ej. 132M o 213/5T")
    marca: str | None = Field(None, description="Marca que se lee en la placa")
    ilegibles: list[str] = Field(
        default_factory=list,
        description="Campos que NO pudiste leer con confianza. Sé honesto: es mejor "
        "declararlos que adivinarlos.",
    )


def _registrar_placa(a: PlacaArgs, memoria: SessionMemory) -> ToolOutput:
    d = motores.validar_placa(
        potencia=a.potencia,
        unidad_potencia=a.unidad_potencia,
        rpm=a.rpm,
        tension=a.tension,
        corriente=a.corriente,
        eficiencia=a.eficiencia,
    )

    datos = {
        "potencia_kw": round(d.potencia_kw, 3) if d.potencia_kw else None,
        "polos": d.polos,
        "rpm": a.rpm,
        "tension_v": a.tension,
        "corriente_a": a.corriente,
        "frame": a.frame,
        "marca": a.marca,
        "coherente": d.coherente,
    }

    # La memoria de sesión se llena ACÁ, y se ve en pantalla. No es historial de
    # chat: son hechos establecidos que el agente reusa tres preguntas después.
    if d.coherente:
        for k, v in datos.items():
            if v is not None:
                memoria.guardar(f"placa.{k}", v, origen="registrar_placa")

    if not d.coherente:
        return ToolOutput(
            result={**datos, "problemas": d.problemas},
            uncertainty=(
                "La placa no es coherente: " + "; ".join(d.problemas) +
                ". No calcules nada con estos datos: pregúntale al usuario y confirma."
            ),
        )

    faltan = list(a.ilegibles)
    incierto = None
    if faltan:
        incierto = "no se pudieron leer: " + ", ".join(faltan)

    return ToolOutput(
        result={**datos, "diagnostico": d.resumen()},
        sources=[
            Source(
                doc="placa del motor (foto del usuario)",
                section="validación física a 60 Hz",
                page=None,
                snippet=d.resumen(),
            )
        ],
        uncertainty=incierto,
    )


# ---------------------------------------------------------------------------
# 2. Buscar el equivalente en el catálogo
# ---------------------------------------------------------------------------


class BuscarMotorArgs(BaseModel):
    potencia_hp: float | None = Field(None, description="Potencia en HP")
    polos: int | None = Field(None, description="Número de polos: 2, 4, 6 u 8")
    frame: str | None = Field(None, description="Carcasa, si se conoce")
    extra: str = Field("", description="Cualquier otro término del catálogo a buscar")


def _buscar_motor(a: BuscarMotorArgs, corpus: Corpus) -> ToolOutput:
    partes = []
    if a.potencia_hp:
        partes.append(f"{a.potencia_hp:g} HP")
        partes.append(f"{motores.potencia_a_kw(a.potencia_hp, 'hp'):.2f} kW")
    if a.polos:
        partes.append(f"{a.polos} polos")
        partes.append(str(motores.SINCRONAS.get(a.polos, "")))
    if a.frame:
        partes.append(a.frame)
    if a.extra:
        partes.append(a.extra)
    consulta = " ".join(p for p in partes if p).strip()

    if not consulta:
        return ToolOutput(result=None, uncertainty="no me diste ningún criterio de búsqueda")

    golpes = corpus.buscar(consulta, k=4)
    if not golpes:
        return ToolOutput(
            result=[],
            uncertainty=(
                f"no hay nada en el catálogo cargado para '{consulta}'. "
                "Puede que el corpus no tenga ese producto: no lo inventes, dilo."
            ),
        )

    sources = [
        frag.como_source(corpus.lineas_relevantes(frag, consulta)) for frag, _ in golpes
    ]
    return ToolOutput(
        result=[
            {"doc": s.doc, "seccion": s.section, "pagina": s.page, "texto": s.snippet}
            for s in sources
        ],
        sources=sources,
    )


# ---------------------------------------------------------------------------
# 3. Calcular el ahorro
# ---------------------------------------------------------------------------


class AhorroArgs(BaseModel):
    potencia_kw: float = Field(description="Potencia nominal del motor en kW")
    eficiencia_vieja: float = Field(description="Rendimiento del motor actual, como fracción (0,872)")
    eficiencia_nueva: float = Field(description="Rendimiento del motor propuesto, como fracción (0,917)")
    horas_dia: float = Field(description="Horas de operación al día")
    tarifa_kwh: float = Field(description="Costo del kWh en pesos")
    dias_ano: float = Field(300, description="Días de operación al año")
    carga: float = Field(0.75, description="Factor de carga real, 0 a 1")
    precio_motor: float | None = Field(None, description="Precio del motor nuevo, para el payback")


def _calcular_ahorro(a: AhorroArgs, memoria: SessionMemory) -> ToolOutput:
    try:
        r = motores.calcular_ahorro(
            potencia_kw=a.potencia_kw,
            eficiencia_vieja=a.eficiencia_vieja,
            eficiencia_nueva=a.eficiencia_nueva,
            horas_dia=a.horas_dia,
            dias_ano=a.dias_ano,
            tarifa_kwh=a.tarifa_kwh,
            carga=a.carga,
            precio_motor=a.precio_motor,
        )
    except ValueError as e:
        return ToolOutput(result=None, uncertainty=str(e))

    memoria.guardar("tarifa_kwh", a.tarifa_kwh, origen="calcular_ahorro")
    memoria.guardar("horas_dia", a.horas_dia, origen="calcular_ahorro")

    return ToolOutput(
        result=r.como_dict(),
        sources=[],
        uncertainty=(
            "El ahorro sale de las dos eficiencias y de los datos de operación que "
            "diste; el precio del motor no está en el catálogo de WEG (venden por "
            "distribuidor), así que el payback usa el precio que ingresaste."
            if a.precio_motor
            else "Sin precio del motor no puedo darte el payback, solo el ahorro."
        ),
    )


# ---------------------------------------------------------------------------
# Registro
# ---------------------------------------------------------------------------


def registrar_dominio(reg: Registro, corpus: Corpus, memoria: SessionMemory) -> Registro:
    """Agrega las herramientas de motores al registro base. Devuelve el mismo registro."""

    reg.registrar(
        Tool(
            nombre="registrar_placa",
            descripcion=(
                "Registra los datos que leíste en la foto de la placa y los VALIDA con "
                "física de motores a 60 Hz. Llámala SIEMPRE que el usuario mande una "
                "foto, antes de buscar nada. Si devuelve incoherencia, no calcules: "
                "pregúntale al usuario."
            ),
            args_model=PlacaArgs,
            fn=lambda a: _registrar_placa(a, memoria),
            es_conocimiento=False,
            usa_modelo=False,
        )
    )
    reg.registrar(
        Tool(
            nombre="buscar_motor_equivalente",
            descripcion=(
                "Busca en el catálogo WEG cargado el motor que corresponde a unas "
                "especificaciones, y devuelve la cita con documento y página. Úsala "
                "antes de nombrar cualquier referencia de producto."
            ),
            args_model=BuscarMotorArgs,
            fn=lambda a: _buscar_motor(a, corpus),
            es_conocimiento=True,
            usa_modelo=False,
        )
    )
    reg.registrar(
        Tool(
            nombre="calcular_ahorro",
            descripcion=(
                "Calcula el ahorro anual en kWh y pesos, el CO2 evitado y el payback "
                "de reemplazar un motor por uno más eficiente. NUNCA hagas esta cuenta "
                "tú: llama a esta herramienta."
            ),
            args_model=AhorroArgs,
            fn=lambda a: _calcular_ahorro(a, memoria),
            es_conocimiento=False,
            usa_modelo=False,
        )
    )
    return reg
