#!/usr/bin/env python3
"""One-off: port the AIA Method document and the secondary WordPress pages.

    python3 .claude/skills/sync-site/port-live-pages.py <dir of saved live pages>

Run from the repo root, before the DNS switch, after port-live-content.py. Writes pages to
extra-pages/, the full Method document to extra-pages/fragments/, figures to
docs/assets/ported/method/, and registers everything in pages.json, sitemap.xml, llms.txt.
"""
import html, importlib.util, json, os, re, sys
from html.parser import HTMLParser

HERE = os.path.dirname(os.path.abspath(__file__))
LIVE = sys.argv[1]
_s = open(os.path.join(HERE, "port-live-content.py"), encoding="utf-8").read().split("patches = []")[0]
exec(_s)  # helpers only: image(), fragment(), live()
EXTRA = os.path.join(HERE, "extra-pages")
KEEP = {"p", "ul", "ol", "li", "table", "thead", "tbody", "tr", "th", "td", "br", "sup", "sub"}
INLINE = {"strong": "strong", "b": "strong", "em": "em", "i": "em"}
DOC_CSS = ("[data-eai-doc] h2{margin:56px 0 0;font:600 30px/1.25 'Open Sans',sans-serif;color:#000;scroll-margin-top:110px}"
           "[data-eai-doc] h3{margin:36px 0 0;font:700 21px/1.35 'Open Sans',sans-serif;color:#829bcb;scroll-margin-top:110px}"
           "[data-eai-doc] h4{margin:28px 0 0;font:700 18px/1.35 'Open Sans',sans-serif;color:#35425b;scroll-margin-top:110px}"
           "[data-eai-doc] h5{margin:22px 0 0;font:700 16px/1.35 'Open Sans',sans-serif;color:#35425b;scroll-margin-top:110px}"
           "[data-eai-doc] p,[data-eai-doc] li{font:300 17px/1.8 'Open Sans',sans-serif}[data-eai-doc] p{margin:14px 0 0}"
           "[data-eai-doc] ul,[data-eai-doc] ol{margin:14px 0 0;padding-left:22px}"
           "[data-eai-doc] strong{font-weight:700}[data-eai-doc] img{display:block;max-width:100%;height:auto;margin:24px auto 0;border-radius:6px}"
           "[data-eai-doc] [data-eai-table]{margin:20px 0 0;overflow-x:auto}"
           "[data-eai-doc] table{border-collapse:collapse;width:100%;background:#fff;font:400 14px/1.5 'Open Sans',sans-serif}"
           "[data-eai-doc] th,[data-eai-doc] td{border:1px solid #dfe4ee;padding:8px 10px;text-align:left;vertical-align:top}"
           "[data-eai-doc] th{background:#35425b;color:#fff;font-weight:600}")


def level(text, ident):
    t = text.strip()
    if t.startswith("Part ") or ident in ("executive-summary", "introduction", "future-directions"):
        return 2
    m = re.match(r"(\d+)\s*\.\s*(\d+)?\s*\.?\s*(\d+)?", t)
    if not m:
        return 3
    return 3 + sum(1 for g in m.groups()[1:] if g)


class Doc(HTMLParser):
    """Keep structure and text; drop WordPress wrappers, spans, classes and inline styles."""

    def __init__(self, figures=None):
        super().__init__(convert_charrefs=True)
        self.out, self.toc, self.seen = [], [], set()
        self.pid, self.head, self.buf, self.figures, self.skip = None, False, "", figures, 0

    def handle_starttag(self, t, a):
        d = dict(a)
        if t in ("script", "style", "button", "form"):
            self.skip += 1
            return
        if self.skip:
            return
        if d.get("id") and t not in ("img",):
            self.pid = d["id"].strip()
        if t in ("h1", "h2", "h3", "h4", "h5"):
            self.head, self.buf = True, ""
        elif t == "img":
            src = d.get("data-src", "")
            if self.figures is not None and src and "/uploads/2026/09/" in src and "Banner" not in src:
                self.out.append('<img src="%s" alt="%s" loading="lazy">' % (self.figures(src), html.escape(d.get("alt") or "Figure", True)))
        elif t == "a":
            href = (d.get("href") or "").strip()
            self.emit('<a href="%s"%s>' % (html.escape(href, True), ' target="_blank" rel="noopener"' if href.startswith("http") else "") if href else "<a>")
        elif t in INLINE:
            self.emit("<%s>" % INLINE[t])
        elif t == "table":
            self.out.append('<div data-eai-table=""><table>')
        elif t in ("td", "th") and d.get("colspan"):
            self.emit('<%s colSpan="%s">' % (t, d["colspan"]))
        elif t == "tr" and "category" in (d.get("class") or ""):
            self.emit('<tr style="background:#f0f2f6;font-weight:700">')
        elif t in KEEP:
            self.emit("<%s>" % t if t != "br" else "<br>")

    def handle_endtag(self, t):
        if t in ("script", "style", "button", "form"):
            self.skip = max(0, self.skip - 1)
            return
        if self.skip:
            return
        if t in ("h1", "h2", "h3", "h4", "h5") and self.head:
            self.head = False
            text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", self.buf)).strip()
            if text:
                n, ident = level(text, self.pid), self.pid
                self.pid = None
                attr = ' id="%s"' % ident.replace(" ", "") if ident else ""
                self.out.append("<h%d%s>%s</h%d>" % (n, attr, text, n))
                if ident:
                    self.toc.append((n, text, ident.replace(" ", "")))
        elif t == "a":
            self.emit("</a>")
        elif t in INLINE:
            self.emit("</%s>" % INLINE[t])
        elif t == "table":
            self.out.append("</table></div>")
        elif t in KEEP and t != "br":
            self.emit("</%s>" % t)

    def emit(self, s):
        if self.head:
            return
        self.out.append(s)

    def handle_data(self, d):
        if self.skip:
            return
        if self.head:
            self.buf += d
        elif d.strip():
            self.out.append(html.escape(re.sub(r"\s+", " ", d), False))
        elif d and self.out and not self.out[-1].endswith(">"):
            self.out.append(" ")

    def html(self):
        s = "".join(self.out).replace("ßeta", "beta")
        s = re.sub(r"<(strong|em|p|li)>\s*</\1>", "", s)
        s = re.sub(r"<a>(.*?)</a>", r"\1", s)
        # Google Docs pastes wrap a list in empty one-item lists: "1. 1. 1. text".
        for _ in range(3):
            s = re.sub(r"<ol>\s*<li>\s*(<ol>)", r"\1", s)
            s = re.sub(r"(</ol>)\s*</li>\s*</ol>", r"\1", s)
        return re.sub(r"(</(?:p|h\d|ul|ol|li|tr|table|div)>)", r"\1\n", s)


def main_of(name):
    t = live(name)
    a = t.find('id="main-content"')
    return re.sub(r"<!--.*?-->", "", t[a + 18:t.find("<footer", a)], flags=re.S)


# Method ----------------------------------------------------------------------------------
n = [0]


def figure(src):
    n[0] += 1
    return image(src, "method", "figure-%02d" % n[0], 1600)


m = main_of("aia-safety-builder_method")
start = m.rfind("<div", 0, m.find('id="executive-summary"'))
end = m.find("Researchers interested in using")
end = m.rfind("<p", 0, end)
doc = Doc(figure)
doc.feed(m[start:end])
fragment("method-document", '<div data-eai-doc="">\n' + doc.html() + "</div>")
toc = [{"l": "Contributors", "href": "#top"}] + [{"l": re.sub(r"\s+", " ", t).replace("ßeta", "beta"), "href": "#" + i} for lv, t, i in doc.toc if lv <= 3]
print("method:", len(doc.html()), "chars,", n[0], "figures,", len(doc.toc), "anchors,", len(toc), "toc entries, tables", doc.html().count("<table"))

patches = json.load(open(os.path.join(HERE, "page-patches.json"), encoding="utf-8"))
patches["patches"] = [p for p in patches["patches"] if not p.get("method")]
F = "AIA Method.dc.html"
for e in [
    {"file": F, "why": "Full document of the live page: Design has about 15 percent of it.", "find": r'<sc-for list="\{\{ sections \}\}".*?(<p [^>]*>Researchers interested)', "replace_file": "extra-pages/fragments/method-document.html"},
    {"file": F, "why": "Full table of contents.", "find": r"toc: \[.*?\]\n", "replace": "toc: " + json.dumps(toc, ensure_ascii=False).replace("\\", "\\\\") + "\n"},
    {"file": F, "why": "Document styles.", "find": r"</helmet>", "replace": "<style>" + DOC_CSS + "</style>\n</helmet>"},
    {"file": F, "why": "Long table of contents below the sticky menu.", "find": r'(<aside data-toc="" style=")position:sticky;top:20px;', "replace": "\\1position:sticky;top:110px;max-height:calc(100vh - 130px);overflow-y:auto;"},
]:
    e["method"] = True
    patches["patches"].append(e)
json.dump(patches, open(os.path.join(HERE, "page-patches.json"), "w", encoding="utf-8"), indent=2, ensure_ascii=False)
open(os.path.join(HERE, "page-patches.json"), "a").write("\n")

# Secondary pages -------------------------------------------------------------------------
tpl = open(os.path.join(EXTRA, "Contact.dc.html"), encoding="utf-8").read()
tpl = tpl.replace("{", "{").replace("</style>\n</helmet>", DOC_CSS + "</style>\n</helmet>")
BTN = "display:inline-block;margin-top:24px;background:#f8903e;color:#fff;font:500 15px/1 Poppins,sans-serif;padding:13px 26px;border-radius:999px;text-decoration:none"


def embed(vid):
    return ('<div style="margin:28px 0 0;aspect-ratio:16/9;background:#0f1522;border-radius:8px;overflow:hidden"><iframe src="https://www.youtube-nocookie.com/embed/%s" '
            'title="Video" allow="encrypted-media; picture-in-picture" allowFullScreen="allowFullScreen" style="width:100%%;height:100%%;border:0"></iframe></div>' % vid)


def page(design, slug, title, desc, body):
    h = tpl.replace("<title>Contact | Everyone.AI</title>", "<title>%s | Everyone.AI</title>" % title)
    h = re.sub(r'<meta name="description"[^>]*>', lambda _: '<meta name="description" content="%s">' % desc, h)
    h = h.replace("https://everyone.ai/contact/", "https://everyone.ai/%s/" % slug).replace('data-screen-label="Contact"', 'data-screen-label="%s"' % title)
    h = h.replace('active="contact"', 'active=""').replace(">Contact us</h1>", ">%s</h1>" % title)
    h = re.sub(r"<main[\s\S]*?</main>", lambda _: '<main data-eai-doc="" style="flex:1;max-width:820px;width:100%%;margin:0 auto;padding:40px 20px 88px;box-sizing:border-box;color:#333">\n%s\n</main>' % body, h)
    open(os.path.join(EXTRA, design + ".dc.html"), "w", encoding="utf-8").write(h)
    return {"design": design + ".dc.html", "slug": slug, "role": "content"}, title, desc


def cleaned(name, drop_first_h=True):
    d = Doc()
    d.feed(main_of(name))
    seen, out = set(), []
    for line in d.html().split("\n"):
        k = re.sub(r"<[^>]+>", "", line).strip()
        if not k or (k in seen and len(k) > 12) or re.match(r"^(Name|Email Address|Message|Submit|Share On \w+|Share Via Email|\d+ \+ \d+ =)", k):
            continue
        seen.add(k)
        out.append(line)
    return "\n".join(out)


def terms():
    s = re.sub(r"</?ol>\n?", "", cleaned("terms-and-conditions"))
    return re.sub(r"<li><strong>([^<]+)</strong></li>", r"<h3>\1</h3>", s)


def workshop():
    s = cleaned("workshop-dec10th")
    a, b = s.find("<p>8.30 - 8.45 am</p>"), s.find("<p>8.30 - 8.45 am - ")
    return s[:a] + s[b:] if 0 <= a < b else s


pages = [
    page("Terms and Conditions", "terms-and-conditions", "Terms and Conditions", "The terms that apply to the use of the everyone.AI website.", terms()),
    page("AIA Info", "aia-safety-builder/info", "How to read this beta report", "What AïA measures, how scores work and how to read the priority levels of the AïA Safety Builder beta report.", re.sub(r"<(?:p|h\d)>AïA Safety Builder</(?:p|h\d)>\n|<h\d[^>]*>How to read this .eta report</h\d>\n", "", cleaned("aia-safety-builder_info"))),
    page("Workshop Dec 10", "workshop-dec10th", "Beneficial AI for Children: Kickoff with Workshop", "Workshop of December 10 in San Francisco, an official partner event of the Paris AI Action Summit.", workshop()),
    page("Thank You Open Letter", "thank-you-open-letter-le-monde", "So what's next?", "Thank you for signing our open letter.", '<p>Thank you for signing our open letter! Your voice matters in protecting children’s future. Watch the following video to learn more about our actions and how you can help. Consider supporting our work with a donation to help us amplify our impact.</p>\n' + embed("SGpe7B1o4g4") + '\n<p><a href="Donate.dc.html" style="%s">Donate</a></p>' % BTN),
    page("Thank You Webinar", "thank-you-access-webinar", "Please watch the Webinar", "Webinar: The Future of Child Development in the AI Era.", embed("A9HRgwdvivE") + '\n<p>Please reach out if you have any questions.</p>\n<p><a href="Contact.dc.html" style="%s">Contact us</a></p>' % BTN),
    page("Events", "events", "Events", "Past and upcoming events of everyone.AI.", '<p>Our past and upcoming events are listed in the Newsroom.</p>\n<p><a href="Newsroom.dc.html#event" style="%s">See our events</a></p>' % BTN),
    page("Blog", "blog", "Blog", "News and updates from everyone.AI.", '<p>Our latest news, press coverage, podcasts and webinars are in the Newsroom.</p>\n<p><a href="Newsroom.dc.html" style="%s">Go to the Newsroom</a></p>' % BTN),
]
data = json.load(open(os.path.join(HERE, "pages.json"), encoding="utf-8"))
sm = open("docs/sitemap.xml").read()
ll = open("docs/llms.txt").read().rstrip("\n")
for entry, title, desc in pages:
    if not any(p["slug"] == entry["slug"] for p in data["pages"]):
        data["pages"].append(entry)
    url = "https://everyone.ai/%s/" % entry["slug"]
    if url + "<" not in sm:
        sm = sm.replace("</urlset>", "  <url><loc>%s</loc><lastmod>2026-10-31</lastmod><priority>0.3</priority></url>\n</urlset>" % url)
    if "(%s)" % url not in ll:
        ll += "\n- [%s](%s): %s" % (title, url, desc)
json.dump(data, open(os.path.join(HERE, "pages.json"), "w", encoding="utf-8"), indent=2, ensure_ascii=False)
open(os.path.join(HERE, "pages.json"), "a").write("\n")
open("docs/sitemap.xml", "w").write(sm)
open("docs/llms.txt", "w").write(ll + "\n")
