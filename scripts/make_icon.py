"""Gera o ícone do aplicativo em vários tamanhos."""

from __future__ import annotations

import io
import struct
from pathlib import Path

from PIL import Image, ImageDraw


def _draw(size: int) -> Image.Image:
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    margin = max(1, size // 16)
    radius = max(2, size // 6)
    draw.rounded_rectangle(
        (margin, margin, size - margin - 1, size - margin - 1),
        radius=radius,
        fill=(23, 26, 31, 255),
    )
    cyan = (61, 222, 203, 255)
    blue = (47, 111, 237, 255)
    center = size / 2
    radius_outer = size * 0.28
    draw.ellipse(
        (center - radius_outer, center - radius_outer, center + radius_outer, center + radius_outer),
        outline=cyan,
        width=max(2, size // 16),
    )
    radius_inner = size * 0.12
    draw.ellipse(
        (center - radius_inner, center - radius_inner, center + radius_inner, center + radius_inner),
        fill=blue,
    )
    bar_top = int(size * 0.72)
    bar_height = max(2, size // 18)
    gap = max(2, size // 14)
    width = int(size * 0.34)
    left = int(center - width / 2)
    for index in range(3):
        top = bar_top + index * (bar_height + gap // 2)
        inset = index * max(1, size // 28)
        draw.rounded_rectangle(
            (left + inset, top, left + width - inset, top + bar_height),
            radius=bar_height // 2,
            fill=cyan,
        )
    return image


def _save_ico(destination: Path, images: list[Image.Image]) -> None:
    """ICO com PNG por tamanho. O save() do Pillow gravou só o quadro de 16 px."""
    payloads: list[bytes] = []
    for image in images:
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        payloads.append(buffer.getvalue())
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries = bytearray()
    for image, payload in zip(images, payloads):
        width = 0 if image.width >= 256 else image.width
        height = 0 if image.height >= 256 else image.height
        entries += struct.pack("<BBBBHHII", width, height, 0, 0, 1, 32, len(payload), offset)
        offset += len(payload)
    destination.write_bytes(header + bytes(entries) + b"".join(payloads))


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    destination = root / "assets" / "icon.ico"
    destination.parent.mkdir(parents=True, exist_ok=True)
    sizes = [16, 24, 32, 48, 64, 128, 256]
    _save_ico(destination, [_draw(size) for size in sizes])


if __name__ == "__main__":
    main()
