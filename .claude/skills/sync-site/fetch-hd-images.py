#!/usr/bin/env python3
"""Make sharper copies of the images Claude Design exported too small (see hd-images.json).

The Home mission photos came out of Design at 215 x 140 px and are shown full width on a
phone (about 360 CSS px, so 1000+ device pixels): the team saw them pixelated. The live
WordPress site still holds the originals. Each one is downloaded once, scaled down to the
entry's "side" (never up) and saved as WebP at quality 85, under the 200 KiB rule of
optimize-images.py. build.py then points the pages at the copy.

Idempotent: existing files are skipped. Do NOT rely on it after the DNS switch - the source
URLs will be gone; the committed copies are the only ones.

Usage:  python3 .claude/skills/sync-site/fetch-hd-images.py   (from the repo root)
"""
import io
import json
import os
import subprocess
import sys
from urllib.parse import quote

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.getcwd(), "docs")
# The live site answers 406 (mod_security) to non-browser user agents.
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
LIMIT = 200 * 1024


def main():
    entries = json.load(open(os.path.join(HERE, "hd-images.json"), encoding="utf-8"))
    made = skipped = failed = 0
    for key, e in entries.items():
        if key.startswith("_"):
            continue
        dest = os.path.join(OUT, e["file"])
        if os.path.exists(dest):
            skipped += 1
            continue
        r = subprocess.run(["curl", "-sfL", "-m", "120", "-A", UA, "https://everyone.ai/" + quote(e["from"])],
                           capture_output=True)
        if r.returncode != 0 or not r.stdout:
            print("  BAD: download failed (%d): %s" % (r.returncode, e["from"]))
            failed += 1
            continue
        img = Image.open(io.BytesIO(r.stdout))
        img = img.convert("RGBA" if "A" in img.getbands() or img.mode == "P" else "RGB")
        img.thumbnail((e["side"], e["side"]), Image.LANCZOS)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        for q in (85, 80, 75):
            img.save(dest, "WEBP", quality=q, method=6)
            if os.path.getsize(dest) <= LIMIT:
                break
        print("  made %4d KiB  %dx%d  %s" % (os.path.getsize(dest) // 1024, img.size[0], img.size[1], e["file"]))
        made += 1
    print("\n%d sharper images, %d made, %d already present, %d failed" % (made + skipped + failed, made, skipped, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
