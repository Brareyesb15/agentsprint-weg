"""Herramientas de dominio: motores WEG. Se registran sobre el registro base.

Reparto a propósito — es el dato del pitch:

    registrar_placa           NO usa el modelo (valida con física)
    calcular_ahorro           NO usa el modelo (aritmética)
    buscar_motor_equivalente  NO usa el modelo (parsea la tabla, filtra y cita la FILA)
    buscar_conocimiento       NO usa el modelo   } del registro base
    leer_documento            NO usa el modelo   }

Lo único que hace el modelo es LEER la foto y REDACTAR. Todo lo que se puede
equivocar con consecuencias —una cuenta, un cruce de catálogo, una validación—
es Python. "El modelo no hace la cuenta" es literalmente cierto acá.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from agent import motores, tablas
from agent.conversacion import Conversacion
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
    clase_eficiencia: str = Field(
        "IE3",
        description="Clase de eficiencia buscada: IE1, IE2, IE3 o IE4. Para un "
        "reemplazo que ahorre energía, usa IE3.",
    )
    extra: str = Field("", description="Cualquier otro término del catálogo a buscar")


def _es_otra_frecuencia(seccion: str) -> bool:
    """¿El título de esta página dice explícitamente una frecuencia que no es la nuestra?"""
    s = seccion.lower().replace(" ", "")
    nuestra = f"{motores.FRECUENCIA_HZ}hz"
    return "hz" in s and nuestra not in s


def _buscar_motor(a: BuscarMotorArgs, corpus: Corpus) -> ToolOutput:
    # PRIMERO la tabla, y solo si no hay tabla se cae a la búsqueda léxica. El orden
    # importa: la selección por filas recorre el catálogo ENTERO y decide con la
    # frecuencia y la clase de cada fila, mientras que la léxica solo rankea páginas
    # por parecido de texto. Cuando la léxica no encontraba nada devolvía "no hay
    # nada en el catálogo" antes de que la tabla pudiera opinar — y la tabla sí sabía
    # la respuesta.
    filas = tablas.filas_del_corpus(corpus)
    if filas and (a.potencia_hp or a.polos or a.frame):
        return _elegir_fila(a, filas)

    # La frecuencia va SIEMPRE, aunque el modelo no la pida. El catálogo trae las
    # mismas potencias en tablas de 50 Hz y de 60 Hz, y sin este término la búsqueda
    # las mezcla: en la primera prueba con la placa real ofreció un IE3 de 50 Hz,
    # que en Colombia no aplica a ninguna placa.
    partes = [f"{motores.FRECUENCIA_HZ} Hz", a.clase_eficiencia]
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

    # Filtro DURO de frecuencia, no un peso. El catálogo trae las mismas potencias
    # en tablas de 50 Hz y de 60 Hz, y en Colombia la de 50 Hz no aplica a ninguna
    # placa: no es "menos relevante", es incorrecta. Un peso blando no alcanzaba —
    # medido: la tabla de 50 Hz le seguía ganando a la de 60 Hz.
    golpes = [
        (f, s)
        for f, s in corpus.buscar(consulta, k=14)
        if not _es_otra_frecuencia(f.section)
    ][:4]
    if not golpes:
        return ToolOutput(
            result=[],
            uncertainty=(
                f"no hay nada en el catálogo cargado para '{consulta}'. "
                "Puede que el corpus no tenga ese producto: no lo inventes, dilo."
            ),
        )

    # Sin tabla parseable o sin criterios que comparar no hay nada que verificar:
    # se cita a nivel de página, como antes, y se dice que la cita es de página.
    sources = [
        frag.como_source(corpus.lineas_relevantes(frag, consulta)) for frag, _ in golpes
    ]
    return ToolOutput(
        result=[
            {"doc": s.doc, "seccion": s.section, "pagina": s.page, "texto": s.snippet}
            for s in sources
        ],
        sources=sources,
        uncertainty=(
            "cita a nivel de PÁGINA, no de fila: no pude aislar el motor en la tabla. "
            "Los valores de esta página pertenecen a muchos motores distintos, así que "
            "no atribuyas a un motor cifras que no puedas ubicar en su propia fila."
        ),
    )


def _elegir_fila(a: BuscarMotorArgs, filas: list[tablas.FilaMotor]) -> ToolOutput:
    """Selecciona la fila que cumple los criterios y REPORTA si los cumple.

    Devolver la fila y no la página es lo que le da sentido al check del guard: la
    evidencia pasa de 1.712 números de la página a los ~20 del motor citado, así que
    mezclar cifras de dos motores deja de validar.
    """
    # En dos pasos a propósito. Primero se acota el universo a las filas que de
    # verdad pueden sostener la recomendación (la frecuencia del país y la clase
    # pedida); recién sobre ese universo se busca la potencia. Así el "más cercano"
    # del caso sin resultados sale de la tabla correcta y no de un IE1 de 50 Hz.
    universo, exigido_base = tablas.seleccionar(
        filas,
        clase_eficiencia=a.clase_eficiencia,
        frecuencia_hz=motores.FRECUENCIA_HZ,
    )
    candidatas, exigido_potencia = tablas.seleccionar(
        universo, potencia_hp=a.potencia_hp, polos=a.polos, carcasa=a.frame
    )
    exigido = exigido_base + exigido_potencia

    if candidatas:
        elegidas = candidatas[:3]
        return ToolOutput(
            result={
                "solicitado": exigido,
                "cumple": True,
                "motores": [f.como_dict() for f in elegidas],
            },
            sources=[f.como_source() for f in elegidas],
        )

    # Nada cumple. En vez de cerrar con un "no existe", se recorre el RESTO del
    # catálogo soltando una restricción por vez: casi siempre la opción existe en
    # otra clase de eficiencia o con otro número de polos. Se le muestran al usuario
    # y se le PREGUNTA cuál puede ceder, que es como se llega a un valor acertado sin
    # que el agente decida por él.
    pedido = " + ".join(exigido) if exigido else "los criterios dados"
    opciones = tablas.alternativas(
        filas,
        potencia_hp=a.potencia_hp,
        polos=a.polos,
        carcasa=a.frame,
        clase_eficiencia=a.clase_eficiencia,
        frecuencia_hz=motores.FRECUENCIA_HZ,
    )

    sources = [fila.como_source() for _, _, elegidas in opciones for fila in elegidas]
    caminos = [
        {
            "si_cambias": criterio,
            "a": variantes,
            "motores": [f.como_dict() for f in elegidas],
        }
        for criterio, variantes, elegidas in opciones
    ]

    if not caminos:
        return ToolOutput(
            result={"solicitado": exigido, "cumple": False, "motores": [], "alternativas": []},
            uncertainty=(
                f"NINGÚN motor cumple {pedido}, y tampoco aparece nada soltando una "
                "sola restricción: no está en el catálogo. Dilo, no ofrezcas un "
                "sustituto como si cumpliera."
            ),
        )

    resumen = "; ".join(f"cambiando {c} a {v}" for c, v, _ in opciones)
    return ToolOutput(
        result={
            "solicitado": exigido,
            "cumple": False,
            "motores": [],
            "alternativas": caminos,
        },
        sources=sources,
        uncertainty=(
            f"NINGÚN motor cumple {pedido}. En el resto del catálogo sí hay opciones "
            f"si se mueve UNA restricción: {resumen}. Muéstrale esas alternativas al "
            "usuario, di claramente en qué se apartan de lo que pidió, y PREGÚNTALE "
            "cuál restricción puede ceder antes de recomendar ninguna. No elijas por él."
        ),
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

    resultado = r.como_dict()
    # La procedencia del precio va en el RESULTADO, no en `uncertainty`. Antes iba
    # como incertidumbre y el turno salía marcado INCIERTO aunque el cálculo fuera
    # perfecto: el agente abría la respuesta disculpándose por el precio en vez de
    # decir "sí vale la pena, se paga en 30 meses". `uncertainty` queda para cuando
    # de verdad falta algo.
    if a.precio_motor:
        resultado["nota_precio"] = (
            "el payback usa el precio que ingresó el usuario; WEG vende por "
            "distribuidor y no publica precios en el catálogo"
        )
    return ToolOutput(
        result=resultado,
        sources=[],
        uncertainty=(
            None
            if a.precio_motor
            else "Sin precio del motor solo puedo dar el ahorro, no el payback. Pídelo."
        ),
    )


# ---------------------------------------------------------------------------
# Registro
# ---------------------------------------------------------------------------


class NuevaBusquedaArgs(BaseModel):
    confirmado: bool = Field(
        description="True SOLO si el usuario ya confirmó que quiere empezar de cero. "
        "Si no se lo has preguntado todavía, no llames a esta herramienta: pregúntale."
    )
    motivo: str = Field("", description="Qué dijo el usuario que indica que es otro motor")


def _nueva_busqueda(
    a: NuevaBusquedaArgs, memoria: SessionMemory, conversacion: Conversacion
) -> ToolOutput:
    """Borra los datos del motor anterior. El borrado lo hace Python, no el prompt.

    Un "olvida lo anterior" metido en el prompt no borra nada: los hechos siguen
    inyectados en el sistema y el agente los sigue viendo. Acá se vacían de verdad,
    y como es una herramienta, el borrado sale en el panel de trazas en vez de ser
    un cambio invisible de estado.
    """
    if not a.confirmado:
        return ToolOutput(
            result={"borrado": False},
            uncertainty=(
                "No borré nada: primero pregúntale al usuario si es una búsqueda NUEVA "
                "o si seguimos con el motor que ya veníamos trabajando. Perder los "
                "datos que ya dio sin confirmar es peor que preguntar de más."
            ),
        )

    anteriores = memoria.como_dict()
    for clave in list(anteriores):
        memoria.olvidar(clave)
    descartados = conversacion.reiniciar()

    return ToolOutput(
        result={
            "borrado": True,
            "hechos_descartados": sorted(anteriores),
            "mensajes_descartados": descartados,
            "motivo": a.motivo,
        },
    )


def registrar_dominio(
    reg: Registro,
    corpus: Corpus,
    memoria: SessionMemory,
    conversacion: Conversacion | None = None,
) -> Registro:
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
    conv = conversacion if conversacion is not None else Conversacion()
    reg.registrar(
        Tool(
            nombre="iniciar_nueva_busqueda",
            descripcion=(
                "Descarta los datos del motor que se venía trabajando y empieza de "
                "cero. Llámala cuando el usuario indique que ahora se trata de OTRO "
                "motor y ya te haya CONFIRMADO que es una búsqueda nueva. Si no lo "
                "confirmó, pregúntale primero: no borres datos por tu cuenta."
            ),
            args_model=NuevaBusquedaArgs,
            fn=lambda a: _nueva_busqueda(a, memoria, conv),
            es_conocimiento=False,
            usa_modelo=False,
        )
    )
    return reg
