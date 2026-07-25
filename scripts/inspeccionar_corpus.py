"""Muestra QUÉ se indexó del corpus. Cero llamadas a la API.

Córrelo cada vez que agregues documentos a `data/`, ANTES de confiar en el agente:

    .venv\\Scripts\\python.exe scripts/inspeccionar_corpus.py
    .venv\\Scripts\\python.exe scripts/inspeccionar_corpus.py "distancia de deteccion"

Sin argumento lista el inventario. Con un argumento, hace la búsqueda real y te
muestra el snippet EXACTO que el agente citaría — que es la forma más rápida de
descubrir que un PDF era una imagen, o que la cita apunta al documento equivocado.
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from agent import config as cfg_mod  # noqa: E402
from agent.corpus import Corpus      # noqa: E402


def main() -> int:
    cfg = cfg_mod.cargar()
    corpus = Corpus.desde_directorio(cfg.data_dir)

    print(f"DATA_DIR = {cfg.data_dir}")
    print(f"fragmentos indexados: {len(corpus.fragmentos)}")

    if corpus.avisos:
        print("\nAVISOS DEL CARGADOR:")
        for a in corpus.avisos:
            print(f"  ! {a}")

    if not corpus.fragmentos:
        print(
            "\nCORPUS VACÍO. El agente va a bloquear TODA respuesta con un número,\n"
            "y va a tener razón. Se indexan .md y .pdf, recursivamente.\n"
            "Si pusiste PDFs y salen 0 fragmentos, probablemente sean de imágenes."
        )
        return 1

    print("\nINVENTARIO por documento:")
    por_doc: dict[str, list] = {}
    for f in corpus.fragmentos:
        por_doc.setdefault(f.doc, []).append(f)
    for doc, frags in sorted(por_doc.items()):
        paginas = sorted({f.page for f in frags if f.page is not None})
        rango = f" · páginas {paginas[0]}-{paginas[-1]}" if paginas else " · sin paginación"
        print(f"  {doc}  ({len(frags)} fragmentos{rango})")
        for f in frags[:3]:
            print(f"      - {f.section[:64] or '(sin sección)'}")
        if len(frags) > 3:
            print(f"      … {len(frags) - 3} más")

    consulta = " ".join(sys.argv[1:]).strip()
    if not consulta:
        print("\nPasa una consulta como argumento para ver qué citaría el agente.")
        return 0

    print(f"\nBÚSQUEDA: {consulta!r}")
    golpes = corpus.buscar(consulta, k=3)
    if not golpes:
        print("  sin resultados — el agente diría que no está en la documentación")
        return 0
    for pos, (frag, puntaje) in enumerate(golpes, start=1):
        src = frag.como_source(corpus.lineas_relevantes(frag, consulta))
        print(f"\n  #{pos}  puntaje {puntaje:.2f}  ->  {src.etiqueta()}")
        for linea in src.snippet.splitlines()[:4]:
            print(f"        | {linea.strip()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
