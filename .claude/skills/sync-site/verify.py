#!/usr/bin/env python3
"""Sanity gates for the built site in docs/. Exits non-zero if anything is wrong.

Run from the repo root:  python3 .claude/skills/sync-site/verify.py

Gates:
  (a) no ".dc.html" left in any link of a published page
  (b) docs/index.html is the homepage: has <x-dc>, no meta refresh
  (c) every page has <title>, canonical in <head>; home has og:title
  (d) every internal page link resolves to a file in docs/
  (e) every local asset reference resolves to a file in docs/
  (f) permanent files are present (.nojekyll, support.js, components, SEO files)
  (g) shared components are published at the site root and marked noindex
  (h) every page carries a pre-render mirror with zero unresolved {{ }}
  (i) pages.json urls == sitemap.xml locs == llms.txt Pages links
External links to the live WordPress site are reported as WARN, not BAD: they
keep working until the DNS switch but must be localized before it.
"""
import glob
import json
import os
import re
import sys
from urllib.parse import unquote

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.getcwd()
OUT = os.path.join(REPO, "docs")
DATA = json.load(open(os.path.join(HERE, "pages.json"), encoding="utf-8"))
SITE = DATA["site"].rstrip("/")
PAGES = [p for p in DATA["pages"] if not p.get("_comment")]
COMPONENTS = DATA.get("components", [])
SLUGS = [p["slug"] for p in PAGES]
MEDIA_EXT = r"(?:png|jpe?g|webp|svg|gif|pdf|mp4|json|ico)"

fail = 0
warn = 0


def bad(msg):
    global fail
    fail = 1
    print("  BAD:", msg)


def warning(msg):
    global warn
    warn += 1
    print("  WARN:", msg)


def ok(msg):
    print("  ok:", msg)


def page_file(slug):
    return os.path.join(OUT, "index.html" if slug == "index" else slug + "/index.html")


def head_of(html):
    return html.split("<body", 1)[0]


def page_dir_url(slug):
    return "/" if slug == "index" else "/" + slug + "/"


def resolve(slug, ref):
    """Resolve a reference against the site root (every page has a root-pointing <base>).

    Returns a docs-relative path, or None for external / anchor-only references."""
    ref = ref.strip()
    if not ref or ref.startswith(("#", "mailto:", "tel:", "data:", "javascript:")):
        return None
    if re.match(r"^[a-z][a-z0-9+.-]*:", ref, re.I) or ref.startswith("//"):
        if ref.startswith(SITE + "/"):
            ref = ref[len(SITE) + 1:]
        elif ref == SITE:
            ref = ""
        else:
            return None
    ref = ref.split("#", 1)[0].split("?", 1)[0]
    ref = unquote(ref)
    if ref.startswith("/"):
        return ref.lstrip("/")
    while ref.startswith(("./", "../")):  # "../" only occurs as the root-pointing <base href>
        ref = ref[3:] if ref.startswith("../") else ref[2:]
    return ref


def read(f):
    return open(f, encoding="utf-8").read()


scan_files = [page_file(s) for s in SLUGS] + \
    [os.path.join(OUT, c) for c in COMPONENTS] + \
    glob.glob(os.path.join(OUT, "*.js")) + [os.path.join(OUT, "404.html")]

print("--- (a) no .dc.html left in links")
left = []
for f in scan_files:
    if not os.path.exists(f):
        continue
    t = read(f)
    for m in re.finditer(r"""(?:href|url)\s*[:=]\s*["']([^"']*\.dc\.html[^"']*)["']""", t):
        if not any(m.group(1).startswith(c) for c in COMPONENTS):
            left.append((os.path.relpath(f, REPO), m.group(1)))
if left:
    for l in left[:20]:
        bad(str(l))
else:
    ok("none")

print("--- (b) index is home")
t = read(os.path.join(OUT, "index.html"))
if "<x-dc>" in t and 'http-equiv="refresh"' not in t:
    ok("docs/index.html has <x-dc>, no refresh")
else:
    bad("docs/index.html is not the home page")

print("--- (c) static SEO head")
before = fail
for s in SLUGS:
    f = page_file(s)
    if not os.path.exists(f):
        bad("missing " + os.path.relpath(f, REPO))
        continue
    h = head_of(read(f))
    for needle in ("<title>", 'rel="canonical"'):
        if needle not in h:
            bad("%s: no %s in <head>" % (os.path.relpath(f, REPO), needle))
    if s == "index" and "og:title" not in h:
        bad("home has no og:title")
if fail == before:
    ok("every page has title + canonical")

print("--- (d) internal links")
valid = set(SLUGS) - {"index"}
before = fail
for s in SLUGS:
    f = page_file(s)
    if not os.path.exists(f):
        continue
    t = read(f)
    for m in re.finditer(r"""(?:href|url)\s*[:=]\s*["']([^"'{}<>]*)["']""", t):
        r = resolve(s, m.group(1))
        if r is None or r == "":
            continue
        if r.startswith("assets/") or "." in r.split("/")[-1]:
            continue  # asset, checked in (e)
        if r.rstrip("/") not in valid:
            bad("%s -> %s (no such page)" % (os.path.relpath(f, REPO), m.group(1)))
if fail == before:
    ok("all internal links resolve")

print("--- (e) assets")
before = fail
missing = set()
asset_re = re.compile(r"""["'(]((?:https://everyone\.ai/)?(?:\.\./|\./)*assets/[^"'()<>{}]+\.%s)["')]""" % MEDIA_EXT)
for f in scan_files:
    if not os.path.exists(f):
        continue
    t = read(f)
    slug = None
    for s in SLUGS:
        if f == page_file(s):
            slug = s
    for m in asset_re.finditer(t):
        r = m.group(1)
        if r.startswith("https://everyone.ai/"):
            r = r[len("https://everyone.ai/"):]
        elif slug is not None and f.endswith(".html"):
            r = resolve(slug, r)
        else:
            r = r.lstrip("./")
        r = unquote(r)
        if not os.path.exists(os.path.join(OUT, r)):
            missing.add(r)
if missing:
    for r in sorted(missing):
        bad("missing asset " + r)
else:
    ok("all asset references exist")

print("--- (f) permanent files")
for n in (".nojekyll", "support.js", "image-slot.js", "i18n-site.js", "i18n-home.js", "404.html",
          "robots.txt", "sitemap.xml", "llms.txt", ".image-slots.state.json"):
    if not os.path.exists(os.path.join(OUT, n)):
        bad("missing docs/" + n)
if fail == before:
    ok("present")

print("--- (g) components")
for c in COMPONENTS:
    f = os.path.join(OUT, c)
    if not os.path.exists(f):
        bad("missing " + c)
    elif "noindex" not in head_of(read(f)):
        bad(c + " not noindex")
    else:
        ok(c)

print("--- (h) pre-render mirror")
SWAP = "#dc-root:not(:empty)~#dc-prerender{display:none}"
for s in SLUGS:
    f = page_file(s)
    if not os.path.exists(f):
        continue
    t = read(f)
    m = re.search(r"<!--dc-prerender-start-->(.*?)<!--dc-prerender-end-->", t, re.S)
    if not m:
        bad("no mirror in " + os.path.relpath(f, REPO))
    elif "{{" in m.group(1):
        bad("unresolved {{ }} in mirror of " + os.path.relpath(f, REPO))
    elif SWAP not in t:
        bad("no swap css in " + os.path.relpath(f, REPO))

print("--- (i) pages.json == sitemap == llms")
want = {SITE + page_dir_url(s) for s in SLUGS}
if os.path.exists(os.path.join(OUT, "sitemap.xml")):
    sm = set(re.findall(r"<loc>([^<]+)</loc>", read(os.path.join(OUT, "sitemap.xml"))))
    if sm != want:
        bad("sitemap differs: only-sitemap=%s only-pages=%s" % (sorted(sm - want), sorted(want - sm)))
    else:
        ok("sitemap matches %d pages" % len(want))
if os.path.exists(os.path.join(OUT, "llms.txt")):
    ll = set(re.findall(r"\((https://everyone\.ai/[^)#]*)\)", read(os.path.join(OUT, "llms.txt"))))
    if not want <= ll:
        bad("llms.txt lacks: %s" % sorted(want - ll))
    else:
        ok("llms.txt lists every page")

print("--- (j) external live-site hotlinks (must be localized before DNS switch)")
for f in scan_files:
    if not os.path.exists(f):
        continue
    t = read(f)
    for u, n in sorted(__import__("collections").Counter(
            re.findall(r"https://everyone\.ai/wp-content/[^\"' )<>\\\\]+", t)).items()):
        warning("%s -> %s" % (os.path.relpath(f, REPO), u))

print()
if fail:
    print("VERIFY: FAILED")
elif warn:
    print("VERIFY: passed with %d warning(s)" % warn)
else:
    print("VERIFY: all checks passed")
sys.exit(fail)
