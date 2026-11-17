#!/usr/bin/env python3
"""Check an annotation file and draw a preview of its badges and zones.

Usage: .venv/bin/python tools/preview_annotation.py src/annotations/<name>.json [out_dir]

- Verifies that every "ref" points at something in the page text (the same
  check tools/build.py does), without building the site.
- Writes one PNG per panel to out_dir (default: /tmp): the image with each
  zone outlined and each numbered badge drawn where the page will show it.
"""
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build  # noqa: E402  (loads site.json; does not write anything)

cfg_path = Path(sys.argv[1])
out_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("/tmp")
cfg = json.loads(cfg_path.read_text())
path = cfg["path"]
if path not in build.PAGES:
    raise SystemExit(f"unknown page path {path}")

body = build.load_body(path)
problems = []
for find, repl in cfg.get("corrections", []):
    if find not in body:
        problems.append(f"correction text not found: {find}")
    body = body.replace(find, repl)
for panel in cfg["panels"]:
    for it in panel["items"]:
        for key in ("name", "text", "at"):
            if key not in it:
                problems.append(f"item without {key}: {it}")
        if it.get("ref"):
            try:
                body, _ = build.add_ref_anchor(body, it["ref"], cfg_path.name)
            except SystemExit as e:
                problems.append(str(e))
    img = build.ROOT / panel["image"]
    if not img.exists():
        problems.append(f"missing image {panel['image']}")

n = 0
for pi, panel in enumerate(cfg["panels"]):
    im = Image.open(build.ROOT / panel["image"]).convert("RGBA")
    bg = Image.new("RGBA", im.size, (246, 245, 244, 255))
    bg.alpha_composite(im)
    scale = max(1, 1400 // max(im.size))
    big = bg.resize((im.width * scale, im.height * scale), Image.LANCZOS)
    d = ImageDraw.Draw(big)
    r = 11
    for it in panel["items"]:
        n += 1
        if it.get("rect"):
            x0, y0, x1, y1 = (v * scale for v in it["rect"])
            d.rectangle((x0, y0, x1, y1), outline=(255, 92, 0, 255), width=2)
        x, y = (v * scale for v in it["at"])
        d.ellipse((x - r, y - r, x + r, y + r), fill=(255, 92, 0, 255), outline=(17, 18, 20, 255), width=2)
        d.text((x - (7 if n > 9 else 4), y - 6), str(n), fill=(255, 255, 255, 255))
    out = out_dir / f"{cfg_path.stem}-panel{pi + 1}.png"
    big.convert("RGB").save(out)
    print("preview:", out)

if problems:
    print("PROBLEMS:")
    for p in problems:
        print(" -", p)
    sys.exit(1)
print("ok:", n, "items")
