"""Create a sample supplier till slip image for demos and testing.

Usage:  python scripts/make_demo_receipt.py [output.png]
"""
import sys
from datetime import date
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

LINES = [
    "KASI CASH & CARRY",
    "Soweto Wholesale",
    f"Date: {date.today():%d/%m/%Y}",
    "",
    "BREAD WHITE 700G 40 x 14.50     580.00",
    "MILK 1L 12 x 18.00              216.00",
    "COOLDRINK 2L 12 x 22.00         264.00",
    "SUGAR 2KG 6 x 38.00             228.00",
    "",
    "SUBTOTAL                       1288.00",
    "VAT INCL                        168.00",
    "TOTAL                          1288.00",
]


def main(out: str = "demo_receipt.png") -> Path:
    font = None
    for candidate in ["DejaVuSansMono.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
                      "C:/Windows/Fonts/consola.ttf", "/System/Library/Fonts/Menlo.ttc"]:
        try:
            font = ImageFont.truetype(candidate, 28)
            break
        except OSError:
            continue
    font = font or ImageFont.load_default()
    img = Image.new("RGB", (760, 60 + 44 * len(LINES)), "white")
    draw = ImageDraw.Draw(img)
    for i, line in enumerate(LINES):
        draw.text((30, 30 + i * 44), line, fill="black", font=font)
    path = Path(out)
    img.save(path)
    print(f"Saved {path.resolve()}")
    return path


if __name__ == "__main__":
    main(*sys.argv[1:2])
