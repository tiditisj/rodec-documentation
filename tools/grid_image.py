"""grid.py IMAGE OUT [maxside] : draw a pixel grid (labels in ORIGINAL image px) for picking coordinates."""
import sys
from PIL import Image, ImageDraw
src, out = sys.argv[1], sys.argv[2]
maxside = int(sys.argv[3]) if len(sys.argv) > 3 else 1400
im = Image.open(src).convert("RGBA")
bg = Image.new("RGBA", im.size, (246, 245, 244, 255)); bg.alpha_composite(im)
W, H = im.size
s = maxside / max(W, H)
big = bg.resize((int(W * s), int(H * s)), Image.LANCZOS).convert("RGB")
d = ImageDraw.Draw(big)
target = max(W, H) / 40
step = next(v for v in (5, 10, 20, 25, 50, 100, 200, 250, 500, 1000) if v >= target)
for x in range(0, W, step):
    X = x * s; major = (x // step) % 5 == 0
    d.line([(X, 0), (X, big.height)], fill=(0, 150, 255) if major else (160, 210, 255), width=1)
    if major: d.text((X + 2, 2), str(x), fill=(0, 90, 255))
for y in range(0, H, step):
    Y = y * s; major = (y // step) % 5 == 0
    d.line([(0, Y), (big.width, Y)], fill=(255, 0, 160) if major else (255, 180, 220), width=1)
    if major: d.text((2, Y + 2), str(y), fill=(220, 0, 120))
big.save(out)
print(W, H, "step", step, "scale", round(s, 3))
