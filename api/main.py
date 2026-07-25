"""API oficial de la demo. Mínima a propósito: tres endpoints y nada más.

Correr:
    .venv\\Scripts\\python.exe -m uvicorn api.main:app --port 8000

Si `ui/index.html` existe, se sirve en http://localhost:8000 — mismo origen,
o sea CERO CORS que depurar. El front de Robinson puede igual desarrollarse
aparte en el 5173: el middleware de CORS queda abierto para eso.

Contrato (team/CONTRATOS.md):
    POST /chat    { session_id, message, image?: base64 }  -> SSE de eventos
    POST /upload  multipart file                           -> { image_id }
    GET  /health                                           -> { ok: true }
"""

from __future__ import annotations

import asyncio
import base64
import uuid
from pathlib import Path

from fastapi import FastAPI, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from agent.events import Emitter, Event
from agent.loop import Agente
from evals.agente_real import construir

RAIZ = Path(__file__).resolve().parents[1]

app = FastAPI(title="AgentSprint · motores WEG")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

# Una sesión = un agente con SU memoria (la placa registrada en el turno 1 se usa
# en el turno 3). El lock serializa turnos de la misma sesión: el Emitter tiene un
# solo sink y dos turnos simultáneos lo pisarían.
_sesiones: dict[str, tuple[Agente, Emitter, asyncio.Lock]] = {}
_imagenes: dict[str, bytes] = {}


def _sesion(session_id: str) -> tuple[Agente, Emitter, asyncio.Lock]:
    if session_id not in _sesiones:
        emitter = Emitter()
        _sesiones[session_id] = (construir(emitter), emitter, asyncio.Lock())
    return _sesiones[session_id]


class ChatBody(BaseModel):
    session_id: str = "demo"
    message: str
    image: str | None = None      # base64 crudo o data URL
    image_id: str | None = None   # alternativa: lo que devolvió /upload


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.post("/upload")
async def upload(file: UploadFile) -> dict:
    image_id = uuid.uuid4().hex[:12]
    _imagenes[image_id] = await file.read()
    return {"image_id": image_id}


@app.post("/chat")
async def chat(body: ChatBody) -> StreamingResponse:
    agente, emitter, lock = _sesion(body.session_id)

    imagen: bytes | None = None
    if body.image:
        b64 = body.image.split(",", 1)[1] if body.image.startswith("data:") else body.image
        imagen = base64.b64decode(b64)
    elif body.image_id:
        imagen = _imagenes.get(body.image_id)

    cola: asyncio.Queue[Event | None] = asyncio.Queue()
    loop = asyncio.get_running_loop()
    # El agente corre en un hilo (sus llamadas a Gemini son bloqueantes); cada
    # evento salta al loop async por la cola y sale por el SSE al instante.
    emitter._sink = lambda ev: loop.call_soon_threadsafe(cola.put_nowait, ev)

    async def correr() -> None:
        try:
            await asyncio.to_thread(agente.responder, body.message, imagen)
        finally:
            cola.put_nowait(None)

    async def emitir():
        async with lock:
            tarea = asyncio.create_task(correr())
            while True:
                ev = await cola.get()
                if ev is None:
                    break
                yield ev.to_sse()
            await tarea

    return StreamingResponse(
        emitir(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# Al final, para que /chat, /upload y /health ganen la ruta.
if (RAIZ / "ui" / "index.html").exists():
    app.mount("/", StaticFiles(directory=RAIZ / "ui", html=True), name="ui")
