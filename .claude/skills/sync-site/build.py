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
  5. slot images        - slots the Design project leaves empty (team photos, newsroom cards)
                          get the local image listed in slot-images.json, set at runtime on
                          <image-slot> elements whose src is empty. A slot that has a src in
                          Design is never touched, so Design stays authoritative.
  6. translation overlay - Design translates only Home and the header. i18n-overlay.js is
                          published as eai-i18n.js and loaded on every page; it translates the
                          rendered text from docs/i18n/<lang>.json, which is emitted here from
                          the reviewed maps in i18n/<lang>.json, restricted to the strings
                          extract-i18n.py found on the site (i18n/en.json). Text that Design
                          already translates matches no key, so Design stays authoritative.
  7. text fixes         - typos of the Design sources listed in text-fixes.json are corrected
                          in the published pages until they are fixed in Design.
  8. mobile CSS         - justified paragraphs are left-aligned below 640 px.
  9. sidecar + .nojekyll - an empty .image-slots.state.json (image-slot.js fetches it) and
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
    'if(el)el.scrollIntoView();else if(h==="#top")window.scrollTo(0,0);}else{window.scrollTo(0,0);}'
    'history.replaceState(null,"",location.pathname+location.search+h);},true);</script>'
)
# Arriving with a fragment (Home / Contact from another page): the browser scrolls
# before the runtime has replaced the pre-rendered mirror, and the page lands one
# viewport too low. Re-align on the rendered target for 10 s (late images still shift
# long pages such as Newsroom), until the visitor scrolls.
# On every page, Home included (it has no <base>, so it does not carry SHIM). The id
# exists twice (mirror/template and live render): take the last one that has a box.
# The expected position is below the sticky header (scroll-padding-top, set by
# sticky-header.js) plus the section's own scroll-margin-top.
LAND = (
    '<script id="eai-hash-land">(function(){if(location.hash.length<2)return;var n=0,stop=false,id;'
    'try{id=decodeURIComponent(location.hash.slice(1));}catch(e){return;}'
    'function off(){stop=true;}'
    '["wheel","touchstart","keydown","mousedown"].forEach(function(t){addEventListener(t,off,{passive:true,once:true});});'
    'var iv=setInterval(function(){if(stop||++n>40){clearInterval(iv);return;}'
    'var all=document.querySelectorAll("[id]"),el=null;'
    'for(var i=0;i<all.length;i++)if(all[i].id===id&&all[i].getClientRects().length)el=all[i];'
    'if(!el)return;var want=(parseFloat(getComputedStyle(document.documentElement).scrollPaddingTop)||0)'
    '+(parseFloat(getComputedStyle(el).scrollMarginTop)||0);'
    'if(Math.abs(el.getBoundingClientRect().top-want)>2)el.scrollIntoView({behavior:"instant"});},250);})();</script>'
)
SLOTS = {}
_slots_file = os.path.join(_HERE, "slot-images.json")
if os.path.exists(_slots_file):
    SLOTS = {k: v["file"] for k, v in json.load(open(_slots_file, encoding="utf-8")).items()
             if os.path.exists(os.path.join(OUT, v["file"]))}
SLOT_SHIM = (
    '<script id="eai-slot-images">(function(){var M=%s;function fill(){'
    'var s=document.querySelectorAll("image-slot[id]");for(var i=0;i<s.length;i++){'
    'var u=M[s[i].id];if(u&&!s[i].getAttribute("src"))s[i].setAttribute("src",u);}}'
    'new MutationObserver(fill).observe(document.documentElement,{childList:true,subtree:true});'
    'fill();})();</script>'
)


def slot_shim(src):
    """Shim for the slot ids this page can render (ids are built as '<prefix>-...' in its script)."""
    mine = {k: v for k, v in SLOTS.items() if "'%s-'" % k.split("-", 1)[0] in src}
    if not mine:
        return ""
    return SLOT_SHIM % json.dumps(mine, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


TEXT_FIXES = {}
if os.path.exists(os.path.join(_HERE, "text-fixes.json")):
    TEXT_FIXES = json.load(open(os.path.join(_HERE, "text-fixes.json"), encoding="utf-8"))["fixes"]


def fix_text(html):
    """Correct known typos of the Design sources (text-fixes.json)."""
    for wrong, right in TEXT_FIXES.items():
        html = html.replace(wrong, right)
    return html


# Justified paragraphs open wide gaps between words on a phone-width column
# (worst with long German words); align them left below 640 px.
MOBILE_CSS = (
    '<style id="eai-mobile">@media (max-width:640px){#dc-root [style*="text-align: justify"],'
    '#dc-root [style*="text-align:justify"]{text-align:left!important}}</style>'
)
I18N_TAG = '<script src="eai-i18n.js" defer></script>'
# Keeps the menu bar visible while scrolling (sticky-header.js, published as eai-sticky.js).
STICKY_TAG = '<script src="eai-sticky.js" defer></script>'


def emit_i18n():
    """Publish the overlay and one English->translation map per language."""
    src_dir = os.path.join(_HERE, "i18n")
    out_dir = os.path.join(OUT, "i18n")
    shutil.rmtree(out_dir, ignore_errors=True)
    os.makedirs(out_dir)
    shutil.copyfile(os.path.join(_HERE, "i18n-overlay.js"), os.path.join(OUT, "eai-i18n.js"))
    shutil.copyfile(os.path.join(_HERE, "sticky-header.js"), os.path.join(OUT, "eai-sticky.js"))
    catalog = None
    if os.path.exists(os.path.join(src_dir, "en.json")):
        catalog = set(json.load(open(os.path.join(src_dir, "en.json"), encoding="utf-8"))["units"])
    for lang in DATA.get("languages", [])[1:]:
        f = os.path.join(src_dir, lang + ".json")
        full = json.load(open(f, encoding="utf-8")) if os.path.exists(f) else {}
        # A translation must keep the segment count of its key or the overlay ignores it.
        keep = {k: v for k, v in full.items()
                if (catalog is None or k in catalog) and v and v != k and k.count("\n") == v.count("\n")}
        with open(os.path.join(out_dir, lang + ".json"), "w", encoding="utf-8") as fh:
            json.dump(keep, fh, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        print("i18n      docs/i18n/%s.json  %d strings" % (lang, len(keep)))


LINK_RE = re.compile(r"""(["'])([^"'#?{}<>]+)\.dc\.html((?:#[^"'{}<>]*)?)\1""")
SITE_RE = re.compile(r"""(["'])https://everyone\.ai/([^"'#?{}<> ]*?)/?((?:[#?][^"'{}<> ]*)?)\1""")
WP_RE = re.compile(r"""https://everyone\.ai/(wp-content/uploads/[^"'\\ )<>]+)""")
# Left absolute: SEO head, JSON-LD, and a page URL held in a JS constant (the Open Letter
# share buttons pass it to LinkedIn / Facebook / X, which need a full URL).
PROTECT_RE = re.compile(
    r"<helmet>.*?</helmet>|<script type=\"application/ld\+json\">.*?</script>"
    r"|\b(?:const|let|var)\s+\w+\s*=\s*[\"']https://everyone\.ai/[^\"']*[\"']", re.S)


_SRC_CACHE = {}


def has_anchor(slug, anchor):
    """True when the Design source of `slug` declares id=<anchor>."""
    if slug not in _SRC_CACHE:
        design = next(p["design"] for p in PAGES if p["slug"] == slug)
        with open(os.path.join(SRC, design), encoding="utf-8") as f:
            _SRC_CACHE[slug] = f.read()
    t = _SRC_CACHE[slug]
    return bool(re.search(r"""id\s*[=:]\s*["']%s["']""" % re.escape(anchor), t))


LANG_CHEVRON = ('<svg width="9" height="9" viewBox="0 0 10 10" aria-hidden="true"><path d="M2 3.5l3 3 3-3" '
                'fill="none" stroke="currentColor" strokeWidth="1.5"></path></svg>')


def unify_header(html):
    """Give the shared SiteHeader the same desktop "Our Initiatives" menu as Home.

    Design ships two menus: Home opens "AIA / CALIBER" and "AIA Safety Builder" in a
    fly-out next to "AIA Evaluation"; SiteHeader (the 14 other pages) lists them indented
    in one column. The Home version is the reference. Its dropdown markup is copied from
    Home.dc.html at build time, so a change to the Home menu in Design carries over, and
    the three state hooks it needs (aiaOpen / openAia / closeAia) are added to the
    SiteHeader logic. Inert once SiteHeader has the fly-out itself.
    """
    if "aiaOpen" in html:
        return html
    home = open(os.path.join(SRC, "Home.dc.html"), encoding="utf-8").read()
    m = re.search(r'<sc-if value="\{\{ initOpen \}\}".*?</sc-if>(?=\n</div>\n<a href="Newsroom\.dc\.html")', home, re.S)
    if not m or "aiaOpen" not in m.group(0):
        raise SystemExit("unify_header: Initiatives dropdown not found in Home.dc.html")
    block = m.group(0)
    html, n = re.subn(r'<sc-if value="\{\{ initOpen \}\}".*?</sc-if>', lambda _: block, html, count=1, flags=re.S)
    edits = [
        ("initOpen: false,", "initOpen: false, aiaOpen: false,"),
        ("initOpen: s.initOpen,", "initOpen: s.initOpen, aiaOpen: s.aiaOpen,"),
        ("closeInit: () => this.setState({ initOpen: false }),",
         "closeInit: () => this.setState({ initOpen: false, aiaOpen: false }),\n"
         "      openAia: () => this.setState({ aiaOpen: true }),\n"
         "      closeAia: () => this.setState({ aiaOpen: false }),"),
    ]
    for old, new in edits:
        if html.count(old) != 1:
            raise SystemExit("unify_header: expected exactly one %r in SiteHeader.dc.html" % old)
        html = html.replace(old, new)
    if n != 1:
        raise SystemExit("unify_header: Initiatives dropdown not found in SiteHeader.dc.html")
    # Home shows a chevron on the language button; SiteHeader does not.
    html = html.replace("{{ langCode }}</button>", "{{ langCode }}" + LANG_CHEVRON + "</button>", 1)
    return html



def out_path(slug):
    return "index.html" if slug == "index" else slug + "/index.html"


def rewrite_links(html, slug):
    depth = 0 if slug == "index" else slug.count("/") + 1
    prefix = "../" * depth

    def rel(target, frag):
        # Every nested page carries <base href="../"...> pointing at the site root,
        # so links are written root-relative with NO per-page prefix.
        # A fragment on Home keeps its "./": a bare "#mission" is caught by the hash
        # shim as an in-page anchor and does nothing on any page but Home.
        url = "./" if target == "index" else target + "/"
        return url + frag

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
        frag = m.group(3)
        if frag.startswith("#") and not has_anchor(target or "index", frag[1:]):
            # e.g. AIA Method "Read Parts I-V": the parts only exist on the live page.
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
    html = fix_text(rewrite_links(src, slug))

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
    if slug not in COMPONENT_SLUGS:
        head_extra.append(LAND)
    if slot_shim(src):
        head_extra.append(slot_shim(src))
    head_extra.append(I18N_TAG)
    if slug not in COMPONENT_SLUGS:
        head_extra.append(STICKY_TAG)
    head_extra.append(MOBILE_CSS)

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
        if slug == "SiteHeader":
            src = unify_header(src)
        html = rewrite_links(src, "index")
        html = html.replace("<html>", '<html lang="en">', 1)
        html = html.replace("<meta charset=\"utf-8\">\n", '<meta charset="utf-8">\n<meta name="robots" content="noindex">\n', 1)
        with open(os.path.join(OUT, comp), "w", encoding="utf-8", newline="") as f:
            f.write(html)
        print("component %s" % os.path.join("docs", comp))

    emit_i18n()
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
