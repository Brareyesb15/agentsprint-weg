"""Armazón del eval: toma una lista de preguntas, se las hace al agente y verifica
automáticamente que la respuesta traiga la cita esperada.

Por qué vale tanto: casi ningún equipo de hackathon lleva evaluación. Correrla en
vivo convierte "confíen en nosotros" en "mírenlo ustedes".

Por qué está separado de las preguntas: el armazón no depende del reto y se escribe
hoy; las preguntas sí dependen y se escriben mañana. Preparar las dos hoy es
arriesgarse a tirar las preguntas a la basura.

`correr()` recibe un `responder` inyectado, así que el armazón se prueba sin API key.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from agent.events import Emitter
from agent.sources import Cantidad, Source, coincide, extraer_cantidades

RAIZ = Path(__file__).resolve().parents[1]
DIR_SETS = Path(__file__).parent / "sets"
DIR_RUNS = Path(__file__).parent / "runs"

# Detección de rechazo. Se probó contra rechazos reales de Gemini en español y una
# lista de frases literales fallaba en 12 de 14 casos: el modelo escribe "La
# documentación proporcionada no especifica el precio", "no se indica", "no consta",
# y a veces con negritas de markdown en medio. Así que es un patrón: negación +
# verbo de disponibilidad, sobre el texto ya normalizado.
_RE_RECHAZO = re.compile(
    r"\bno\s+(?:lo\s+|la\s+|le\s+|me\s+|se\s+)?"
    r"(?:est[aá]|aparec|figur|encuentr|encontr|teng|disping|dispong|pued|s[eé]\b|"
    r"especific|indic|inclu|contien|proporcion|mencion|hay\b|exist|cuent|dic|"
    r"detall|const|precis|report)"
)
_FRASES_RECHAZO_EXTRA = (
    "fuera de alcance",
    "fuera del alcance",
    "sin informacion",
    "sin información",
    "no disponible en",
)


@dataclass
class Pregunta:
    id: str
    pregunta: str
    espera_doc: str | None = None          # substring del nombre del documento citado
    espera_valores: list[str] = field(default_factory=list)  # p.ej. ["24 V"]
    debe_rechazar: bool = False            # trampa: no está en el corpus
    no_debe_decir: list[str] = field(default_factory=list)  # valores prohibidos en la respuesta
    control_negativo: bool = False         # esta pregunta DEBE fallar; si pasa, el guard se rompió
    nota: str = ""
    respuesta_simulada: str | None = None  # solo para el modo --fake
    consulta_simulada: str | None = None   # solo para el modo --fake

    @classmethod
    def desde_dict(cls, d: dict[str, Any]) -> "Pregunta":
        return cls(**{k: v for k, v in d.items() if k in cls.__annotations__})


@dataclass
class Resultado:
    pregunta: Pregunta
    respuesta: str
    aprobada: bool
    motivos: list[str]
    ms: int
    verify_ok: bool | None = None
    verify_detail: str = ""
    docs_citados: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.pregunta.id,
            "pregunta": self.pregunta.pregunta,
            "aprobada": self.aprobada,
            "motivos": self.motivos,
            "respuesta": self.respuesta,
            "ms": self.ms,
            "verify_ok": self.verify_ok,
            "verify_detail": self.verify_detail,
            "docs_citados": self.docs_citados,
        }


@dataclass
class Corrida:
    set_nombre: str
    iniciada: str
    resultados: list[Resultado] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.resultados)

    @property
    def aprobadas(self) -> int:
        return sum(1 for r in self.resultados if r.aprobada)

    def to_dict(self) -> dict[str, Any]:
        return {
            "set": self.set_nombre,
            "iniciada": self.iniciada,
            "aprobadas": self.aprobadas,
            "total": self.total,
            "resultados": [r.to_dict() for r in self.resultados],
        }

    def tabla(self) -> str:
        """Salida para consola. Legible a 3 metros si se proyecta."""
        lineas = [
            f"EVAL '{self.set_nombre}' · {self.iniciada}",
            "-" * 72,
        ]
        for r in self.resultados:
            marca = "PASA" if r.aprobada else "FALLA"
            lineas.append(f"[{marca:5}] {r.pregunta.id:14} {r.pregunta.pregunta[:44]:44} {r.ms:5} ms")
            for m in r.motivos:
                lineas.append(f"          -> {m}")
        lineas.append("-" * 72)
        lineas.append(f"RESULTADO: {self.aprobadas}/{self.total} aprobadas")
        return "\n".join(lineas)

    def guardar(self, directorio: Path | None = None) -> Path:
        d = directorio or DIR_RUNS
        d.mkdir(parents=True, exist_ok=True)
        sello = self.iniciada.replace(":", "-").replace(" ", "_")
        ruta = d / f"{self.set_nombre}_{sello}.json"
        ruta.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return ruta


# ---------------------------------------------------------------------------
# Carga de sets
# ---------------------------------------------------------------------------


def cargar_set(nombre: str) -> list[Pregunta]:
    ruta = DIR_SETS / f"{nombre}.json"
    if not ruta.exists():
        disponibles = ", ".join(p.stem for p in DIR_SETS.glob("*.json")) or "(ninguno)"
        raise FileNotFoundError(f"no existe el set '{nombre}'. Disponibles: {disponibles}")
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    return [Pregunta.desde_dict(d) for d in datos["preguntas"]]


# ---------------------------------------------------------------------------
# Corrida
# ---------------------------------------------------------------------------


def correr(
    preguntas: Sequence[Pregunta],
    responder: Callable[[Pregunta], Any],
    *,
    set_nombre: str = "sin-nombre",
    emitter: Emitter | None = None,
) -> Corrida:
    """`responder(pregunta)` devuelve algo con `.texto`, `.sources`, `.verify`, `.bloqueada`.

    Es decir: un `agent.loop.RespuestaFinal`. Se inyecta para que el armazón se pueda
    probar sin API key y para que la API pueda reusarlo en `POST /eval/run`.
    """
    corrida = Corrida(
        set_nombre=set_nombre,
        iniciada=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )

    for p in preguntas:
        inicio = time.perf_counter()
        try:
            resp = responder(p)
        except Exception as e:  # noqa: BLE001 - una pregunta que revienta no tumba la corrida
            ms = int((time.perf_counter() - inicio) * 1000)
            corrida.resultados.append(
                Resultado(
                    pregunta=p, respuesta="", aprobada=False,
                    motivos=[f"excepción: {type(e).__name__}: {e}"], ms=ms,
                )
            )
            if emitter is not None:
                emitter.error("eval", f"{p.id}: {e}", recoverable=True)
            continue

        ms = int((time.perf_counter() - inicio) * 1000)
        corrida.resultados.append(_invertir_si_control(_calificar(p, resp, ms)))

    return corrida


def _invertir_si_control(r: Resultado) -> Resultado:
    """Un control negativo aprueba cuando FALLA.

    Sin esto, una corrida sana reportaría 3/4 y saldría con código de error, y
    nadie sabría si el 1 que falta es el control o un bug de verdad.
    """
    if not r.pregunta.control_negativo:
        return r
    # Se exige que haya fallado POR EL GUARD (verify_ok is False), no por cualquier
    # motivo. Antes, con el guard desactivado la pregunta seguía fallando por
    # "no dijo los valores esperados" y el control aprobaba igual: no controlaba nada.
    fallo_como_debia = (not r.aprobada) and r.verify_ok is False
    r.motivos = (
        ["control negativo: falló como se esperaba (" + "; ".join(r.motivos) + ")"]
        if fallo_como_debia
        else ["CONTROL NEGATIVO APROBÓ: el guard dejó pasar un valor sin respaldo"]
    )
    r.aprobada = fallo_como_debia
    return r


def _calificar(p: Pregunta, resp: Any, ms: int) -> Resultado:
    texto: str = getattr(resp, "texto", "") or ""
    sources: list[Source] = list(getattr(resp, "sources", []) or [])
    verify = getattr(resp, "verify", None)
    bloqueada: bool = bool(getattr(resp, "bloqueada", False))

    motivos: list[str] = []
    docs = sorted({s.doc for s in sources})

    # --- caso trampa: la respuesta correcta es rechazar --------------------
    if p.debe_rechazar:
        rechazo = bloqueada or _parece_rechazo(texto)
        if not rechazo:
            motivos.append("debía rechazar y en cambio afirmó algo")
        # Una muletilla no salva una alucinación: "cuesta 1.200.000 COP, aunque no
        # puedo confirmar la fecha" contiene un rechazo Y afirma el dato prohibido.
        dichos = _normalizar(texto)
        prohibidos = [v for v in p.no_debe_decir if _normalizar(v) in dichos]
        if prohibidos:
            motivos.append("dijo valores prohibidos: " + ", ".join(prohibidos))
        return Resultado(
            pregunta=p,
            respuesta=texto,
            aprobada=rechazo and not prohibidos,
            motivos=motivos,
            ms=ms,
            verify_ok=getattr(verify, "ok", None),
            verify_detail=getattr(verify, "detail", ""),
            docs_citados=docs,
        )

    # --- caso normal --------------------------------------------------------
    if bloqueada:
        motivos.append("el guard bloqueó la respuesta")

    if verify is not None and not verify.ok:
        motivos.append(f"verify falló: {verify.detail}")

    if p.espera_doc:
        # Se comprueba contra los RESPALDOS del guard (las fuentes que de verdad
        # sostuvieron un valor), no contra todo lo que la búsqueda trajo. Antes,
        # cambiar espera_doc a un documento que solo apareció en los resultados de
        # la búsqueda daba verde aunque la respuesta se apoyara en otro.
        respaldos = list(getattr(verify, "respaldos", []) or [])
        donde = respaldos if respaldos else [s.doc for s in sources]
        if not any(p.espera_doc.lower() in d.lower() for d in donde):
            etiqueta = "se apoyó en" if respaldos else "citó"
            motivos.append(
                f"no se apoyó en '{p.espera_doc}' ({etiqueta}: {', '.join(donde) or 'nada'})"
            )

    faltantes = _valores_faltantes(texto, p.espera_valores)
    if faltantes:
        motivos.append("no dijo los valores esperados: " + ", ".join(faltantes))

    if not texto.strip():
        motivos.append("respuesta vacía")

    return Resultado(
        pregunta=p, respuesta=texto, aprobada=not motivos, motivos=motivos, ms=ms,
        verify_ok=getattr(verify, "ok", None),
        verify_detail=getattr(verify, "detail", ""),
        docs_citados=docs,
    )


def _normalizar(texto: str) -> str:
    """Quita el marcado y colapsa espacios: 'no está en la **documentación**' tiene
    que leerse igual que sin negritas."""
    limpio = re.sub(r"[*_`~]+", "", texto.lower())
    return re.sub(r"\s+", " ", limpio)


def _parece_rechazo(texto: str) -> bool:
    norm = _normalizar(texto)
    if _RE_RECHAZO.search(norm):
        return True
    return any(f in norm for f in _FRASES_RECHAZO_EXTRA)


def _valores_faltantes(texto: str, esperados: Iterable[str]) -> list[str]:
    """Compara con la misma normalización del guard: '3,7 kW' cuenta como '5 HP'."""
    dichos = extraer_cantidades(texto)
    faltan: list[str] = []
    for crudo in esperados:
        objetivo = extraer_cantidades(crudo)
        if not objetivo:
            if crudo.lower() not in texto.lower():
                faltan.append(crudo)
            continue
        blanco: Cantidad = objetivo[0]
        if not any(coincide(d, blanco, 0.02) for d in dichos):
            faltan.append(crudo)
    return faltan


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Corre un set de preguntas contra el agente.")
    ap.add_argument("--set", default="juguete", help="nombre del set en evals/sets/")
    ap.add_argument(
        "--fake",
        action="store_true",
        help="usa el agente simulado (corpus y guard REALES, modelo simulado). No requiere API key.",
    )
    ap.add_argument("--guardar", action="store_true", help="guarda el JSON de la corrida")
    args = ap.parse_args()

    preguntas = cargar_set(args.set)

    if args.fake:
        from evals.agente_simulado import responder_simulado as responder
    else:
        from evals.agente_real import responder_real as responder

    corrida = correr(preguntas, responder, set_nombre=args.set)
    print(corrida.tabla())
    if args.guardar:
        print(f"\nguardado en: {corrida.guardar()}")
    return 0 if corrida.aprobadas == corrida.total else 1


if __name__ == "__main__":
    raise SystemExit(_main())
