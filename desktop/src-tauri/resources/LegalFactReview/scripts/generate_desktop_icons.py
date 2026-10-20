from __future__ import annotations

import struct
import zlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ICONS_DIR = ROOT / "desktop" / "src-tauri" / "icons"


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + kind
        + data
        + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    )


def build_png(size: int) -> bytes:
    rows = []
    for y in range(size):
        row = bytearray([0])
        for x in range(size):
            in_border = x < 3 or y < 3 or x >= size - 3 or y >= size - 3
            in_badge = size * 0.22 < x < size * 0.78 and size * 0.18 < y < size * 0.82
            in_line = abs((y - size * 0.62) - (x - size * 0.20) * 0.35) < max(1, size * 0.025)
            if in_border:
                color = (25, 70, 130, 255)
            elif in_line:
                color = (255, 255, 255, 255)
            elif in_badge:
                color = (45, 110, 190, 255)
            else:
                color = (230, 238, 247, 255)
            row.extend(color)
        rows.append(bytes(row))
    raw = b"".join(rows)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
        + _png_chunk(b"IDAT", zlib.compress(raw, 9))
        + _png_chunk(b"IEND", b"")
    )


def build_ico(png_entries: list[tuple[int, bytes]]) -> bytes:
    header = struct.pack("<HHH", 0, 1, len(png_entries))
    entries = []
    offset = 6 + len(png_entries) * 16
    payloads = []
    for size, png in png_entries:
        width = 0 if size >= 256 else size
        height = 0 if size >= 256 else size
        entries.append(struct.pack("<BBBBHHII", width, height, 0, 0, 1, 32, len(png), offset))
        payloads.append(png)
        offset += len(png)
    return header + b"".join(entries) + b"".join(payloads)


def generate_icons(icons_dir: Path = ICONS_DIR) -> list[Path]:
    icons_dir.mkdir(parents=True, exist_ok=True)
    png_32 = build_png(32)
    png_128 = build_png(128)
    png_256 = build_png(256)
    files = {
        "32x32.png": png_32,
        "128x128.png": png_128,
        "128x128@2x.png": png_256,
        "icon.png": png_256,
        "icon.ico": build_ico([(32, png_32), (128, png_128), (256, png_256)]),
    }
    written = []
    for name, data in files.items():
        path = icons_dir / name
        path.write_bytes(data)
        written.append(path)
    return written


if __name__ == "__main__":
    for path in generate_icons():
        print(path)
