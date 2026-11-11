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
import html as H
import json, os, re, shutil, sys

from PIL import Image
from urllib.parse import unquote

_HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.getcwd()
SRC = os.path.join(REPO, "src")
EXTRA = os.path.join(_HERE, "extra-pages")  # pages Design does not have yet (same format as src/)
OUT = os.path.join(REPO, "docs")
PREVIEW = "--preview" in sys.argv

DATA = json.load(open(os.path.join(_HERE, "pages.json"), encoding="utf-8"))
CONFIG = json.load(open(os.path.join(_HERE, "site-config.json"), encoding="utf-8"))
IMAGE_MAP = {}
_map_file = os.path.join(_HERE, "image-map.json")
if os.path.exists(_map_file):
    IMAGE_MAP = json.load(open(_map_file, encoding="utf-8"))
HD_MAP = {}
_hd_file = os.path.join(_HERE, "hd-images.json")
if os.path.exists(_hd_file):
    HD_MAP = {k: v["file"] for k, v in json.load(open(_hd_file, encoding="utf-8")).items()
              if not k.startswith("_") and os.path.exists(os.path.join(REPO, "docs", v["file"]))}
# Languages hidden from the selector and from hreflang, translations kept (team decision
# 2026-11-03: no Chinese for now). Re-enable by removing the code from this list.
DISABLED_LANGS = CONFIG.get("disabledLanguages", [])
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
    '#dc-root [style*="text-align:justify"]{text-align:left!important}'
    # Banners: on a phone the picture keeps its left third, so the title gets a little more room.
    '[data-eai-banner-text]{max-width:64%!important;padding:12px 14px!important}}</style>'
)
I18N_TAG = '<script src="eai-i18n.js" defer></script>'
FORMS_TAG = ('<script>window.EAI_FORMS=%s;</script><script src="eai-forms.js" defer></script>'
             % json.dumps({k: CONFIG[k] for k in ("contactEmail", "formEndpoint", "formTabs", "newsletter")}))
GIVEBUTTER_TAG = '<script async src="https://widgets.givebutter.com/latest.umd.cjs?acct=%s&p=wordpress"></script>' % CONFIG["givebutterAccount"]
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
    shutil.copyfile(os.path.join(_HERE, "forms-overlay.js"), os.path.join(OUT, "eai-forms.js"))
    catalog = None
    if os.path.exists(os.path.join(src_dir, "en.json")):
        catalog = set(json.load(open(os.path.join(src_dir, "en.json"), encoding="utf-8"))["units"])
    for lang in DATA.get("languages", [])[1:]:
        f = os.path.join(src_dir, lang + ".json")
        full = json.load(open(f, encoding="utf-8")) if os.path.exists(f) else {}
        # A translation must keep the segment count of its key or the overlay ignores it.
        keep = {k: v for k, v in full.items()
                if (catalog is None or k in catalog) and v and v != k and k.count("\n") == v.count("\n")}
        keep = {k: fix_language(v, lang) for k, v in keep.items()}
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


def source_path(design):
    """Design snapshot first, so a page added in Design replaces its extra-pages copy."""
    path = os.path.join(SRC, design)
    return path if os.path.exists(path) else os.path.join(EXTRA, design)


# Content overrides that belong in Design. Each one goes inert once Design has the new
# text: a pattern that no longer matches is only reported.
PATCHES = json.load(open(os.path.join(_HERE, "page-patches.json"), encoding="utf-8"))["patches"]
NAV_LABELS = {"fr": "Contact", "es": "Contacto", "de": "Kontakt", "nl": "Contact",
              "it": "Contatti", "pt": "Contacto", "zh": "联系我们"}
BANNER_CTA = {"fr": "Découvrir AïA Safety Builder", "es": "Descubrir AïA Safety Builder",
              "de": "AïA Safety Builder entdecken", "nl": "Ontdek AïA Safety Builder",
              "it": "Scopri AïA Safety Builder", "pt": "Descobrir o AïA Safety Builder",
              "zh": "了解 AïA Safety Builder"}

PUB_CTA = {"fr": "Lire le rapport Mapping", "es": "Leer el informe Mapping", "de": "Mapping-Bericht lesen",
           "nl": "Lees het Mapping-rapport", "it": "Leggi il report Mapping",
           "pt": "Ler o relatório Mapping", "zh": "阅读 Mapping 报告"}


# Home wording that Design has not caught up with, per language (see port-live-content.py).
HOME_DICT = json.load(open(os.path.join(_HERE, "home-dict.json"), encoding="utf-8"))
LANGUAGE_FIXES = json.load(open(os.path.join(_HERE, "language-fixes.json"), encoding="utf-8"))


def fix_language(text, lang):
    for table in (LANGUAGE_FIXES["all"], LANGUAGE_FIXES[lang]):
        for old in sorted(table, key=len, reverse=True):
            text = text.replace(old, table[old])
    return text


def apply_patches(html, design):
    for p in PATCHES:
        if p["file"] != design:
            continue
        if "replace_file" in p:
            body = open(os.path.join(_HERE, p["replace_file"]), encoding="utf-8").read()
            html, n = re.subn(p["find"], lambda m: body + (m.group(1) if m.re.groups else ""), html, flags=re.S)
        else:
            html, n = re.subn(p["find"], p["replace"], html, flags=re.S)
        if not n:
            print("patch inert (%s): %s" % (design, p["find"][:60]))
    if design in ("Home.dc.html", "SiteHeader.dc.html", "SiteFooter.dc.html"):
        html = add_contact_links(html)
    html = html.replace("mailto:eai-contact-email", "mailto:" + CONFIG["contactEmail"])
    html = html.replace(">eai-contact-email<", ">" + CONFIG["contactEmail"] + "<")
    address = CONFIG["address"]
    html = html.replace("<!--eai-address-->", (
        '<h2 style="margin:28px 0 0;font:600 18px/1.3 \'Open Sans\',sans-serif;color:#000">Postal address</h2>'
        '<p style="margin:10px 0 0;font:300 16px/1.7 \'Open Sans\',sans-serif">%s</p>' % address) if address else "")
    if address and design in ("Home.dc.html", "SiteFooter.dc.html"):
        html = html.replace("</footer>", (
            '<p style="margin:16px auto 0;text-align:center;font:300 13px/1.7 \'Open Sans\',sans-serif;'
            'color:rgba(255,255,255,.88)">%s</p>\n</footer>' % address), 1)
    # Sharper originals for images Design exported too small (full path: same base names).
    for old, new in HD_MAP.items():
        html = re.sub(r"(?<![\w/.-])%s(?=[\"'?)\s])" % re.escape(old), new, html)
    html = disable_languages(html)
    # By file name: some pages join a base path and a name in JS.
    for old, new in IMAGE_MAP.items():
        html = html.replace(os.path.basename(old), os.path.basename(new))
    html = html.replace("assets/og-cover.png", CONFIG["ogImage"])
    html = add_image_ratios(html)
    # Hidden <x-dc> templates are real HTML: the browser fetched src="{{ m.photo }}" and
    # logged 404s. support.js restores the attribute when it reads the template.
    return re.sub(r'\bsrc="(\{\{[^"]*\}\})"', r'data-eai-src="\1"', html)


_RATIO = {}


def add_image_ratios(html):
    """Reserve each local image's box before it loads (Julien's kanban, card T5).

    Only <img> tags with a literal assets/ path and no width attribute or aspect-ratio. It adds
    the CSS aspect-ratio "auto W / H", not width/height attributes: the attributes also set a
    height that would stretch the many images styled width:100% without height:auto, while
    aspect-ratio only applies where the page leaves the height free, and "auto" hands over to
    the real file once it has loaded. Images whose src is a template ({{ }}) are not touched.
    """
    def ratio(path):
        if path not in _RATIO:
            try:
                with Image.open(os.path.join(OUT, path)) as im:
                    _RATIO[path] = im.size
            except (OSError, ValueError):
                _RATIO[path] = None
        return _RATIO[path]

    def one(m):
        tag = m.group(0)
        if re.search(r"\swidth=", tag) or "aspect-ratio" in tag:
            return tag
        size = ratio(unquote(m.group(1)))
        if not size:
            return tag
        css = "aspect-ratio:auto %d / %d;" % size
        if re.search(r'\sstyle="', tag):
            return re.sub(r'(\sstyle=")', lambda s: s.group(1) + css, tag, count=1)
        return tag[:4] + ' style="%s"' % css + tag[4:]

    return re.sub(r'<img\b[^>]*?\ssrc="(assets/[^"{}]+)"[^>]*>', one, html)


SOCIAL_KEYS = ("og:type", "og:site_name", "og:title", "og:description", "og:url", "og:image",
               "twitter:card", "twitter:image")


def add_social_meta(html):
    """Give every page the sharing tags the Home page has (Julien's kanban, card S4).

    Only Home carried og: and twitter: tags, so a shared link to any other page showed a bare
    URL. Each missing tag is built from what the page already has: its <title>, meta
    description and canonical URL, plus the site's sharing image. Tags a page sets are kept.
    """
    head, sep, rest = html.partition("<body")
    if not sep:
        return html
    title = re.search(r"<title>([^<]*)</title>", head)
    desc = re.search(r'<meta name="description" content="([^"]*)"', head)
    url = re.search(r'<link rel="canonical" href="([^"]*)"', head)
    image = "https://everyone.ai/" + CONFIG["ogImage"]
    values = {"og:type": "website", "og:site_name": "everyone.AI",
              "og:title": title and title.group(1).strip(), "og:description": desc and desc.group(1),
              "og:url": url and url.group(1), "og:image": image,
              "twitter:card": "summary_large_image", "twitter:image": image}
    tags = []
    for key in SOCIAL_KEYS:
        attr = "name" if key.startswith("twitter:") else "property"
        if not values[key] or re.search(r'<meta (?:property|name)="%s"' % re.escape(key), head):
            continue
        tags.append('<meta %s="%s" content="%s">' % (attr, key, values[key].replace('"', "&quot;")))
    if not tags:
        return html
    head = head.replace("</head>", "\n".join(tags) + "\n</head>", 1)
    return head + sep + rest


BANNERS = {k: v for k, v in json.load(open(os.path.join(_HERE, "banners.json"), encoding="utf-8")).items()
           if not k.startswith("_")}
HERO_RE = re.compile(r'(SiteHeader"[^>]*></dc-import>\s*)<section style="background:#35425b;padding:[^"]*;'
                     r'text-align:center">(.*?)</section>', re.S)
SR_ONLY = "position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap;margin:0"


def apply_banner(html, design):
    """Turn the page's dark title section into Gaelle's banner (banners.json).

    The banner (1455 x 190) is drawn at its own ratio: the section is 13.06vw high, so the
    picture spans the full width with nothing cropped, down to a 120 px floor on phones where
    it keeps its left part. The banner colour (#34435b) fills whatever is left. The old H1 text
    stays the H1 unless banners.json gives another title, in which case it moves under the
    banner as a subtitle; logos the banner already shows are dropped.
    """
    conf = BANNERS.get(design)
    if not conf:
        return html
    m = HERO_RE.search(html)
    if not m:
        print("banner inert (%s): no title section found" % design)
        return html
    inner = m.group(2)
    if conf.get("dropLogo"):
        inner = re.sub(r"\s*<img [^>]*>", "", inner, count=1)
    h1 = re.search(r"<h1 [^>]*>(.*?)</h1>", inner, re.S)
    old = h1.group(1).strip() if h1 else ""
    title = conf.get("title", old)
    keep = ""
    if h1 and title != old and not conf.get("full"):
        keep = ('<p style="margin:0;font:600 clamp(18px,2.2vw,28px)/1.3 Poppins,sans-serif;color:#35425b;'
                'text-transform:uppercase;letter-spacing:.04em">%s</p>' % old)
    rest = (inner[:h1.start()] + keep + inner[h1.end():]) if h1 else inner
    # The band under the banner is the page colour (Gaelle, 11 Nov), so its white and pale-blue
    # paragraph text turns dark; buttons keep their own colours.
    rest = re.sub(r'(<p [^>]*?color:)(?:#fff|#cfd8ea)\b', lambda t: t.group(1) + "#35425b", rest)
    if conf.get("full"):
        banner = ('<section data-eai-banner="" style="position:relative;background:#324973">'
                  '<h1 style="%s">%s</h1>'
                  '<img src="%s" alt="iRAISE, International Research-driven Alliance for AI Serving Every child, '
                  'an initiative by the Paris Peace Forum and everyone.AI" fetchpriority="high" '
                  'style="display:block;width:100%%;max-width:1455px;height:auto;margin:0 auto"></section>'
                  % (SR_ONLY, old or "International Coalition", conf["img"]))
    else:
        caps = "text-transform:uppercase;" if conf.get("caps") else ""
        sub = ('<p style="margin:6px 0 0;font:500 clamp(14px,1.5vw,22px)/1.3 Poppins,sans-serif;color:#fff">%s</p>'
               % conf["sub"]) if conf.get("sub") else ""
        banner = ('<section data-eai-banner="" style="position:relative;overflow:hidden;background:#34435b;'
                  'min-height:clamp(120px,13.06vw,260px);display:flex;align-items:center;justify-content:flex-end">'
                  '<img src="%s" alt="" fetchpriority="high" style="position:absolute;left:0;top:0;height:100%%;'
                  'width:auto;max-width:none">'
                  '<div data-eai-banner-text="" style="position:relative;max-width:62%%;padding:16px 4.1vw 16px 24px;'
                  'box-sizing:border-box;text-align:right">'
                  '<h1 style="margin:0;font:600 clamp(22px,2.9vw,46px)/1.15 Poppins,sans-serif;color:#fff;'
                  'letter-spacing:.03em;%s">%s</h1>%s</div></section>' % (conf["img"], caps, title, sub))
    if rest.strip():
        banner += ('\n<section style="background:#f0f2f6;padding:36px 20px 0;text-align:center">%s</section>'
                   % rest)
    return html[:m.start()] + m.group(1) + banner + html[m.end():]


DESCRIPTIONS = {k: v for k, v in json.load(open(os.path.join(_HERE, "descriptions.json"), encoding="utf-8")).items()
                if not k.startswith("_")}


def set_description(html, slug):
    """Use the reviewed description from descriptions.json for the page's meta description and
    its sharing copies (Julien's kanban, card S2). Both copies are rewritten: the static head,
    and the <helmet> block the runtime mounts into the head again on load, which would otherwise
    bring the old description back as a second tag."""
    if slug not in DESCRIPTIONS:
        return html
    value = H.escape(DESCRIPTIONS[slug], quote=True)
    pattern = r'(<meta (?:name="description"|property="og:description"|name="twitter:description") content=")[^"]*(")'
    head, sep, rest = html.partition("<body")
    head = re.sub(pattern, lambda m: m.group(1) + value + m.group(2), head)
    rest = re.sub(r"<helmet>.*?</helmet>",
                  lambda h: re.sub(pattern, lambda m: m.group(1) + value + m.group(2), h.group(0)), rest, flags=re.S)
    return head + sep + rest


# Report pages: what the page text states. No date where the page gives none; no person where
# the report names none (the organisation is then the author).
REPORTS = {
    "research/human-centredailiteracy": {"authors": ["Maxime Le Bourgeois", "Mathilde Cerioli", "Yann Bonnet"], "date": "2026-11"},
    "research/mapping-of-genai-impacts": {"authors": ["Mathilde Cerioli", "Daniel Hipp"]},
    "research/adolescents-and-anthropomorphic-ai": {"authors": ["Mathilde Cerioli"]},
    "research/the-future-of-child-development-in-the-ai-era": {"date": "2024-05"},
    "research/relational-positioning-dependency-exclusivity-policy-rpd": {},
}
ORG = {"@id": "https://everyone.ai/#org"}


def add_structured_data(html, slug):
    """Give every page a JSON-LD WebPage tied to the organisation, and report pages a Report
    (Julien's kanban, card G2: only Home had structured data). A page that already has JSON-LD
    in its head (Home) is left as it is; the NGO node itself is declared on Home only and
    referenced here by @id.
    """
    head, sep, rest = html.partition("<body")
    if not sep or "application/ld+json" in head:
        return html
    title = re.search(r"<title>([^<]*)</title>", head)
    desc = re.search(r'<meta name="description" content="([^"]*)"', head)
    url = re.search(r'<link rel="canonical" href="([^"]*)"', head)
    if not (title and url):
        return html
    name = re.sub(r"\s*\|\s*everyone\.AI\s*$", "", H.unescape(title.group(1)).strip(), flags=re.I)
    page = {"@type": "WebPage", "@id": url.group(1) + "#webpage", "url": url.group(1), "name": name,
            "inLanguage": "en", "isPartOf": {"@id": "https://everyone.ai/#website"}, "about": ORG,
            "publisher": ORG}
    if desc:
        page["description"] = H.unescape(desc.group(1))
    graph = [page]
    if slug in REPORTS:
        meta = REPORTS[slug]
        report = {"@type": "Report", "@id": url.group(1) + "#report", "name": name, "url": url.group(1),
                  "inLanguage": "en", "publisher": ORG, "mainEntityOfPage": {"@id": page["@id"]},
                  "author": [{"@type": "Person", "name": a} for a in meta.get("authors", [])] or ORG}
        if desc:
            report["description"] = page["description"]
        if meta.get("date"):
            report["datePublished"] = meta["date"]
        pdf = re.search(r'href="(assets/wp-content/[^"]+\.pdf)"', rest)
        if pdf:
            report["encoding"] = {"@type": "MediaObject", "encodingFormat": "application/pdf",
                                  "contentUrl": "https://everyone.ai/" + pdf.group(1)}
        graph.append(report)
    block = '<script type="application/ld+json">%s</script>' % json.dumps(
        {"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False).replace("</", "<\\/")
    return head.replace("</head>", block + "\n</head>", 1) + sep + rest


def disable_languages(text):
    """Drop disabled languages from every language list (selector, hreflang, og:locale).

    Only the entries that offer the language go; its translations stay in place, so a
    language comes back by removing it from site-config.json disabledLanguages.
    A visitor whose stored or browser language is disabled falls back to English, because
    both language runtimes accept only codes still listed.
    """
    for code in DISABLED_LANGS:
        c = re.escape(code)
        text = re.sub(r",\s*\['%s',\s*'[^']*'\]" % c, "", text)
        text = re.sub(r",\s*\{\s*code:\s*'%s',\s*name:\s*'[^']*'\s*\}" % c, "", text)
        text = re.sub(r'\s*<link rel="alternate" hreflang="%s"[^>]*>' % c, "", text)
        text = re.sub(r'\s*<meta property="og:locale:alternate" content="%s_[A-Z]{2}">' % c, "", text)
    return text


def add_contact_links(html):
    """Add Contact to the main menu (Google Ad Grants: Contact one click from every page)."""
    html = html.replace("nav: { home: 'Home',", "nav: { contact: 'Contact', home: 'Home',")
    html = html.replace("['zh', '中文']", "['zh', '简体中文']")
    html = html.replace("code: 'zh', name: '中文'", "code: 'zh', name: '简体中文'")
    html = re.sub(r'<a href="About\.dc\.html"[^>]*>\{\{ t\.nav\.about \}\}</a>',
                  lambda m: m.group(0) + "\n" + m.group(0).replace("About.dc.html", "Contact.dc.html")
                  .replace("t.nav.about", "t.nav.contact"), html)
    html = re.sub(r"(\{ label: n\.about, href: '[^']*', k: 'about' \})",
                  r"\1,\n      { label: n.contact, href: 'Contact.dc.html', k: 'contact' }", html)
    html = html.replace('href="Home.dc.html#contact"', 'href="Contact.dc.html"')
    html = re.sub(r'href="#contact"( style="[^"]*" style-hover="[^"]*">\{\{ t\.footer\.contact)',
                  r'href="Contact.dc.html"\1', html)
    return html


def patch_runtime():
    """Patch the two runtime files published as they are by the Design export."""
    path = os.path.join(OUT, "support.js")
    t = open(path, encoding="utf-8").read()
    if "data-eai-src" not in t:
        old = "tpl.innerHTML = encodeCase(html);"
        if t.count(old) != 1:
            raise SystemExit("patch_runtime: template compile not found in support.js")
        t = t.replace(old, 'tpl.innerHTML = encodeCase(html).replace(/\\bdata-eai-src=/g, "src=");')
        open(path, "w", encoding="utf-8", newline="").write(t)
    path = os.path.join(OUT, "i18n-site.js")
    t = open(path, encoding="utf-8").read()
    open(path, "w", encoding="utf-8", newline="").write(disable_languages(t.replace("name: '中文'", "name: '简体中文'")))
    path = os.path.join(OUT, "i18n-home.js")
    t = open(path, encoding="utf-8").read()
    for lang, label in NAV_LABELS.items():
        m = re.search(r"\n\s*'?%s'?: \{" % lang, t)
        if not m:
            raise SystemExit("patch_runtime: language %s not found in i18n-home.js" % lang)
        head, tail = t[:m.start()], t[m.start():]
        if "nav: { contact:" not in tail.split("nav: {", 1)[0] + tail[tail.find("nav: {"):tail.find("nav: {") + 20]:
            tail = tail.replace("nav: {", "nav: { contact: '%s'," % label, 1)
        tail = re.sub(r"(ann: \{ text: (?:'[^']*'|\"[^\"]*\"), cta: )(?:'[^']*'|\"[^\"]*\")",
                      lambda x: x.group(1) + repr(BANNER_CTA[lang]), tail, count=1)
        tail = re.sub(r"(\n\s*pub: \{[^\n]*?cta: )(?:'[^']*'|\"[^\"]*\")",
                      lambda x: x.group(1) + repr(PUB_CTA[lang]), tail, count=1)
        fields = HOME_DICT.get(lang, {})
        for field, value in fields.items():
            if field == "status":
                if "mission: { status:" not in tail:
                    tail = tail.replace("mission: {", "mission: { status: %r," % value, 1)
                continue
            tail = re.sub(r"\b%s: (?:'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\")" % field,
                          lambda x: "%s: %r" % (field, value), tail, count=1)
        next_lang = re.search(r"\n\s*'?(?:%s)'?: \{" % "|".join(NAV_LABELS), tail[2:])
        cut = next_lang.start() + 2 if next_lang else len(tail)
        t = head + fix_language(tail[:cut], lang) + tail[cut:]
    open(path, "w", encoding="utf-8", newline="").write(disable_languages(t))


_SRC_CACHE = {}


def has_anchor(slug, anchor):
    """True when the Design source of `slug` declares id=<anchor>."""
    if slug not in _SRC_CACHE:
        design = next(p["design"] for p in PAGES if p["slug"] == slug)
        with open(source_path(design), encoding="utf-8") as f:
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
    # A file that was not localized stays hotlinked (the launch video, until it moves to
    # YouTube): rewriting it anyway pointed the player at a local 404.
    body = WP_RE.sub(lambda m: "assets/" + m.group(1)
                     if os.path.exists(os.path.join(OUT, "assets", unquote(m.group(1)))) else m.group(0), body)
    return re.sub("\x00(\\d+)\x00", lambda m: held[int(m.group(1))], body)


def build_page(page):
    slug = page["slug"]
    src = apply_banner(apply_patches(open(source_path(page["design"]), encoding="utf-8").read(), page["design"]),
                       page["design"])
    depth = 0 if slug == "index" else slug.count("/") + 1
    html = fix_text(rewrite_links(src, slug))

    m = re.search(r"<helmet>(.*?)</helmet>", html, re.S)
    helmet = m.group(1).strip("\n") if m else ""
    head_extra = []
    if depth:
        head_extra.append('<base href="%s">' % ("../" * depth))
    if helmet and "<title>" not in html.split("<body", 1)[0]:
        head_extra.append(helmet)
        # The runtime also mounts <helmet> into <head>, and crawlers read the JSON-LD left in
        # the body copy, so Home declared its NGO graph twice. The head copy is the one kept.
        if "application/ld+json" in helmet:
            html = re.sub(r"(<helmet>.*?)<script type=\"application/ld\+json\">.*?</script>\n?(.*?</helmet>)",
                          r"\1\2", html, count=1, flags=re.S)
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
        head_extra.append(FORMS_TAG)
    if slug == "donate":
        head_extra.append(GIVEBUTTER_TAG)
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
    if slug not in COMPONENT_SLUGS:
        html = set_description(html, slug)
        html = add_social_meta(html)
        html = add_structured_data(html, slug)

    dest = os.path.join(OUT, out_path(slug))
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "w", encoding="utf-8", newline="") as f:
        f.write(html)
    return dest


COMPONENT_SLUGS = {c[: -len(".dc.html")] for c in COMPONENTS}


SLOT_ALT_MARK = "/* eai: alt from attribute */"


def patch_image_slot():
    """Give image-slot pictures a text alternative (Julien's kanban S5, 11 Nov).

    Design's image-slot.js draws the picture as <img alt=""> inside its shadow root, so every slot
    image (report covers, AIA photos, Newsroom thumbnails) read as decorative. The picture now
    takes the slot's alt attribute, or failing that its placeholder caption without the
    "Photo -" prefix. image-slot.js comes from the Design pull, so the patch is reapplied here.
    """
    path = os.path.join(OUT, "image-slot.js")
    if not os.path.exists(path):
        return
    js = open(path, encoding="utf-8").read()
    if SLOT_ALT_MARK in js:
        return
    a = "      return ['shape', 'radius', 'mask', 'fit', 'placeholder', 'src', 'id', 'credit', 'credit-href'];"
    b = "    _render() {"
    if a not in js or b not in js:
        print("image-slot alt patch inert: image-slot.js changed")
        return
    js = js.replace(a, a.replace("'credit-href']", "'credit-href', 'alt']"), 1)
    js = js.replace(b, b + "\n      " + SLOT_ALT_MARK + " if (this._img) this._img.alt = this.getAttribute('alt') || "
                    "(this.getAttribute('placeholder') || '').replace(/^Photo\\s*[\u2014-]\\s*/, '');", 1)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(js)


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

    patch_image_slot()
    for page in PAGES:
        d = build_page(page)
        print("page      %s" % os.path.relpath(d, REPO))

    for comp in COMPONENTS:
        slug = comp[: -len(".dc.html")]
        src = open(os.path.join(SRC, comp), encoding="utf-8").read()
        if slug == "SiteHeader":
            src = unify_header(src)
        src = apply_patches(src, comp)
        src = fix_text(src)
        html = rewrite_links(src, "index")
        html = html.replace("<html>", '<html lang="en">', 1)
        html = html.replace("<meta charset=\"utf-8\">\n", '<meta charset="utf-8">\n<meta name="robots" content="noindex">\n', 1)
        with open(os.path.join(OUT, comp), "w", encoding="utf-8", newline="") as f:
            f.write(html)
        print("component %s" % os.path.join("docs", comp))

    emit_i18n()
    patch_runtime()
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
