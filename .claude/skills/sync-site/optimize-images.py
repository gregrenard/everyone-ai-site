#!/usr/bin/env python3
"""Keep every image under docs/assets within the agreed limits (run before build.py).

Rule agreed by the team (2026-10-29): at most 1600 px on the long side, WebP, under 200 KiB;
lowered to 150 KiB on 2026-11-09 (Julien's fixes kanban, card T5: about 150 KB per image).
An oversized .webp is rewritten in place. An oversized .png/.jpg becomes a .webp next to it,
and the old -> new path is recorded in image-map.json so build.py can rewrite references.
Quality goes down from 82 to 70, then the image is scaled down, so a large photo loses
pixels it does not need before it loses visible quality.

An image that is too SMALL cannot be fixed here: enlarging it does not add detail. verify.py
lists those, and they need the original file.
"""
import glob, json, os, sys
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.getcwd(), "docs")
LIMIT = 150 * 1024
MAP_FILE = os.path.join(HERE, "image-map.json")


def encode(im, dest):
    side = 1600
    while True:
        w, h = im.size
        ratio = min(1, side / max(w, h))
        cur = im.resize((round(w * ratio), round(h * ratio)), Image.LANCZOS) if ratio < 1 else im
        for q in (82, 78, 74, 70):
            cur.save(dest, "WEBP", quality=q, method=6)
            if os.path.getsize(dest) <= LIMIT:
                return cur.size, q
        side = int(side * 0.85)


def main():
    mapping = json.load(open(MAP_FILE)) if os.path.exists(MAP_FILE) else {}
    n = 0
    for f in sorted(glob.glob(os.path.join(OUT, "assets", "**", "*"), recursive=True)):
        ext = os.path.splitext(f)[1].lower()
        if ext not in (".png", ".jpg", ".jpeg", ".webp") or os.path.getsize(f) <= LIMIT:
            continue
        rel = os.path.relpath(f, OUT)
        before = os.path.getsize(f)
        im = Image.open(f)
        im = im.convert("RGBA" if im.mode in ("RGBA", "LA", "P") else "RGB")
        dest = f if ext == ".webp" else os.path.splitext(f)[0] + ".webp"
        tmp = dest + ".tmp"
        size, q = encode(im, tmp)
        os.replace(tmp, dest)
        if dest != f:
            os.remove(f)
            mapping[rel] = os.path.relpath(dest, OUT)
        n += 1
        print("image %-62s %5d -> %4d KiB  %dx%d q%d" % (rel, before // 1024, os.path.getsize(dest) // 1024, size[0], size[1], q))
    with open(MAP_FILE, "w") as fh:
        json.dump(mapping, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print("images optimized: %d" % n)


if __name__ == "__main__":
    sys.exit(main())
