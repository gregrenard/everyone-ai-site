#!/usr/bin/env python3
"""Deploy-only build: src/*.dc.html (the Claude Design snapshot) -> docs/ (the published site).

Claude Design is the source of truth for content; this script never changes what a page
says, only how it is addressed and served. Idempotent: docs/ page outputs are regenerated
from src/ on every run, so it can be re-run at any time.

Transforms, in order (each exists because the raw Design export is not deployable as-is):
  1. nested clean URLs  - each page is written to docs/<slug>/index.html (home -> docs/index.html)
                          with a relative <base href> so the runtime's relative fetches
                          (./support.js, ./SiteHeader.dc.html, assets/...) resolve at the site root
                          under BOTH a project path (github.io/<repo>/) and a custom domain root.
  2. link rewrite       - "<Name>.dc.html[#frag]" -> "<slug>/[#frag]" (base-relative), and absolute
                          https://everyone.ai/<slug>/ links to known pages -> base-relative, so a
                          preview never sends visitors to the live WordPress site. Other
                          everyone.ai URLs (wp-content PDFs, privacy policy...) are left alone.
  3. static SEO head    - <helmet> is copied into the real <head> (crawlers do not run JS), with
                          <html lang>, and noindex on shared components and on preview builds.
  4. hash-link shim     - with <base>, a bare href="#x" would navigate to the site root; a small
                          capture-phase listener keeps in-page anchors in-page.
  5. sidecar + .nojekyll - an empty .image-slots.state.json (image-slot.js fetches it) and
                          .nojekyll so dotfiles/underscored paths are served as-is.

Usage (from the repo root):
    python3 .claude/skills/sync-site/build.py [--preview]
"""
import json, os, re, shutil, sys
from urllib.parse import unquote

_HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.getcwd()
SRC = os.path.join(REPO, "src")
OUT = os.path.join(REPO, "docs")
PREVIEW = "--preview" in sys.argv

DATA = json.load(open(os.path.join(_HERE, "pages.json"), encoding="utf-8"))
SITE = DATA["site"].rstrip("/")
PAGES = DATA["pages"]
COMPONENTS = DATA.get("components", [])
NAME2SLUG = {p["design"][: -len(".dc.html")]: p["slug"] for p in PAGES}
SLUGS = {p["slug"] for p in PAGES}

SHIM = (
    '<script id="eai-hash-shim">document.addEventListener("click",function(e){'
    'var a=e.target.closest&&e.target.closest(\'a[href^="#"]\');if(!a)return;'
    'var h=a.getAttribute("href");e.preventDefault();'
    'if(h.length>1){var el=document.getElementById(decodeURIComponent(h.slice(1)));'
    "if(el)el.scrollIntoView();}else{window.scrollTo(0,0);}"
    'history.replaceState(null,"",location.pathname+location.search+h);},true);</script>'
)
LINK_RE = re.compile(r"""(["'])([^"'#?{}<>]+)\.dc\.html((?:#[^"'{}<>]*)?)\1""")
SITE_RE = re.compile(r"""(["'])https://everyone\.ai/([^"'#?{}<> ]*?)/?((?:[#?][^"'{}<> ]*)?)\1""")
WP_RE = re.compile(r"""https://everyone\.ai/(wp-content/uploads/[^"'\\ )<>]+)""")
PROTECT_RE = re.compile(r"<helmet>.*?</helmet>|<script type=\"application/ld\+json\">.*?</script>", re.S)


def out_path(slug):
    return "index.html" if slug == "index" else slug + "/index.html"


def rewrite_links(html, slug):
    depth = 0 if slug == "index" else slug.count("/") + 1
    prefix = "../" * depth

    def rel(target, frag):
        # Every nested page carries <base href="../"...> pointing at the site root,
        # so links are written root-relative with NO per-page prefix.
        url = "" if target == "index" else target + "/"
        dest = url + frag
        return dest if dest else "./"

    def dc_link(m):
        name = unquote(m.group(2))
        if name not in NAME2SLUG:
            return m.group(0)
        return m.group(1) + rel(NAME2SLUG[name], m.group(3)) + m.group(1)

    html = LINK_RE.sub(dc_link, html)

    held = []

    def hold(m):
        held.append(m.group(0))
        return "\x00%d\x00" % (len(held) - 1)

    def site_link(m):
        target = m.group(2)
        if target != "" and target not in SLUGS:
            return m.group(0)
        return m.group(1) + rel(target or "index", m.group(3)) + m.group(1)

    body = PROTECT_RE.sub(hold, html)
    body = SITE_RE.sub(site_link, body)
    body = WP_RE.sub(lambda m: "assets/" + m.group(1), body)
    return re.sub("\x00(\\d+)\x00", lambda m: held[int(m.group(1))], body)


def build_page(page):
    slug = page["slug"]
    src = open(os.path.join(SRC, page["design"]), encoding="utf-8").read()
    depth = 0 if slug == "index" else slug.count("/") + 1
    html = rewrite_links(src, slug)

    m = re.search(r"<helmet>(.*?)</helmet>", html, re.S)
    helmet = m.group(1).strip("\n") if m else ""
    head_extra = []
    if depth:
        head_extra.append('<base href="%s">' % ("../" * depth))
    if helmet and "<title>" not in html.split("<body", 1)[0]:
        head_extra.append(helmet)
    if PREVIEW or slug in COMPONENT_SLUGS:
        head_extra.append('<meta name="robots" content="noindex">')
    if depth:
        head_extra.append(SHIM)

    html = html.replace("<html>", '<html lang="en">', 1)
    html = re.sub(
        r"(<meta charset=[^>]*>\n)",
        lambda m: m.group(1) + ("\n".join(head_extra) + "\n" if head_extra else ""),
        html,
        count=1,
    )
    if slug not in COMPONENT_SLUGS and '<title>' not in html.split("<body", 1)[0]:
        raise SystemExit("no <title> in head for %s" % page["design"])

    dest = os.path.join(OUT, out_path(slug))
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "w", encoding="utf-8", newline="") as f:
        f.write(html)
    return dest


COMPONENT_SLUGS = {c[: -len(".dc.html")] for c in COMPONENTS}


def main():
    for entry in os.listdir(OUT):
        full = os.path.join(OUT, entry)
        if entry in ("assets", ".nojekyll", "CNAME"):
            continue
        if entry.endswith(".dc.html"):
            os.remove(full)
        elif os.path.isdir(full) and os.path.exists(os.path.join(full, "index.html")):
            shutil.rmtree(full)
    if os.path.exists(os.path.join(OUT, "index.html")):
        os.remove(os.path.join(OUT, "index.html"))

    for page in PAGES:
        d = build_page(page)
        print("page      %s" % os.path.relpath(d, REPO))

    for comp in COMPONENTS:
        slug = comp[: -len(".dc.html")]
        src = open(os.path.join(SRC, comp), encoding="utf-8").read()
        html = rewrite_links(src, "index")
        html = html.replace("<html>", '<html lang="en">', 1)
        html = html.replace("<meta charset=\"utf-8\">\n", '<meta charset="utf-8">\n<meta name="robots" content="noindex">\n', 1)
        with open(os.path.join(OUT, comp), "w", encoding="utf-8", newline="") as f:
            f.write(html)
        print("component %s" % os.path.join("docs", comp))

    open(os.path.join(OUT, ".nojekyll"), "w").close()
    with open(os.path.join(OUT, ".image-slots.state.json"), "w") as f:
        f.write("{}\n")

    left = []
    for root, _, files in os.walk(OUT):
        for fn in files:
            if fn.endswith(".html"):
                t = open(os.path.join(root, fn), encoding="utf-8").read()
                for m in re.finditer(r"""(?:href|url)\s*[:=]\s*["']([^"']*\.dc\.html[^"']*)["']""", t):
                    if not any(m.group(1).startswith(c) for c in COMPONENTS):
                        left.append((os.path.relpath(os.path.join(root, fn), REPO), m.group(1)))
    if left:
        print("UNREWRITTEN .dc.html links:")
        for l in left[:30]:
            print("  ", l)
        sys.exit(1)
    print("build ok: %d pages, %d components" % (len(PAGES), len(COMPONENTS)))


if __name__ == "__main__":
    main()
