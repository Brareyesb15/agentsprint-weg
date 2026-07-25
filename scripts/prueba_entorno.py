"""Prueba REAL del entorno — la que exige el checklist del evento.

No es un "hola mundo": verifica las tres cosas de las que depende el sábado.
Cada persona del equipo corre esto en SU máquina con SU key:

    .venv\\Scripts\\python.exe scripts/prueba_entorno.py

Qué verifica:
  1. Qué modelos existen de verdad para tu key (los Flash están en preview).
  2. Texto.
  3. Visión (imagen generada al vuelo, no hace falta traer una foto).
  4. Function calling con tool_config en modo ANY — el mecanismo que fuerza
     al modelo a consultar el conocimiento en vez de responder de memoria.
"""

from __future__ import annotations

import io
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types
from PIL import Image, ImageDraw

RAIZ = Path(__file__).resolve().parents[1]
load_dotenv(RAIZ / ".env")

CANDIDATOS = [
    "gemini-3.6-flash",
    "gemini-3-flash-preview",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-2.5-flash",
]

ok_global = True


def titulo(t: str) -> None:
    print(f"\n{'=' * 62}\n{t}\n{'=' * 62}")


def bien(m: str) -> None:
    print(f"  [OK]    {m}")


def mal(m: str) -> None:
    global ok_global
    ok_global = False
    print(f"  [FALLA] {m}")


def placa_de_prueba() -> bytes:
    """Imagen sintética tipo placa de equipo, para probar visión sin traer foto."""
    img = Image.new("RGB", (520, 300), "white")
    d = ImageDraw.Draw(img)
    d.rectangle([8, 8, 512, 292], outline="black", width=4)
    lineas = [
        "MODELO  XT-4408",
        "TENSION  24 V DC",
        "CORRIENTE  0,25 A",
        "FRECUENCIA  60 Hz",
        "PROTECCION  IP67",
    ]
    y = 45
    for ln in lineas:
        d.text((40, y), ln, fill="black")
        y += 45
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def main() -> int:
    key = os.getenv("GOOGLE_API_KEY_1")
    modelo = os.getenv("MODEL_NAME")

    titulo("0. Configuración")
    if not key:
        mal("GOOGLE_API_KEY_1 vacía en .env. Copia .env.example a .env y llénala.")
        return 1
    bien(f"key cargada desde .env ({key[:6]}...{key[-4:]}, {len(key)} caracteres)")
    if not modelo:
        mal("MODEL_NAME vacío en .env")
        return 1
    bien(f"MODEL_NAME = {modelo}   (leído del .env, no del código)")

    client = genai.Client(api_key=key)

    # ---------------------------------------------------------------- modelos
    titulo("1. Modelos que existen DE VERDAD para esta key")
    disponibles: set[str] = set()
    try:
        for m in client.models.list():
            nombre = (m.name or "").replace("models/", "")
            disponibles.add(nombre)
        flash = sorted(n for n in disponibles if "flash" in n)
        bien(f"{len(disponibles)} modelos visibles; {len(flash)} Flash")
        for n in flash[:14]:
            marca = " <-- el del .env" if n == modelo else ""
            print(f"          {n}{marca}")
    except Exception as e:
        mal(f"no se pudo listar modelos: {type(e).__name__}: {e}")

    if disponibles and modelo not in disponibles:
        mal(f"'{modelo}' NO está disponible para esta key")
        alt = next((c for c in CANDIDATOS if c in disponibles), None)
        if alt:
            print(f"          -> usa MODEL_NAME={alt} en el .env")
            modelo = alt
            print(f"          (sigo la prueba con {alt})")
        else:
            return 1
    elif disponibles:
        bien(f"'{modelo}' está disponible")

    # ----------------------------------------------------------------- texto
    titulo("2. Llamada de texto")
    try:
        r = client.models.generate_content(
            model=modelo,
            contents="Responde solo con la palabra: FUNCIONA",
        )
        txt = (r.text or "").strip()
        bien(f"respondió: {txt!r}")
        if r.usage_metadata:
            u = r.usage_metadata
            print(f"          tokens: entrada={u.prompt_token_count} salida={u.candidates_token_count}")
    except Exception as e:
        mal(f"{type(e).__name__}: {e}")

    # ---------------------------------------------------------------- visión
    titulo("3. Visión — imagen tipo placa")
    png = placa_de_prueba()
    print(f"  imagen generada: {len(png) / 1024:.1f} KB, 520x300 px")
    try:
        r = client.models.generate_content(
            model=modelo,
            contents=[
                types.Part.from_bytes(data=png, mime_type="image/png"),
                "Lee esta placa y devuelve SOLO los pares campo: valor, uno por línea.",
            ],
        )
        txt = (r.text or "").strip()
        bien("el modelo leyó la imagen")
        for ln in txt.splitlines():
            if ln.strip():
                print(f"          | {ln.strip()}")
        aciertos = sum(t in txt for t in ("XT-4408", "24", "0,25", "60", "IP67"))
        if aciertos >= 4:
            bien(f"extrajo {aciertos}/5 de los datos sembrados en la imagen")
        else:
            mal(f"solo extrajo {aciertos}/5 datos — visión poco confiable con este modelo")
        if r.usage_metadata:
            print(f"          tokens de entrada con imagen: {r.usage_metadata.prompt_token_count}")
    except Exception as e:
        mal(f"{type(e).__name__}: {e}")

    # ------------------------------------------------- function calling / ANY
    titulo("4. Function calling con tool_config = ANY (forzar consulta)")
    herramienta = types.Tool(
        function_declarations=[
            types.FunctionDeclaration(
                name="buscar_en_catalogo",
                description=(
                    "Busca una referencia en el catálogo oficial y devuelve la "
                    "especificación con su cita. Úsala SIEMPRE antes de afirmar "
                    "cualquier dato de un producto."
                ),
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "referencia": types.Schema(
                            type=types.Type.STRING, description="La referencia del producto"
                        ),
                        "motivo": types.Schema(
                            type=types.Type.STRING,
                            description="Una frase corta en español: por qué haces esta búsqueda",
                        ),
                    },
                    required=["referencia", "motivo"],
                ),
            )
        ]
    )

    # La pregunta trampa: un modelo sin forzado tiende a inventar la respuesta.
    pregunta = "¿Qué grado de protección tiene la referencia XT-4408?"

    for etiqueta, modo in (
        ("AUTO (el modelo decide)", types.FunctionCallingConfigMode.AUTO),
        ("ANY  (obligado a usar herramienta)", types.FunctionCallingConfigMode.ANY),
    ):
        try:
            cfg = types.GenerateContentConfig(
                tools=[herramienta],
                tool_config=types.ToolConfig(
                    function_calling_config=types.FunctionCallingConfig(mode=modo)
                ),
            )
            r = client.models.generate_content(model=modelo, contents=pregunta, config=cfg)
            llamadas = [
                p.function_call
                for p in (r.candidates[0].content.parts or [])
                if getattr(p, "function_call", None)
            ]
            if llamadas:
                fc = llamadas[0]
                args = dict(fc.args or {})
                bien(f"{etiqueta}: llamó a {fc.name}({args})")
                if "motivo" in args:
                    print(f"          motivo que dio el modelo: {args['motivo']!r}")
            else:
                texto = (r.text or "").strip()[:90]
                if modo == types.FunctionCallingConfigMode.ANY:
                    mal(f"{etiqueta}: NO llamó herramienta. Respondió: {texto!r}")
                else:
                    print(f"  [nota]  {etiqueta}: respondió de memoria -> {texto!r}")
                    print("          (justo el fallo que el guard de citas tiene que atrapar)")
        except Exception as e:
            mal(f"{etiqueta}: {type(e).__name__}: {e}")

    # -------------------------------------------------------------- veredicto
    titulo("VEREDICTO")
    if ok_global:
        print("  Entorno LISTO. Modelo verificado:", modelo)
    else:
        print("  Hay fallas arriba. Revisa las líneas [FALLA].")
    return 0 if ok_global else 1


if __name__ == "__main__":
    sys.exit(main())
