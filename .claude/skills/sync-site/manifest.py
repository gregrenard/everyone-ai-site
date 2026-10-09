#!/usr/bin/env python3
"""Single source of truth for the site's page list — see pages.json.

Import it from Python (extract-pulled.py, prerender.py):

    from manifest import design_pages, content_slugs, home_design

or query it from bash (deploy.sh, verify.sh), one item per line:

    python3 manifest.py design         # 14 Design .dc.html filenames (incl. home)
    python3 manifest.py home-design    # the home's Design filename
    python3 manifest.py subpages       # 13 deployed slugs (everything but the home)
    python3 manifest.py content        # 10 real content slugs (no home, no stubs)
    python3 manifest.py stubs          # 3 redirect-only slugs
    python3 manifest.py prerender      # 11 deployed .html filenames (index.html first)
    python3 manifest.py sitemap-urls   # 11 canonical URLs (home + content)

Bash callers must read line-by-line, never word-split: the home's Design filename
contains spaces ("Gregory Renard - Home v2.dc.html").
"""
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_DATA = json.load(open(os.path.join(_HERE, "pages.json"), encoding="utf-8"))

SITE = _DATA["site"]
PAGES = [p for p in _DATA["pages"] if not p.get("_comment")]


def _by_role(*roles):
    return [p for p in PAGES if p["role"] in roles]


def design_pages():
    """Every Design-side filename to pull, home included (extract-pulled.py)."""
    return [p["design"] for p in PAGES]


def home_design():
    """The home component's Design filename — deployed as index.html."""
    homes = _by_role("home")
    if len(homes) != 1:
        raise SystemExit("pages.json: expected exactly 1 role=home, found %d" % len(homes))
    return homes[0]["design"]


def subpage_slugs():
    """Deployed slugs for everything except the home — the *.dc.html -> *.html rename set."""
    return [p["slug"] for p in _by_role("content", "stub")]


def content_slugs():
    """Real content pages: static SEO head, pre-render, sitemap and llms.txt apply."""
    return [p["slug"] for p in _by_role("content")]


def stub_slugs():
    """Redirect-only pages: excluded from pre-render, sitemap and llms.txt."""
    return [p["slug"] for p in _by_role("stub")]


def prerender_files():
    """Deployed .html files that carry a static pre-render mirror (index.html first)."""
    return ["index.html"] + [s + ".html" for s in content_slugs()]


def sitemap_urls():
    """Canonical URLs that must appear in sitemap.xml AND llms.txt."""
    return [SITE + "/"] + [SITE + "/" + s for s in content_slugs()]


_QUERIES = {
    "design": design_pages,
    "home-design": lambda: [home_design()],
    "subpages": subpage_slugs,
    "content": content_slugs,
    "stubs": stub_slugs,
    "prerender": prerender_files,
    "sitemap-urls": sitemap_urls,
}

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in _QUERIES:
        raise SystemExit("usage: manifest.py {%s}" % "|".join(_QUERIES))
    for item in _QUERIES[sys.argv[1]]():
        print(item)
