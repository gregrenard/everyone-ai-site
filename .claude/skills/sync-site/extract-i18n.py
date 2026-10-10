#!/usr/bin/env python3
"""List every translatable string the built site renders, into i18n/en.json.

Runs each page of docs/ in headless Chrome with ?lang=en&eai_extract=1, at a
desktop and a phone width (layout decides what is one unit, and some content is
only rendered on one of them), and collects the units the translation overlay
(i18n-overlay.js) reports. Because the overlay itself does the reporting, the
keys written here are exactly the keys it looks up at runtime.

Then reports, per language, how many of those strings i18n/<lang>.json lacks.
A string the Design project changes gets a new key and falls back to English
until it is translated again, so run this after every sync.

Usage (from the repo root, after build.py):
    python3 .claude/skills/sync-site/extract-i18n.py [--missing <lang>]
"""
import functools
import http.server
import json
import os
import re
import subprocess
import sys
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.getcwd(), "docs")
DATA = json.load(open(os.path.join(HERE, "pages.json"), encoding="utf-8"))
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
WIDTHS = (1400, 420)


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def units(url, width, lang="en"):
    r = subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--window-size=%d,2000" % width,
                        "--virtual-time-budget=20000", "--dump-dom",
                        "%s?lang=%s&eai_extract=1" % (url, lang)], capture_output=True, text=True)
    m = re.search(r'<script type="application/json" id="eai-i18n-units">(.*?)</script>', r.stdout, re.S)
    if not m:
        raise SystemExit("no units dumped for " + url)
    return json.loads(m.group(1))["units"]


def main():
    handler = functools.partial(Quiet, directory=OUT)
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    root = "http://127.0.0.1:%d/" % srv.server_address[1]

    catalog = {}
    for page in DATA["pages"]:
        slug = page["slug"]
        url = root + ("" if slug == "index" else slug + "/")
        for w in WIDTHS:
            for u in units(url, w):
                pages = catalog.setdefault(u["k"], [])
                if slug not in pages:
                    pages.append(slug)
        print("%-62s %4d strings so far" % (slug, len(catalog)))
    srv.shutdown()

    dest = os.path.join(HERE, "i18n", "en.json")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "w", encoding="utf-8") as f:
        json.dump({"units": catalog}, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print("\n%d strings -> %s" % (len(catalog), os.path.relpath(dest)))

    want = sys.argv[sys.argv.index("--missing") + 1] if "--missing" in sys.argv else None
    for lang in DATA["languages"][1:]:
        f = os.path.join(HERE, "i18n", lang + ".json")
        have = json.load(open(f, encoding="utf-8")) if os.path.exists(f) else {}
        lack = [k for k in catalog if k not in have]
        print("%s: %d of %d translated" % (lang, len(catalog) - len(lack), len(catalog)))
        if lang == want:
            for k in lack:
                print("   ", json.dumps(k, ensure_ascii=False))


if __name__ == "__main__":
    main()
