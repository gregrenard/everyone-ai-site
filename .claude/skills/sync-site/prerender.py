#!/usr/bin/env python3
"""Deploy-only transform: static pre-render so non-JS consumers see real content.

The dc-runtime (docs/support.js) renders each page BODY from a {{ }} template at
runtime (React, loaded from unpkg). The raw HTML therefore ships unresolved
{{ }} bindings — fine for browsers and for Google, bad for no-JS clients, link
unfurlers and most AI crawlers.

Fix (progressive enhancement, no cloaking, no JS timing): headless-render each
page with Chrome, capture the resolved #dc-root HTML, and inject it as a
visible-by-default mirror that pure CSS hides the instant the runtime mounts:

    x-dc{display:none}                                   /* hide the raw template  */
    #dc-root:not(:empty) ~ #dc-prerender{display:none}   /* hide mirror once mounted */

The <x-dc> template is KEPT (the runtime needs it for language switching and the
forms), so raw view-source still contains {{ }}. MUST run LAST, after build.py,
so the mirror's links are the final clean URLs. Idempotent: any prior mirror is
stripped before re-injecting. Non-fatal when Chrome is missing (warn and skip).

Adapted from gregrenard/gregory-renard-site for nested slug directories: each page
is docs/<slug>/index.html with <base href="../"...>, so the page is requested at
its directory URL (/<slug>/) for the base to resolve.

Usage:  python3 .claude/skills/sync-site/prerender.py   (from the repo root)
"""
import json
import os
import re
import subprocess
import sys
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.getcwd()
OUT = os.path.join(REPO, "docs")
DATA = json.load(open(os.path.join(HERE, "pages.json"), encoding="utf-8"))
SLUGS = [p["slug"] for p in DATA["pages"] if not p.get("_comment")]

CHROME = os.environ.get("CHROME") or "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
SWAP_CSS = "x-dc{display:none}#dc-root:not(:empty)~#dc-prerender{display:none}"
STYLE = '<style id="dc-prerender-css">' + SWAP_CSS + "</style>"
MARK_A, MARK_B = "<!--dc-prerender-start-->", "<!--dc-prerender-end-->"
MEDIA_EXT = (".mp4", ".webm", ".mov", ".m4v", ".ogv")


def page_file(slug):
    return os.path.join(OUT, "index.html" if slug == "index" else slug + "/index.html")


def page_url(port, slug):
    return "http://127.0.0.1:%d/%s" % (port, "" if slug == "index" else slug + "/")


class Handler(SimpleHTTPRequestHandler):
    """Serve docs/ over loopback but refuse heavy media: Chrome's virtual time does
    not advance while a media element is still loading, and the captured DOM is the
    same whether or not a <video>'s metadata loaded."""

    def send_head(self):
        if self.path.split("?")[0].lower().endswith(MEDIA_EXT):
            self.send_error(404, "media blocked during pre-render")
            return None
        return super().send_head()

    def log_message(self, *args):
        pass


def render(url):
    try:
        out = subprocess.run(
            [CHROME, "--headless=new", "--disable-gpu", "--dump-dom",
             "--virtual-time-budget=12000", url],
            capture_output=True, text=True, timeout=60)
        return out.stdout or None
    except Exception as e:
        print("  render error:", e)
        return None


_TOK = re.compile(r"<div\b|</div\s*>", re.I)


def extract_dc_root_inner(html):
    """Inner HTML of <div id="dc-root">…</div> via a balanced <div> scan."""
    m = re.search(r'<div\b[^>]*\bid="dc-root"[^>]*>', html)
    if not m:
        return None
    start = m.end()
    depth = 1
    for t in _TOK.finditer(html, start):
        if t.group().lower().startswith("<div"):
            depth += 1
        else:
            depth -= 1
            if depth == 0:
                return html[start:t.start()]
    return None


def strip_prior(s):
    s = re.sub(r'\n?<style id="dc-prerender-css">.*?</style>', "", s, flags=re.S)
    s = re.sub(re.escape(MARK_A) + ".*?" + re.escape(MARK_B) + r"\n?", "", s, flags=re.S)
    return s


def main():
    if not os.path.exists(CHROME):
        print("WARN: Chrome not found at %r — skipping pre-render (pages still render via JS)." % CHROME)
        return 0
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), partial(Handler, directory=OUT))
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    done, skipped = 0, []
    try:
        for slug in SLUGS:
            f = page_file(slug)
            if not os.path.exists(f):
                skipped.append(slug + " (no file)")
                continue
            dom = render(page_url(port, slug))
            if not dom:
                skipped.append(slug + " (no render)")
                continue
            inner = extract_dc_root_inner(dom)
            if inner is None:
                skipped.append(slug + " (no #dc-root)")
                continue
            ph = len(re.findall(r"\{\{[^}]*\}\}", inner))
            if ph:
                skipped.append("%s (%d placeholders left)" % (slug, ph))
                continue
            if "</x-dc>" in inner:
                skipped.append(slug + " (contains </x-dc>)")
                continue
            s = strip_prior(open(f, encoding="utf-8").read())
            if "</x-dc>" not in s or "</head>" not in s:
                skipped.append(slug + " (no </x-dc> or </head> anchor)")
                continue
            s = s.replace("</head>", STYLE + "\n</head>", 1)
            block = MARK_A + '<div id="dc-prerender">' + inner + "</div>" + MARK_B
            s = s.replace("</x-dc>", "</x-dc>\n" + block, 1)
            with open(f, "w", encoding="utf-8", newline="") as fh:
                fh.write(s)
            done += 1
            print("prerender: %-70s (+%d bytes)" % (slug, len(inner)))
    finally:
        httpd.shutdown()
        httpd.server_close()
    print("\nprerendered %d/%d pages." % (done, len(SLUGS)))
    if skipped:
        print("SKIPPED:", skipped)
    return 0


if __name__ == "__main__":
    sys.exit(main())
