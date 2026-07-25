"""Genera la placa de motor para la demo, con desgaste realista.

    .venv\\Scripts\\python.exe scripts/generar_placa.py

Por qué generarla y no bajar una de Google: los datos tienen que **cuadrar con el
catálogo que cargamos**. Una placa cualquiera de internet puede ser de 50 Hz, o de
una potencia que no está en el W22, y entonces el agente responde "no encontré" y
parece roto cuando el que está mal es el insumo.

Qué tiene esta placa, y por qué cada dato:

  10 HP / 7,5 kW   está en la tabla del W22 IE3 a 60 Hz (carcasa 132S)
  1750 RPM         a 60 Hz son 4 polos con 2,8% de deslizamiento -> la validación
                   física pasa. Si el modelo lee 17500, el agente repregunta.
  220/440 V        tensión estándar colombiana, doble
  26,2/13,1 A      cuadra con P = raiz3 x V x I x cosfi x eta, +-25%
  60 Hz            si fuera 50 Hz, ninguna tabla del catálogo aplicaría
  132S             la carcasa que permite el cruce directo con el W22
  SIN rendimiento  DELIBERADO: los motores viejos IE1 no lo traen. Ese hueco es lo
                   que obliga al agente a citar la norma en vez de inventar
  marca ficticia   no es WEG: es el motor VIEJO que se va a reemplazar
"""

from __future__ import annotations

import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

SALIDA = Path(__file__).resolve().parents[1] / "data" / "placa_demo.png"
ANCHO, ALTO = 1000, 640

DATOS = [
    ("MOTOR TRIFASICO DE INDUCCION", None),
    ("MOD.", "ELM-132S-4"),
    ("HP", "10        kW  7,5"),
    ("RPM", "1750"),
    ("V", "220 / 440"),
    ("A", "26,2 / 13,1"),
    ("Hz", "60"),
    ("CARCASA", "132S"),
    ("F.S.", "1,15"),
    ("AISL.", "F"),
    ("IP", "55"),
    ("AÑO", "2004"),
]


def _fuente(tam: int, negrita: bool = False):
    for nombre in (["arialbd.ttf", "consolab.ttf"] if negrita else ["arial.ttf", "consola.ttf"]):
        try:
            return ImageFont.truetype(nombre, tam)
        except OSError:
            continue
    return ImageFont.load_default()


def _fondo() -> Image.Image:
    """Aluminio con veta y suciedad."""
    img = Image.new("RGB", (ANCHO, ALTO), (168, 170, 166))
    px = img.load()
    for y in range(ALTO):
        for x in range(0, ANCHO, 2):
            v = random.randint(-14, 14) + int(10 * ((x / ANCHO) - 0.5))
            base = 168 + v
            px[x, y] = (max(0, min(255, base)), max(0, min(255, base + 2)), max(0, min(255, base - 2)))
            if x + 1 < ANCHO:
                px[x + 1, y] = px[x, y]
    return img.filter(ImageFilter.GaussianBlur(0.4))


def _grabado(d: ImageDraw.ImageDraw, xy, texto, fuente, fuerza=1):
    """Texto que parece troquelado: sombra clara abajo, texto oscuro encima."""
    x, y = xy
    d.text((x + fuerza, y + fuerza), texto, font=fuente, fill=(215, 216, 212))
    d.text((x, y), texto, font=fuente, fill=(48, 48, 50))


def main() -> int:
    random.seed(7)  # misma placa siempre: la demo tiene que ser repetible
    img = _fondo()
    d = ImageDraw.Draw(img)

    d.rectangle([16, 16, ANCHO - 16, ALTO - 16], outline=(120, 122, 118), width=3)
    for cx, cy in [(48, 48), (ANCHO - 48, 48), (48, ALTO - 48), (ANCHO - 48, ALTO - 48)]:
        d.ellipse([cx - 13, cy - 13, cx + 13, cy + 13], fill=(150, 152, 148), outline=(105, 107, 103), width=2)
        d.ellipse([cx - 6, cy - 6, cx + 4, cy + 4], fill=(186, 188, 184))

    _grabado(d, (95, 44), "ELECTROMEC", _fuente(46, True), 2)
    _grabado(d, (95, 100), DATOS[0][0], _fuente(21))
    d.line([95, 136, ANCHO - 95, 136], fill=(120, 122, 118), width=2)

    f_et, f_val = _fuente(24), _fuente(30, True)
    y = 164
    for i, (etiqueta, valor) in enumerate(DATOS[1:], start=1):
        col = 95 if i % 2 else 540
        if i % 2 == 0:
            pass
        _grabado(d, (col, y), etiqueta, f_et)
        if valor:
            _grabado(d, (col + 130, y - 4), valor, f_val)
        if i % 2 == 0:
            y += 62

    # Desgaste: rayones, manchas de grasa y una esquina más oscura.
    for _ in range(90):
        x1, y1 = random.randint(20, ANCHO - 20), random.randint(20, ALTO - 20)
        d.line([x1, y1, x1 + random.randint(-45, 45), y1 + random.randint(-7, 7)],
               fill=(random.randint(130, 200),) * 3, width=1)
    mancha = Image.new("L", (ANCHO, ALTO), 0)
    md = ImageDraw.Draw(mancha)
    for _ in range(7):
        cx, cy, r = random.randint(0, ANCHO), random.randint(0, ALTO), random.randint(60, 190)
        md.ellipse([cx - r, cy - r, cx + r, cy + r], fill=random.randint(18, 52))
    img = Image.composite(Image.new("RGB", img.size, (92, 88, 82)), img,
                          mancha.filter(ImageFilter.GaussianBlur(38)))

    # Foto de celular: rotación leve, desenfoque y luz despareja.
    img = img.rotate(-1.6, resample=Image.BICUBIC, expand=True, fillcolor=(40, 40, 42))
    img = img.filter(ImageFilter.GaussianBlur(0.7))
    luz = Image.new("L", img.size, 0)
    ld = ImageDraw.Draw(luz)
    ld.ellipse([-260, -190, img.width + 130, img.height + 240], fill=225)
    img = Image.composite(img, Image.new("RGB", img.size, (58, 58, 60)),
                          luz.filter(ImageFilter.GaussianBlur(150)))

    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    img.save(SALIDA, quality=88)
    print(f"placa generada: {SALIDA}  ({SALIDA.stat().st_size // 1024} KB, {img.width}x{img.height})")
    print("pruébala:  .venv\\Scripts\\python.exe scripts/chat.py \"lee esta placa y dime "
          "qué motor WEG la reemplaza\" data/placa_demo.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
