#!/usr/bin/env python3
"""Cut a product photo on a white background loose: the white area that
touches the image border becomes transparent, with a soft edge.

Usage: .venv/bin/python tools/cutout_white.py assets/images/<file> [threshold]
Writes src/img/panels-sharp/<same name>.webp (same size), which the build
then uses instead of the original (legend coordinates stay valid).
"""
import sys
from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
src = Path(sys.argv[1])
thr = int(sys.argv[2]) if len(sys.argv) > 2 else 232
a = np.asarray(Image.open(ROOT / src).convert("RGB")).astype(int)
H, W, _ = a.shape
white = a.min(axis=2) >= thr
bg = np.zeros((H, W), bool)
q = deque((y, x) for x in range(W) for y in (0, H - 1) if white[y, x])
q.extend((y, x) for y in range(H) for x in (0, W - 1) if white[y, x])
for y, x in q:
    bg[y, x] = True
while q:
    y, x = q.popleft()
    for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        ny, nx = y + dy, x + dx
        if 0 <= ny < H and 0 <= nx < W and white[ny, nx] and not bg[ny, nx]:
            bg[ny, nx] = True
            q.append((ny, nx))
alpha = Image.fromarray(np.where(bg, 0, 255).astype("uint8"))
grown = np.asarray(alpha.filter(ImageFilter.MaxFilter(3))) > 0
shrunk = np.asarray(alpha.filter(ImageFilter.MinFilter(3))) == 0
edge = grown & shrunk
A = np.asarray(alpha).astype(float)
lum = a.mean(axis=2)
A[edge] = np.clip((255 - lum[edge]) / (255 - 30) * 255, 0, 255)
out = Image.fromarray(np.dstack([a.astype("uint8"), A.astype("uint8")]))
dest = ROOT / "src" / "img" / "panels-sharp" / (src.stem + ".webp")
out.save(dest, "WEBP", lossless=True, method=6)
print("wrote", dest.relative_to(ROOT), out.size, out.getchannel("A").getbbox())
