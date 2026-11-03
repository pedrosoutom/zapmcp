"""Gera unlock/ZapMCP.iconset (PNGs) para o iconutil montar o ZapMCP.icns: balão de conversa com um cadeado."""

import sys
from pathlib import Path

from PIL import Image, ImageDraw

FUNDO, BALAO, CADEADO = (30, 41, 59), (255, 255, 255), (30, 41, 59)


def desenhar(tamanho: int) -> Image.Image:
    s = tamanho
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, s - 1, s - 1), radius=int(s * 0.22), fill=FUNDO)
    # balão
    d.rounded_rectangle((s * 0.17, s * 0.22, s * 0.83, s * 0.70), radius=int(s * 0.16), fill=BALAO)
    d.polygon([(s * 0.30, s * 0.66), (s * 0.24, s * 0.84), (s * 0.44, s * 0.69)], fill=BALAO)
    # cadeado dentro do balão
    cx, cy = s * 0.50, s * 0.49
    w, h = s * 0.20, s * 0.15
    d.rounded_rectangle((cx - w / 2, cy - h * 0.1, cx + w / 2, cy + h), radius=int(s * 0.03), fill=CADEADO)
    arco = s * 0.07
    d.arc((cx - w * 0.36, cy - h * 0.95, cx + w * 0.36, cy + h * 0.25), 180, 360, fill=CADEADO, width=int(s * 0.035))
    d.ellipse((cx - arco * 0.3, cy + h * 0.25, cx + arco * 0.3, cy + h * 0.55), fill=BALAO)
    return img


def main(saida: Path) -> None:
    saida.mkdir(parents=True, exist_ok=True)
    for base in (16, 32, 128, 256, 512):
        desenhar(base).save(saida / f"icon_{base}x{base}.png")
        desenhar(base * 2).save(saida / f"icon_{base}x{base}@2x.png")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
