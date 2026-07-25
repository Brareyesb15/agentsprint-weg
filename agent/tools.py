"""Registro de herramientas con la firma que fija team/CONTRATOS.md.

Toda herramienta:
  entrada  -> argumentos validados con Pydantic + `motivo: str` obligatorio
  salida   -> { result, sources, uncertainty }

REGLA DURA: si una herramienta afirma algo del mundo, DEBE devolver de dónde lo
sacó en `sources`. Si no puede, devuelve `uncertainty` explicando por qué.

Gracias a eso el guard de citas funciona con CUALQUIER herramienta futura —
incluidas las de dominio que se escriban mañana cuando sepamos el reto.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

from pydantic import BaseModel, Field, ValidationError

from agent.corpus import Corpus
from agent.sources import Source

# Claves del JSON Schema de Pydantic que la API de Gemini no acepta.
_NO_SOPORTADAS = {"title", "default", "$defs", "additionalProperties", "examples", "const"}


@dataclass
class ToolOutput:
    result: Any
    sources: list[Source] = field(default_factory=list)
    uncertainty: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "result": self.result,
            "sources": [s.to_dict() for s in self.sources],
            "uncertainty": self.uncertainty,
        }

    def resumen(self) -> str:
        """Frase corta para `tool_result.summary` en el panel de trazas.

        Se proyecta en pantalla frente al jurado, así que no puede ser el `repr()`
        de una lista de diccionarios de Python cortado a media palabra.
        """
        if self.uncertainty:
            return f"sin dato firme: {self.uncertainty}"
        n = len(self.sources)
        cita = f" · {n} fuente{'s' if n != 1 else ''}" if n else " · sin fuentes"
        return _humanizar(self.result) + cita


def _humanizar(valor: Any, maximo: int = 90) -> str:
    """Convierte el resultado de una herramienta en algo legible a 3 metros."""
    if valor is None:
        return "sin resultado"
    if isinstance(valor, list):
        if not valor:
            return "0 resultados"
        cabeza = valor[0]
        if isinstance(cabeza, dict) and ("doc" in cabeza or "section" in cabeza):
            etiquetas = [
                " / ".join(str(v[k]) for k in ("doc", "section") if v.get(k))
                for v in valor
                if isinstance(v, dict)
            ]
            unicas = list(dict.fromkeys(e for e in etiquetas if e))
            return _cortar(f"{len(valor)} fragmento(s): " + "; ".join(unicas), maximo)
        return _cortar(f"{len(valor)} resultado(s): " + _humanizar(cabeza, maximo), maximo)
    if isinstance(valor, dict):
        pares = ", ".join(f"{k}={v}" for k, v in list(valor.items())[:4])
        return _cortar(pares, maximo)
    return _cortar(str(valor), maximo)


def _cortar(texto: str, maximo: int) -> str:
    """Corta en la última frontera de palabra, no a media palabra."""
    texto = " ".join(texto.split())
    if len(texto) <= maximo:
        return texto
    recortado = texto[:maximo]
    corte = recortado.rfind(" ")
    return (recortado[:corte] if corte > maximo // 2 else recortado).rstrip(" ,;:") + "…"


@dataclass
class Tool:
    nombre: str
    descripcion: str
    args_model: type[BaseModel]
    fn: Callable[..., ToolOutput]
    es_conocimiento: bool = False
    usa_modelo: bool = False

    def declaracion(self) -> dict[str, Any]:
        """Declaración en el formato que espera `types.FunctionDeclaration`."""
        esquema = _limpiar_schema(_resolver_refs(self.args_model.model_json_schema()))
        propiedades = esquema.setdefault("properties", {})
        propiedades["motivo"] = {
            "type": "string",
            "description": (
                "UNA frase corta en español explicando por qué llamas esta "
                "herramienta ahora. Se muestra al usuario en el panel de trazas."
            ),
        }
        requeridos = set(esquema.get("required", []))
        requeridos.add("motivo")
        esquema["required"] = sorted(requeridos)
        return {
            "name": self.nombre,
            "description": self.descripcion,
            "parameters": esquema,
        }


def _resolver_refs(esquema: dict[str, Any], profundidad: int = 0) -> dict[str, Any]:
    """Reemplaza cada `$ref` por la definición a la que apunta, y luego borra `$defs`.

    Esto NO es cosmético. Pydantic saca a `$defs` todo lo que sea un Enum o un modelo
    anidado y deja un `$ref` en su lugar. Borrar `$defs` sin resolver los `$ref`
    (que es lo que se hacía antes) produce `{"medida": {"$ref": "#/$defs/Sub"}}`
    apuntando al vacío: la API responde 400 de esquema inválido.

    Cuándo muerde: en la PRIMERA herramienta de dominio que use un Enum o un
    BaseModel anidado — o sea, mañana, en vivo, con el reto en la mano. `BuscarArgs`
    y `LeerArgs` son planas y por eso nunca lo destaparon.
    """
    defs = esquema.get("$defs", {})

    def caminar(nodo: Any, nivel: int) -> Any:
        if nivel > 12:  # corta referencias circulares en vez de colgarse
            return {"type": "string"}
        if isinstance(nodo, dict):
            if "$ref" in nodo:
                nombre = str(nodo["$ref"]).split("/")[-1]
                destino = defs.get(nombre)
                if destino is None:
                    # Degradación honesta: string libre antes que un $ref roto.
                    return {"type": "string"}
                resto = {k: v for k, v in nodo.items() if k != "$ref"}
                return caminar({**destino, **resto}, nivel + 1)
            return {k: caminar(v, nivel + 1) for k, v in nodo.items()}
        if isinstance(nodo, list):
            return [caminar(v, nivel + 1) for v in nodo]
        return nodo

    resuelto = caminar(esquema, profundidad)
    resuelto.pop("$defs", None)
    return resuelto


def _limpiar_schema(esquema: Any) -> Any:
    """Quita del JSON Schema de Pydantic lo que la API de Gemini rechaza.

    `const` NO se borra: se traduce a `enum` de un solo valor. Borrarlo convertía un
    `Literal["estricto"]` en un string libre, el modelo mandaba cualquier cosa,
    Pydantic la rechazaba y se quemaba una llamada de cuota para nada.
    """
    if isinstance(esquema, dict):
        limpio = {
            k: _limpiar_schema(v)
            for k, v in esquema.items()
            if k not in _NO_SOPORTADAS
        }
        if "const" in esquema and "enum" not in limpio:
            limpio["enum"] = [esquema["const"]]
        return limpio
    if isinstance(esquema, list):
        return [_limpiar_schema(v) for v in esquema]
    return esquema


class Registro:
    """Las herramientas disponibles en un turno."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def registrar(self, tool: Tool) -> Tool:
        if tool.nombre in self._tools:
            raise ValueError(f"herramienta duplicada: {tool.nombre}")
        self._tools[tool.nombre] = tool
        return tool

    def obtener(self, nombre: str) -> Tool | None:
        return self._tools.get(nombre)

    def nombres(self) -> list[str]:
        return sorted(self._tools)

    def de_conocimiento(self) -> list[str]:
        return sorted(n for n, t in self._tools.items() if t.es_conocimiento)

    def declaraciones(self) -> list[dict[str, Any]]:
        return [t.declaracion() for t in self._tools.values()]

    def cuentas(self) -> tuple[int, int]:
        """(deterministas, con modelo) — el dato del pitch: "6 de 8 no usan el modelo"."""
        con_modelo = sum(1 for t in self._tools.values() if t.usa_modelo)
        return len(self._tools) - con_modelo, con_modelo

    def ejecutar(self, nombre: str, args: dict[str, Any]) -> tuple[ToolOutput, int]:
        """Valida, ejecuta y cronometra. Devuelve (salida, milisegundos).

        Nunca lanza por culpa de argumentos malos del modelo: devuelve un
        ToolOutput con `uncertainty`, que es información útil para el loop
        (y se ve en el panel) en vez de un stacktrace que tumba el turno.
        """
        inicio = time.perf_counter()
        tool = self._tools.get(nombre)
        if tool is None:
            ms = int((time.perf_counter() - inicio) * 1000)
            return ToolOutput(result=None, uncertainty=f"no existe la herramienta '{nombre}'"), ms

        limpios = {k: v for k, v in args.items() if k != "motivo"}
        try:
            validados = tool.args_model(**limpios)
        except ValidationError as e:
            ms = int((time.perf_counter() - inicio) * 1000)
            return (
                ToolOutput(
                    result=None,
                    uncertainty=f"argumentos inválidos para '{nombre}': {e.error_count()} error(es)",
                ),
                ms,
            )

        try:
            salida = tool.fn(validados)
        except Exception as e:  # noqa: BLE001 - un fallo de tool no debe tumbar el turno
            salida = ToolOutput(result=None, uncertainty=f"la herramienta falló: {e}")

        return salida, int((time.perf_counter() - inicio) * 1000)


# ---------------------------------------------------------------------------
# Herramientas de conocimiento — independientes del reto
# ---------------------------------------------------------------------------


class BuscarArgs(BaseModel):
    consulta: str = Field(description="Qué buscar, en palabras del dominio.")
    k: int = Field(3, ge=1, le=8, description="Cuántos fragmentos traer.")


class LeerArgs(BaseModel):
    doc: str = Field(description="Nombre del archivo, tal como lo devolvió la búsqueda.")
    section: str | None = Field(
        None, description="Sección exacta. Si se omite, trae el documento completo."
    )


def construir_registro(corpus: Corpus) -> Registro:
    """Registro base: solo conocimiento. Las de dominio se agregan mañana."""
    reg = Registro()

    def buscar(a: BuscarArgs) -> ToolOutput:
        golpes = corpus.buscar(a.consulta, k=a.k)
        if not golpes:
            return ToolOutput(
                result=[],
                uncertainty=f"no hay nada en el corpus sobre '{a.consulta}'",
            )
        sources = [
            frag.como_source(corpus.lineas_relevantes(frag, a.consulta))
            for frag, _ in golpes
        ]
        return ToolOutput(
            result=[
                {"doc": s.doc, "section": s.section, "texto": s.snippet} for s in sources
            ],
            sources=sources,
        )

    def leer(a: LeerArgs) -> ToolOutput:
        frags = corpus.leer(a.doc, a.section)
        if not frags:
            return ToolOutput(
                result=None,
                uncertainty=f"no encontré '{a.doc}'" + (f" sección '{a.section}'" if a.section else ""),
            )
        # Tope de 3 fragmentos, y no es tacañería: sin sección, esto devolvía el
        # catálogo ENTERO (72 páginas ≈ 40k tokens) al historial. Medido en vivo:
        # el contexto del cierre pasó de 6k a 72k tokens y el modelo dejó de
        # responder. Si hay más fragmentos, se dice cuáles quedaron fuera para que
        # el modelo pida la sección exacta.
        recorte = frags[:3]
        sources = [f.como_source() for f in recorte]
        incierto = None
        if len(frags) > len(recorte):
            resto = sorted({f"{f.section} (pág. {f.page})" for f in frags[3:]})
            incierto = (
                f"hay {len(frags)} fragmentos y solo devolví 3. Los demás: "
                + "; ".join(resto[:8])
                + ". Pide la sección exacta si necesitas otro."
            )
        return ToolOutput(
            result=[{"section": s.section, "texto": s.snippet} for s in sources],
            sources=sources,
            uncertainty=incierto,
        )

    reg.registrar(
        Tool(
            nombre="buscar_conocimiento",
            descripcion=(
                "Busca en la documentación oficial cargada en el repo y devuelve "
                "fragmentos con su cita (documento y sección). Úsala SIEMPRE antes "
                "de afirmar cualquier dato de producto."
            ),
            args_model=BuscarArgs,
            fn=buscar,
            es_conocimiento=True,
            usa_modelo=False,
        )
    )
    reg.registrar(
        Tool(
            nombre="leer_documento",
            descripcion=(
                "Lee una sección completa de un documento antes de afirmar algo. "
                "Úsala cuando la búsqueda devolvió un fragmento y necesitas el contexto entero."
            ),
            args_model=LeerArgs,
            fn=leer,
            es_conocimiento=True,
            usa_modelo=False,
        )
    )
    return reg


__all__ = [
    "BuscarArgs",
    "LeerArgs",
    "Registro",
    "Tool",
    "ToolOutput",
    "construir_registro",
]
