"""PLAN B — servidor mínimo para que la demo exista aunque `api/` no esté listo.

⚠ NO ES EL CARRIL DE NADIE. Esto lo escribió Brandon como respaldo.
Si Robinson entrega `api/main.py` + `ui/index.html`, **este directorio se borra**.
No construyas sobre esto: es desechable a propósito. Ver `plan_b/README.md`.

Correr:
    .venv\\Scripts\\python.exe -m uvicorn plan_b.servidor:app --port 8010

Después abrir http://localhost:8010

Va en el puerto **8010**, no en el 8000, justamente para que pueda convivir con el
servidor de Robinson corriendo al mismo tiempo sin pelearse el puerto.
"""

from __future__ import annotations

import asyncio
import base64
import queue
import threading
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from agent import config as cfg_mod
from agent.corpus import Corpus
from agent.dominio import registrar_dominio
from agent.events import Emitter
from agent.keys import Rotador
from agent.llm import Cliente
from agent.loop import Agente
from agent.memory import SessionMemory
from agent.tools import construir_registro

AQUI = Path(__file__).parent
app = FastAPI(title="AgentSprint · plan B")

# El corpus y el cliente se construyen UNA vez: parsear un PDF de 72 páginas en cada
# request costaría segundos de demo. La memoria y el emitter sí son por conversación.
_cfg = None
_corpus: Corpus | None = None
_cliente: Cliente | None = None
_memorias: dict[str, SessionMemory] = {}
_lock = threading.Lock()


def _base():
    global _cfg, _corpus, _cliente
    with _lock:
        if _corpus is None:
            _cfg = cfg_mod.cargar()
            _cfg.exigir_keys()
            _corpus = Corpus.desde_directorio(_cfg.data_dir)
            if not _corpus.fragmentos:
                raise RuntimeError(
                    f"El corpus de {_cfg.data_dir} está vacío: no hay nada que citar."
                )
            _cliente = Cliente(Rotador(_cfg.api_keys), _cfg.cadena_de_modelos)
    return _cfg, _corpus, _cliente


class ChatIn(BaseModel):
    session_id: str = "demo"
    message: str
    image: str | None = None


@app.get("/health")
def health() -> dict[str, Any]:
    try:
        cfg, corpus, cliente = _base()
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:200]}
    return {
        "ok": True,
        "fragmentos": len(corpus.fragmentos),
        "documentos": sorted({f.doc for f in corpus.fragmentos}),
        "modelo": cliente.modelo_en_uso,
        "avisos": corpus.avisos,
    }


@app.post("/chat")
async def chat(req: ChatIn) -> StreamingResponse:
    """SSE con los eventos de team/CONTRATOS.md, tal cual.

    El agente es SÍNCRONO y bloqueante, así que corre en un hilo y empuja los eventos
    a una cola; el generador async la drena. Si se llamara directo, el `await` no
    cedería el control y el front no vería nada hasta el final — que es justo lo que
    hace que la espera se sienta como un cuelgue.
    """
    cfg, corpus, cliente = _base()
    cola: queue.Queue = queue.Queue()
    FIN = object()

    imagen = None
    if req.image:
        crudo = req.image.split(",", 1)[1] if req.image.startswith("data:") else req.image
        imagen = base64.b64decode(crudo)

    def trabajar() -> None:
        try:
            em = Emitter(sink=cola.put)
            memoria = _memorias.setdefault(req.session_id, SessionMemory(em))
            memoria._emitter = em  # el emitter cambia por request, la memoria no
            registro = registrar_dominio(construir_registro(corpus), corpus, memoria)
            agente = Agente(
                cliente=cliente,
                registro=registro,
                emitter=em,
                memoria=memoria,
                tolerancia=cfg.guard_tolerancia,
                lado_maximo_imagen=cfg.image_max_side,
            )
            agente.responder(req.message, imagen=imagen)
        except Exception as e:  # noqa: BLE001
            # El agente ya captura lo suyo; esto cubre fallos al construirlo.
            cola.put(Emitter().error("servidor", str(e)[:300], recoverable=False))
        finally:
            cola.put(FIN)

    threading.Thread(target=trabajar, daemon=True).start()

    async def generar():
        while True:
            ev = await asyncio.to_thread(cola.get)
            if ev is FIN:
                break
            yield ev.to_sse()

    return StreamingResponse(
        generar(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# Al FINAL: montar la raíz antes de declarar las rutas se las comería.
# Servir el HTML desde el mismo origen es lo que elimina el CORS por completo.
app.mount("/", StaticFiles(directory=str(AQUI), html=True), name="ui")
