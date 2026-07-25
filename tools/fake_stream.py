"""Servidor de eventos FALSOS que siguen team/CONTRATOS.md al pie de la letra.

Para qué: que Robinson construya el panel de trazas HOY, sin esperar a que exista
el agente. El criterio de "listo" de los contratos es literalmente que el panel
pinte correctamente eventos falsos. Si funciona con datos inventados, mañana
funciona con los reales — porque el sobre es el mismo.

No es parte del producto. Es un andamio: se borra o se ignora el sábado.

Correr:
    .venv\\Scripts\\python.exe -m uvicorn tools.fake_stream:app --port 8000 --reload

Probar sin front:
    curl -N http://localhost:8000/chat
"""

from __future__ import annotations

import asyncio
import json

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from agent.events import Emitter
from agent.sources import Source

app = FastAPI(title="AgentSprint · emisor de eventos falsos")

# El front corre en otro puerto (5173), así que sin CORS el navegador bloquea el SSE.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

PAUSA = 0.45  # segundos entre eventos, para que se vea el movimiento en el panel


def guion() -> list[dict]:
    """Un turno completo con LOS OCHO tipos de evento, en orden realista."""
    em = Emitter()
    fuente = Source(
        doc="ficha_ZX-100.md",
        section="Sección 1 — Datos eléctricos",
        page=1,
        snippet="Tensión de alimentación: 24 V DC. Consumo máximo: 35 mA.",
    )

    em.thought("Voy a consultar la documentación antes de afirmar nada.")
    em.tool_call(
        "a1b2c3d4",
        "buscar_conocimiento",
        {"consulta": "tensión alimentación ZX-100", "k": 3},
        "El usuario pregunta por la tensión y no puedo responder de memoria.",
    )
    em.tool_result(
        "a1b2c3d4",
        "buscar_conocimiento",
        ok=True,
        ms=41,
        summary="1 fragmento · 1 fuente",
        sources=[fuente],
    )
    em.tool_call(
        "e5f6a7b8",
        "calcular_consumo",
        {"tension_v": 24, "corriente_ma": 35},
        "Calculo la potencia en código, no se la pregunto al modelo.",
    )
    em.tool_result(
        "e5f6a7b8", "calcular_consumo", ok=True, ms=1, summary="0,84 W · sin fuentes"
    )
    em.memory("producto_en_foco", "ZX-100")
    em.verify(ok=True, checked=3, confirmed=3, detail="3/3 valores confirmados en ficha_ZX-100.md, Sección 1 — Datos eléctricos, pág. 1")
    em.citation(fuente)
    for trozo in [
        "El ZX-100 se alimenta con ",
        "24 V DC y consume hasta 35 mA, ",
        "según ficha_ZX-100.md, sección 1. ",
        "Eso son 0,84 W, calculado en código.",
    ]:
        em.token(trozo)
    em.error(
        "demo",
        "este evento de error es de mentira, existe para que el panel tenga cómo pintarlo",
        recoverable=True,
    )
    return [e.to_dict() for e in em.historial]


async def _emitir():
    for evento in guion():
        yield f"data: {json.dumps(evento, ensure_ascii=False)}\n\n"
        await asyncio.sleep(PAUSA)


@app.get("/health")
@app.get("/")
def health() -> dict:
    return {"ok": True, "aviso": "emisor de eventos FALSOS, no es el agente"}


@app.get("/chat")
@app.post("/chat")
async def chat() -> StreamingResponse:
    return StreamingResponse(
        _emitir(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/eventos")
def eventos() -> list[dict]:
    """Todos los eventos de golpe, sin SSE. Útil para escribir el panel sin pelear
    con el streaming al principio."""
    return guion()
