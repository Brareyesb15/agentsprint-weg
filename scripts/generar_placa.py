"""Genera el juego de placas para la demo, con desgaste realista.

    .venv\\Scripts\\python.exe scripts/generar_placa.py

Salen a `demo/`, NO a `data/`. `data/` es el corpus que indexa el agente: meter ahí
una imagen de entrada ensucia el manifiesto de fuentes y confunde a cualquiera que
revise de dónde salen las citas.

Por qué generarlas y no bajarlas de Google: los datos tienen que **cuadrar con el
catálogo que cargamos**. Una placa cualquiera de internet puede ser de 50 Hz o de una
potencia que no está en el W22, y entonces el agente responde "no encontré" y parece
roto cuando el que está mal es el insumo.

Cuatro placas, cada una para probar una cosa distinta:

  placa_10hp.png    CAMINO FELIZ. 10 HP / 1750 rpm / 132S. Es la del pitch.
  placa_25hp.png    SEGUNDO CASO VÁLIDO. Demuestra que nada está cableado a mano.
  placa_ilegible.png  17500 rpm: imposible a 60 Hz. El validador la rechaza y el
                      agente REPREGUNTA en vez de calcular. Es el "sabe cuándo no sabe".
  placa_50hz.png    Motor europeo de 50 Hz / 1450 rpm. Ninguna tabla del catálogo
                    aplica: el agente tiene que decirlo, no aproximar.
"""

from __future__ import annotations

import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

SALIDA = Path(__file__).resolve().parents[1] / "demo"
ANCHO, ALTO = 1000, 640

PLACAS = [
    (
        "placa_10hp.png", "ELECTROMEC",
        [("MOD.", "ELM-132S-4"), ("HP", "10       kW  7,5"), ("RPM", "1750"),
         ("V", "220 / 440"), ("A", "26,2 / 13,1"), ("Hz", "60"),
         ("CARCASA", "132S"), ("F.S.", "1,15"), ("AISL.", "F"), ("IP", "55"),
         ("AÑO", "2004")],
    ),
    (
        "placa_25hp.png", "INDUMOTOR",
        [("MOD.", "IM-180M-4"), ("HP", "25       kW  18,5"), ("RPM", "1765"),
         ("V", "220 / 440"), ("A", "62,0 / 31,0"), ("Hz", "60"),
         ("CARCASA", "180M"), ("F.S.", "1,15"), ("AISL.", "F"), ("IP", "55"),
         ("AÑO", "2001")],
    ),
    (
        "placa_ilegible.png", "ELECTROMEC",
        [("MOD.", "ELM-132S-4"), ("HP", "10       kW  7,5"), ("RPM", "17500"),
         ("V", "220 / 440"), ("A", "26,2 / 13,1"), ("Hz", "60"),
         ("CARCASA", "132S"), ("F.S.", "1,15"), ("AISL.", "F"), ("IP", "55"),
         ("AÑO", "1998")],
    ),
    (
        "placa_50hz.png", "EUROMOT",
        [("MOD.", "EU-132S-4"), ("kW", "7,5      HP  10"), ("RPM", "1450"),
         ("V", "230 / 400"), ("A", "26,5 / 15,2"), ("Hz", "50"),
         ("CARCASA", "132S"), ("F.S.", "1,00"), ("AISL.", "F"), ("IP", "55"),
         ("AÑO", "2007")],
    ),
]


def _fuente(tam: int, negrita: bool = False):
    for n in (["arialbd.ttf", "consolab.ttf"] if negrita else ["arial.ttf", "consola.ttf"]):
        try:
            return ImageFont.truetype(n, tam)
        except OSError:
            continue
    return ImageFont.load_default()


def _fondo(rng: random.Random) -> Image.Image:
    img = Image.new("RGB", (ANCHO, ALTO), (168, 170, 166))
    px = img.load()
    for y in range(ALTO):
        for x in range(0, ANCHO, 2):
            base = 168 + rng.randint(-14, 14) + int(10 * ((x / ANCHO) - 0.5))
            c = (max(0, min(255, base)), max(0, min(255, base + 2)), max(0, min(255, base - 2)))
            px[x, y] = c
            if x + 1 < ANCHO:
                px[x + 1, y] = c
    return img.filter(ImageFilter.GaussianBlur(0.4))


def _grabado(d, xy, texto, fuente, fuerza=1):
    """Texto troquelado: sombra clara abajo, texto oscuro encima."""
    x, y = xy
    d.text((x + fuerza, y + fuerza), texto, font=fuente, fill=(215, 216, 212))
    d.text((x, y), texto, font=fuente, fill=(48, 48, 50))


def generar(nombre: str, marca: str, datos: list[tuple[str, str]], semilla: int) -> Path:
    rng = random.Random(semilla)  # misma placa siempre: la demo tiene que repetirse
    img = _fondo(rng)
    d = ImageDraw.Draw(img)

    d.rectangle([16, 16, ANCHO - 16, ALTO - 16], outline=(120, 122, 118), width=3)
    for cx, cy in [(48, 48), (ANCHO - 48, 48), (48, ALTO - 48), (ANCHO - 48, ALTO - 48)]:
        d.ellipse([cx - 13, cy - 13, cx + 13, cy + 13], fill=(150, 152, 148),
                  outline=(105, 107, 103), width=2)
        d.ellipse([cx - 6, cy - 6, cx + 4, cy + 4], fill=(186, 188, 184))

    _grabado(d, (95, 44), marca, _fuente(46, True), 2)
    _grabado(d, (95, 100), "MOTOR TRIFASICO DE INDUCCION", _fuente(21))
    d.line([95, 136, ANCHO - 95, 136], fill=(120, 122, 118), width=2)

    f_et, f_val = _fuente(24), _fuente(30, True)
    y = 164
    for i, (etiqueta, valor) in enumerate(datos):
        col = 95 if i % 2 == 0 else 540
        _grabado(d, (col, y), etiqueta, f_et)
        _grabado(d, (col + 130, y - 4), valor, f_val)
        if i % 2 == 1:
            y += 62

    for _ in range(90):  # rayones
        x1, y1 = rng.randint(20, ANCHO - 20), rng.randint(20, ALTO - 20)
        d.line([x1, y1, x1 + rng.randint(-45, 45), y1 + rng.randint(-7, 7)],
               fill=(rng.randint(130, 200),) * 3, width=1)

    mancha = Image.new("L", (ANCHO, ALTO), 0)  # grasa
    md = ImageDraw.Draw(mancha)
    for _ in range(7):
        cx, cy, r = rng.randint(0, ANCHO), rng.randint(0, ALTO), rng.randint(60, 190)
        md.ellipse([cx - r, cy - r, cx + r, cy + r], fill=rng.randint(18, 52))
    img = Image.composite(Image.new("RGB", img.size, (92, 88, 82)), img,
                          mancha.filter(ImageFilter.GaussianBlur(38)))

    # Foto de celular: rotación leve, desenfoque y luz despareja.
    img = img.rotate(rng.uniform(-2.2, 2.2), resample=Image.BICUBIC, expand=True,
                     fillcolor=(40, 40, 42))
    img = img.filter(ImageFilter.GaussianBlur(0.7))
    luz = Image.new("L", img.size, 0)
    ld = ImageDraw.Draw(luz)
    ld.ellipse([-260, -190, img.width + 130, img.height + 240], fill=225)
    img = Image.composite(img, Image.new("RGB", img.size, (58, 58, 60)),
                          luz.filter(ImageFilter.GaussianBlur(150)))

    SALIDA.mkdir(parents=True, exist_ok=True)
    ruta = SALIDA / nombre
    img.save(ruta, quality=88)
    return ruta


def main() -> int:
    for i, (nombre, marca, datos) in enumerate(PLACAS):
        r = generar(nombre, marca, datos, semilla=7 + i * 13)
        print(f"  {r.relative_to(SALIDA.parent)}  ({r.stat().st_size // 1024} KB)")
    print("\npruébalas:")
    print('  .venv\\Scripts\\python.exe scripts/chat.py "lee la placa y dime qué WEG '
          'la reemplaza" demo/placa_10hp.png')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
