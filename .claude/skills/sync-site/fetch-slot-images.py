#!/usr/bin/env python3
"""Fill image slots the Design project leaves empty, from the live WordPress site.

The About team grid and the Newsroom podcast/event/webinar/award cards render
<image-slot> elements whose photo is not set in Claude Design, so they show a
dashed placeholder. slot-images.json maps each such slot id to the upload the
live site shows for it ("from") and to the optimized local copy build.py wires
in ("file"). This script creates the local copies that are missing.

The WordPress originals are far larger than the slots need (a 5 MB PNG for a
140 px avatar; 47 MB for the 89 files), so each one is resized and re-encoded
as WebP: team photos to 400 px on the long side, news cards to 1200 px.

The durable fix is to set these images in Claude Design; once a slot has a
src there, its entry here is ignored by the runtime shim and can be removed.

Idempotent: existing files are skipped. Do NOT rely on it after the DNS
switch - the source URLs will be gone; the committed copies are the only ones.

Usage:  python3 .claude/skills/sync-site/fetch-slot-images.py   (from the repo root)
Requires Pillow.
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
MAX_SIDE = {"team": 400, "news": 1200}


def main():
    slots = json.load(open(os.path.join(HERE, "slot-images.json"), encoding="utf-8"))
    todo = {}
    for entry in slots.values():
        todo[entry["file"]] = entry["from"]
    made = skipped = failed = 0
    for rel, src in sorted(todo.items()):
        dest = os.path.join(OUT, rel)
        if os.path.exists(dest):
            skipped += 1
            continue
        r = subprocess.run(["curl", "-sfL", "-m", "120", "-A", UA, "https://everyone.ai/" + quote(src)],
                           capture_output=True)
        if r.returncode != 0 or not r.stdout:
            print("  BAD: download failed (%d): %s" % (r.returncode, src))
            failed += 1
            continue
        kind = os.path.basename(rel).split("-", 1)[0]
        img = Image.open(io.BytesIO(r.stdout))
        img = img.convert("RGBA" if "A" in img.getbands() or img.mode == "P" else "RGB")
        img.thumbnail((MAX_SIDE[kind], MAX_SIDE[kind]), Image.LANCZOS)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        img.save(dest, "WEBP", quality=82, method=6)
        print("  made %7d  %s" % (os.path.getsize(dest), rel))
        made += 1
    print("\n%d slot images, %d made, %d already present, %d failed"
          % (len(todo), made, skipped, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
