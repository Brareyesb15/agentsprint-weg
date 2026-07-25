"""Único módulo que conoce la API de Gemini.

Si Google renombra algo, se arregla acá y en ningún otro archivo.

Verificado contra `google-genai 2.14.0` instalado en este repo (24-jul-2026):
  - `client.models.generate_content` existe y acepta `tool_config`.
  - `client.interactions` TAMBIÉN existe en esta versión. Se deja documentado pero
    no se usa: `generate_content` es la superficie donde `function_calling_config`
    está documentada, y no conviene apoyar el hito de grounding en la superficie
    nueva sin haberla probado.
  - `FunctionCallingConfigMode` expone cuatro modos: AUTO, ANY, NONE y VALIDATED.
    (Los documentos del equipo decían tres — VALIDATED no aparece en ellos.)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from google import genai
from google.genai import types

from agent.keys import Rotador

MODO_FORZAR = "ANY"    # obliga a llamar una herramienta: turno de consulta
MODO_LIBRE = "AUTO"    # deja redactar: turno de cierre
MODO_SIN_TOOLS = "NONE"


@dataclass
class LlamadaHerramienta:
    nombre: str
    args: dict[str, Any]

    @property
    def motivo(self) -> str:
        return str(self.args.get("motivo", "")).strip()


@dataclass
class Respuesta:
    texto: str = ""
    llamadas: list[LlamadaHerramienta] = field(default_factory=list)
    crudo: Any = None
    finish_reason: str = ""
    partes: int = 0
    tokens: str = ""
    contenido: Any = None
    """El `Content` TAL CUAL lo devolvió el modelo.

    Hay que devolver este objeto al historial sin tocarlo, no una reconstrucción.
    Gemini 3 firma sus turnos de function calling con un `thought_signature`, y si
    se manda de vuelta un Content armado a mano la API responde:
        400 INVALID_ARGUMENT — Function call is missing a thought_signature
    Verificado en vivo el 24-jul-2026 con gemini-3.6-flash.
    """

    @property
    def pidio_herramienta(self) -> bool:
        return bool(self.llamadas)


class Cliente:
    """Envoltura del SDK con rotación de keys Y de modelos.

    Lo de los modelos no es lujo: la cuota del tier gratis es **por proyecto y por
    modelo**. Verificado en vivo el 24-jul-2026 con una key real:

        gemini-3.6-flash        limit: 20 requests/día  (se agotó en una prueba)
        gemini-3-flash-preview  cuota propia, seguía disponible
        gemini-2.0-flash        limit: 0 (no está en el tier gratis)

    Con 20/día por modelo, un turno del agente (que gasta entre 3 y 6 llamadas)
    agota un modelo en cuatro preguntas. Así que cuando las keys se agotan para un
    modelo, se pasa al siguiente de la cadena en vez de morir.
    """

    def __init__(self, rotador: Rotador, model_name: str | list[str]) -> None:
        modelos = [model_name] if isinstance(model_name, str) else list(model_name)
        modelos = [m for m in modelos if m]
        if not modelos:
            raise ValueError("sin modelos: MODEL_NAME tiene que venir del .env")
        self.rotador = rotador
        self.modelos = modelos
        self.model_name = modelos[0]
        self.modelo_en_uso = modelos[0]
        self.degradaciones: list[str] = []
        self._cache: dict[str, genai.Client] = {}

    def _cliente(self, key: str) -> genai.Client:
        if key not in self._cache:
            self._cache[key] = genai.Client(api_key=key)
        return self._cache[key]

    # -- API pública -------------------------------------------------------

    def generar(
        self,
        contenidos: list[Any],
        *,
        sistema: str | None = None,
        declaraciones: list[dict[str, Any]] | None = None,
        modo: str = MODO_LIBRE,
        temperatura: float | None = None,
        modelo: str | None = None,
    ) -> Respuesta:
        config = self._config(sistema, declaraciones, modo, temperatura)
        candidatos = [modelo] if modelo else self._desde_el_actual()
        ultimo: BaseException | None = None

        for nombre_modelo in candidatos:

            def llamar(key: str, m: str = nombre_modelo) -> Any:
                return self._cliente(key).models.generate_content(
                    model=m, contents=contenidos, config=config
                )

            try:
                bruto = self.rotador.ejecutar(llamar)
            except RuntimeError as e:
                # Todas las keys agotadas PARA ESTE MODELO: probar el siguiente.
                ultimo = e
                if nombre_modelo != candidatos[-1]:
                    self.degradaciones.append(nombre_modelo)
                continue
            self.modelo_en_uso = nombre_modelo
            return _parsear(bruto)

        raise RuntimeError(
            f"Sin cuota en ninguno de los modelos {candidatos} con "
            f"{len(self.rotador.keys)} key(s). Último error: {ultimo}"
        ) from ultimo

    def _desde_el_actual(self) -> list[str]:
        """La cadena empezando por el modelo que ya funcionó, para no reintentar
        uno que se sabe agotado en cada llamada."""
        if self.modelo_en_uso in self.modelos:
            i = self.modelos.index(self.modelo_en_uso)
            return self.modelos[i:] + self.modelos[:i]
        return list(self.modelos)

    def estado(self) -> str:
        """Línea para el panel: qué modelo se está usando y si hubo degradación."""
        linea = f"modelo: {self.modelo_en_uso}"
        if self.degradaciones:
            linea += f" (cuota agotada en: {', '.join(dict.fromkeys(self.degradaciones))})"
        return f"{linea} · {self.rotador.estado()}"

    def _config(
        self,
        sistema: str | None,
        declaraciones: list[dict[str, Any]] | None,
        modo: str,
        temperatura: float | None,
    ) -> types.GenerateContentConfig:
        # La temperatura NO se manda salvo que alguien la pida explícita. Íbamos con
        # 0.0 "para determinismo" y la guía de Gemini 3 advierte exactamente contra
        # eso: en los modelos con razonamiento, bajarla produce respuestas VACÍAS y
        # loops. Coincide con lo observado en vivo: el cierre del turno de ROI volvía
        # sin contenido dos veces seguidas. El determinismo del proyecto no viene de
        # la temperatura: viene de que las cuentas las hace Python.
        kwargs: dict[str, Any] = {}
        if temperatura is not None:
            kwargs["temperature"] = temperatura
        if sistema:
            kwargs["system_instruction"] = sistema
        if declaraciones:
            kwargs["tools"] = [types.Tool(function_declarations=declaraciones)]
            kwargs["tool_config"] = types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(mode=modo)
            )
        return types.GenerateContentConfig(**kwargs)


# ---------------------------------------------------------------------------
# Construcción de contenidos
# ---------------------------------------------------------------------------


def texto_usuario(texto: str) -> types.Content:
    return types.Content(role="user", parts=[types.Part(text=texto)])


def texto_modelo(texto: str) -> types.Content:
    return types.Content(role="model", parts=[types.Part(text=texto)])


def usuario_con_imagen(texto: str, imagen: bytes, mime: str = "image/jpeg") -> types.Content:
    return types.Content(
        role="user",
        parts=[
            types.Part(text=texto),
            types.Part(inline_data=types.Blob(mime_type=mime, data=imagen)),
        ],
    )


def respuesta_de_herramienta(nombre: str, salida: dict[str, Any]) -> types.Content:
    """El resultado de la herramienta, devuelto al modelo."""
    return types.Content(
        role="user",
        parts=[
            types.Part(
                function_response=types.FunctionResponse(name=nombre, response=salida)
            )
        ],
    )


def peticion_de_herramienta(llamadas: list[LlamadaHerramienta]) -> types.Content:
    """Reconstruye a mano el turno del modelo donde pidió las herramientas.

    ⚠ NO usar con Gemini 3 para continuar una conversación real: pierde el
    `thought_signature` y la API devuelve 400. Para eso está `Respuesta.contenido`.
    Esto queda solo para fixtures y tests donde no hay API de por medio.
    """
    return types.Content(
        role="model",
        parts=[
            types.Part(
                function_call=types.FunctionCall(name=l.nombre, args=l.args)
            )
            for l in llamadas
        ],
    )


# ---------------------------------------------------------------------------
# Parseo de la respuesta
# ---------------------------------------------------------------------------


def _parsear(bruto: Any) -> Respuesta:
    textos: list[str] = []
    llamadas: list[LlamadaHerramienta] = []
    contenido_original: Any = None

    candidatos = getattr(bruto, "candidates", None) or []
    for cand in candidatos:
        contenido = getattr(cand, "content", None)
        if contenido_original is None:
            contenido_original = contenido
        for parte in (getattr(contenido, "parts", None) or []):
            fc = getattr(parte, "function_call", None)
            if fc is not None and getattr(fc, "name", None):
                llamadas.append(
                    LlamadaHerramienta(nombre=fc.name, args=dict(fc.args or {}))
                )
                continue
            # Las partes con thought=True son el razonamiento del modelo, no la
            # respuesta: concatenarlas filtraría el borrador SIN verificar al texto
            # final. Se saltan.
            if getattr(parte, "thought", False):
                continue
            t = getattr(parte, "text", None)
            if t:
                textos.append(t)

    # `finish_reason` y el conteo de tokens son la única forma de saber POR QUÉ una
    # respuesta vino vacía: MAX_TOKENS (se gastó el presupuesto pensando), SAFETY,
    # RECITATION o simplemente ninguna parte de texto. Sin esto solo se ve el
    # síntoma y se depura a ciegas.
    razon = ""
    partes_vistas = 0
    if candidatos:
        fr = getattr(candidatos[0], "finish_reason", None)
        razon = getattr(fr, "name", None) or str(fr or "")
        contenido0 = getattr(candidatos[0], "content", None)
        partes_vistas = len(getattr(contenido0, "parts", None) or [])
    uso = getattr(bruto, "usage_metadata", None)

    return Respuesta(
        texto="".join(textos).strip(),
        llamadas=llamadas,
        crudo=bruto,
        contenido=contenido_original,
        finish_reason=razon,
        partes=partes_vistas,
        tokens=(
            f"in={getattr(uso, 'prompt_token_count', '?')} "
            f"out={getattr(uso, 'candidates_token_count', '?')} "
            f"think={getattr(uso, 'thoughts_token_count', '?')}"
            if uso
            else ""
        ),
    )
