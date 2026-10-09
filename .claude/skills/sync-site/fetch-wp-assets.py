#!/usr/bin/env python3
"""Localize files the Design pages still hotlink from the live WordPress site.

The Claude Design project references some files by absolute URL on
https://everyone.ai/wp-content/uploads/... (report PDFs, a video). Those keep
working only while WordPress serves everyone.ai; after the DNS switch they 404.
This script downloads each one into docs/assets/wp-content/uploads/..., where
build.py rewrites the references to point (it only rewrites files that exist
locally, so run this BEFORE build.py / deploy.sh).

Images and PDFs are always fetched. Videos are large (the coalition launch
video is ~77 MB; GitHub rejects files over 100 MB and warns above 50 MB), so
they are fetched only with --media. Without it they are reported and left
external.

Idempotent: files already present are skipped. Do NOT run after the DNS
switch — the source URLs will be gone; the committed copies are then the only
ones.

Usage:  python3 .claude/skills/sync-site/fetch-wp-assets.py [--media]   (from the repo root)
"""
import glob
import os
import re
import subprocess
import sys
from urllib.parse import unquote

REPO = os.getcwd()
SRC = os.path.join(REPO, "src")
OUT = os.path.join(REPO, "docs")
MEDIA = "--media" in sys.argv
WP_RE = re.compile(r"""https://everyone\.ai/(wp-content/uploads/[^"' )<>\\]+)""")
VIDEO_EXT = (".mp4", ".webm", ".mov", ".m4v", ".ogv")


def main():
    urls = set()
    for f in glob.glob(os.path.join(SRC, "*.dc.html")):
        urls.update(WP_RE.findall(open(f, encoding="utf-8").read()))
    fetched = skipped = failed = 0
    for u in sorted(urls):
        rel = "assets/" + unquote(u)
        dest = os.path.join(OUT, rel)
        if os.path.exists(dest):
            skipped += 1
            continue
        if rel.lower().endswith(VIDEO_EXT) and not MEDIA:
            print("  WARN: video left external (use --media to fetch): " + u)
            continue
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        r = subprocess.run(["curl", "-sfL", "-m", "300", "-o", dest, "https://everyone.ai/" + u])
        if r.returncode != 0 or not os.path.exists(dest) or os.path.getsize(dest) == 0:
            if os.path.exists(dest):
                os.remove(dest)
            print("  BAD: download failed (%d): %s" % (r.returncode, u))
            failed += 1
            continue
        print("  fetched %8d  %s" % (os.path.getsize(dest), rel))
        fetched += 1
    print("\n%d referenced, %d fetched, %d already present, %d failed"
          % (len(urls), fetched, skipped, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
