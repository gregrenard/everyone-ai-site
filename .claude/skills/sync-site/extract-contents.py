#!/usr/bin/env python3
"""Deploy-adjacent: dump every page's rendered text to .works/contents/<lang>/<slug>.txt.

These are the proof-reading copies Gregory hands to his reviewer: one plain-text
file per URL, in English and French, with the URL on the first line. .works/ is
gitignored, so nothing here ever reaches a commit.

EN comes straight from the pre-render mirror each page already carries (so run
prerender.py / deploy.sh first). FR cannot: the FR/EN toggle is client-side and
leaves no FR copy on disk, so each page is re-rendered from a throwaway sibling
whose DCLogic state starts at lang:'fr'. The FR files carry no TITLE/META line
because <title> and <meta description> stay English on the FR toggle.

Usage:  python3 .claude/skills/sync-site/extract-contents.py   (from repo root)
"""
import os, re, sys, html, threading
from functools import partial
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import prerender as pr
from manifest import prerender_files, SITE

REPO = os.getcwd()
OUT = os.path.join(REPO, ".works", "contents")
RULE = "-" * 72

# <br> and <span> stay INLINE (a <br>-split heading must read as one line);
# everything else block-level starts a new line.
BLOCK = {"p", "div", "section", "article", "header", "footer", "nav", "main", "aside",
         "h1", "h2", "h3", "h4", "h5", "h6", "li", "ul", "ol", "tr", "td", "th",
         "blockquote", "figure", "figcaption", "hr", "label", "button", "form", "table"}


def to_text(frag):
    frag = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", frag)
    frag = re.sub(r"<\s*/?\s*([a-zA-Z0-9-]+)[^>]*>",
                  lambda m: "\n" if m.group(1).lower() in BLOCK else " ", frag)
    frag = html.unescape(frag)
    lines = [re.sub(r"[ \t ]+", " ", ln).strip() for ln in frag.split("\n")]
    return "\n".join(ln for ln in lines if ln)


def head_meta(page_html):
    def g(pat):
        m = re.search(pat, page_html, re.I | re.S)
        return html.unescape(m.group(1)).strip() if m else ""
    return g(r"<title>(.*?)</title>"), g(r'<meta\s+name="description"\s+content="([^"]*)"')


def main():
    for lang in ("en", "fr"):
        os.makedirs(os.path.join(OUT, lang), exist_ok=True)

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), partial(pr.Handler, directory=REPO))
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    tmp, done, failed = [], 0, []
    try:
        for page in prerender_files():
            slug = "index" if page == "index.html" else page[:-5]
            url = SITE + "/" if slug == "index" else SITE + "/" + slug
            src = open(page, encoding="utf-8").read()

            m = re.search(r"<!--dc-prerender-start-->(.*?)<!--dc-prerender-end-->", src, re.S)
            if not m:
                failed.append(slug + " (no pre-render mirror — run deploy.sh first)")
                continue
            title, desc = head_meta(src)
            open(os.path.join(OUT, "en", slug + ".txt"), "w", encoding="utf-8").write(
                "URL: %s\nTITLE: %s\nMETA DESCRIPTION: %s\n%s\n\n%s\n"
                % (url, title, desc, RULE, to_text(m.group(1))))

            fr = re.sub(r"(state = \{[^}]*?)lang: 'en'", r"\1lang: 'fr'", src, count=1)
            if fr == src:
                failed.append(slug + " (no lang state to flip)")
                continue
            tf = "__fr__%s.html" % slug
            open(tf, "w", encoding="utf-8").write(fr)
            tmp.append(tf)
            inner = pr.extract_dc_root_inner(pr.render("http://127.0.0.1:%d/%s" % (port, tf)) or "")
            if inner is None or re.search(r"\{\{[^}]*\}\}", inner):
                failed.append(slug + " (FR render failed)")
                continue
            open(os.path.join(OUT, "fr", slug + ".txt"), "w", encoding="utf-8").write(
                "URL: %s  (version francaise — bascule FR du site)\n%s\n\n%s\n"
                % (url, RULE, to_text(inner)))
            done += 1
            print("contents: %-28s en + fr" % slug)
    finally:
        for t in tmp:
            try:
                os.remove(t)
            except Exception:
                pass
        httpd.shutdown()
        httpd.server_close()

    print("\n%d/%d pages extracted to .works/contents/{en,fr}/." % (done, len(prerender_files())))
    if failed:
        print("FAILED:", failed)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
