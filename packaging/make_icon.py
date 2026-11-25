"""Genera packaging/icon.ico (quadrato blu con + − × ÷) usando solo la libreria standard."""
import math
import struct
import zlib
from pathlib import Path

BG = (29, 78, 216)
FG = (255, 255, 255)
STROKE = 0.04
ARM = 0.13
SS = 4  # campioni per lato di ogni pixel (antialiasing)


def seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


def glyph_shapes():
    segs, dots = [], []
    cx, cy = 0.30, 0.30  # +
    segs += [(cx - ARM, cy, cx + ARM, cy), (cx, cy - ARM, cx, cy + ARM)]
    cx, cy = 0.70, 0.30  # −
    segs += [(cx - ARM, cy, cx + ARM, cy)]
    cx, cy, d = 0.30, 0.70, ARM * 0.75  # ×
    segs += [(cx - d, cy - d, cx + d, cy + d), (cx - d, cy + d, cx + d, cy - d)]
    cx, cy = 0.70, 0.70  # ÷
    segs += [(cx - ARM, cy, cx + ARM, cy)]
    dots += [(cx, cy - 0.095), (cx, cy + 0.095)]
    return segs, dots


def inside_rounded_rect(x, y, m=0.03, r=0.2):
    if x < m or x > 1 - m or y < m or y > 1 - m:
        return False
    qx = min(x - m, 1 - m - x)
    qy = min(y - m, 1 - m - y)
    if qx >= r or qy >= r:
        return True
    return math.hypot(r - qx, r - qy) <= r


def render(size):
    segs, dots = glyph_shapes()
    rows = []
    for j in range(size):
        row = bytearray([0])  # filtro PNG "None"
        for i in range(size):
            bg = fg = 0
            for sj in range(SS):
                for si in range(SS):
                    x = (i + (si + 0.5) / SS) / size
                    y = (j + (sj + 0.5) / SS) / size
                    if not inside_rounded_rect(x, y):
                        continue
                    bg += 1
                    if (any(seg_dist(x, y, *s) <= STROKE for s in segs)
                            or any(math.hypot(x - dx, y - dy) <= STROKE * 1.25 for dx, dy in dots)):
                        fg += 1
            n = SS * SS
            if bg == 0:
                row += bytes(4)
                continue
            f = fg / bg
            rgb = [round(BG[k] * (1 - f) + FG[k] * f) for k in range(3)]
            row += bytes(rgb + [round(255 * bg / n)])
        rows.append(bytes(row))
    return png(size, b"".join(rows))


def png(size, raw):
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def ico(images):
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries, blobs = b"", b""
    for size, data in images:
        dim = 0 if size >= 256 else size
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(data), offset)
        blobs += data
        offset += len(data)
    return header + entries + blobs


if __name__ == "__main__":
    out = Path(__file__).with_name("icon.ico")
    out.write_bytes(ico([(s, render(s)) for s in (256, 48, 32, 16)]))
    print(f"Creato {out}")
