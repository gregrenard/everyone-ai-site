#!/usr/bin/env python3
"""One-off: port content that exists on the WordPress site but not in Claude Design.

Run from the repo root, while everyone.ai still serves WordPress:
    python3 .claude/skills/sync-site/port-live-content.py <dir of saved live pages>

Writes HTML fragments to extra-pages/fragments/, the images to docs/assets/ported/, and the
page patches that use them to page-patches.json (entries tagged "ported": true are replaced
on each run). The committed output is what build.py reads; this script is only kept to show
where the content came from, and stops working after the DNS switch.
"""
import html, io, json, os, re, subprocess, sys
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.getcwd(), "docs")
FRAG = os.path.join(HERE, "extra-pages", "fragments")
LIVE = sys.argv[1]
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
H2 = "margin:0;font:600 36px/1.2 'Open Sans',sans-serif;color:#000"
P = "margin:18px 0 0;font:300 17px/1.8 'Open Sans',sans-serif"
CARD = "background:#fff;border-radius:8px;padding:26px;text-align:center"
H3 = "margin:0;font:700 19px/1.35 'Open Sans',sans-serif"
BTN = "display:inline-block;margin:12px 6px 0;background:#f8903e;color:#fff;font:500 14px/1 Poppins,sans-serif;padding:11px 22px;border-radius:999px;text-decoration:none"
HOVER = 'style-hover="background:#e97f2d;color:#fff"'
SEC = "margin-top:72px"
SECH2 = "margin:0;text-align:center;font:600 34px/1.2 'Open Sans',sans-serif;color:#000"
STRONG = 'style="font-weight:700"'


def live(name):
    return open(os.path.join(LIVE, name + ".html"), errors="ignore").read()


def fetch(url):
    url = html.unescape(url).split("?")[0]
    return subprocess.run(["curl", "-s", "-L", "-m", "40", "-A", UA, "--", url.replace(" ", "%20")],
                          capture_output=True, check=True).stdout


def image(url, sub, name, side):
    """Save a live image under docs/assets/ported/<sub>/ and return its site path."""
    os.makedirs(os.path.join(OUT, "assets", "ported", sub), exist_ok=True)
    data = fetch(url)
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:48]
    if url.split("?")[0].lower().endswith(".svg"):
        rel = "assets/ported/%s/%s.svg" % (sub, base)
        open(os.path.join(OUT, rel), "wb").write(data)
        return rel
    im = Image.open(io.BytesIO(data))
    im = im.convert("RGBA" if im.mode in ("RGBA", "LA", "P") else "RGB")
    im.thumbnail((side, side), Image.LANCZOS)
    rel = "assets/ported/%s/%s.webp" % (sub, base)
    im.save(os.path.join(OUT, rel), "WEBP", quality=82, method=6)
    return rel


def fragment(name, body):
    open(os.path.join(FRAG, name + ".html"), "w", encoding="utf-8").write(body.strip() + "\n")
    return "extra-pages/fragments/%s.html" % name


def shares(page, title):
    u = "https://everyone.ai/%s/" % page
    q = title.replace(" ", "+")
    links = [("Share On LinkedIn", "https://www.linkedin.com/shareArticle?mini=1&amp;url=%s&amp;title=%s" % (u, q)),
             ("Share Via Email", "mailto:?subject=%s&amp;body=%%0D%%0ALink: %s" % (title, u)),
             ("Share On Facebook", "https://www.facebook.com/sharer.php?u=" + u),
             ("Share On X", "https://twitter.com/intent/tweet?text=%s&amp;url=%s" % (q, u))]
    return "".join('<a href="%s" target="_blank" rel="noopener" style="%s" %s>%s</a>' % (h, BTN, HOVER, l) for l, h in links)


def flat(t):
    """Page as text, with links as {url} and images as [IMG url]."""
    a = t.find('id="main-content"')
    b = t.find("<footer", a)
    t = re.sub(r"<(script|style|noscript)[\s\S]*?</\1>", "", t[a:b])
    t = re.sub(r"<img[^>]*>", lambda m: " [IMG " + (re.search(r'data-src="([^"]+)"', m.group(0)) or [0, ""])[1] + "] ", t)
    t = re.sub(r'<a [^>]*href="([^"]+)"[^>]*>', lambda m: " {" + m.group(1).strip() + "} ", t)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", t)))


patches = []


def patch(file, why, find, replace=None, replace_file=None):
    e = {"file": file, "why": why, "find": find, "ported": True}
    if replace_file:
        e["replace_file"] = replace_file
    else:
        e["replace"] = replace
    patches.append(e)


# Home ----------------------------------------------------------------------------------
why = "Current wording of the live home page (audit of 2026-10-30)."
patch("Home.dc.html", why, r"feeds: '[^']*'", "feeds: 'The Scientific Foundation of our Three Pillars'")
patch("Home.dc.html", why, r"p1d: '[^']*'", "p1d: 'Bringing together researchers, industry leaders, governments, international organizations, and civil society to advance Beneficial AI for Children. Through scientific collaboration, policy dialogue, and youth participation, iRAISE translates research into actionable recommendations, standards, and best practices.'")
patch("Home.dc.html", why, r"p2d: '[^']*'", "p2d: \"Translating neuroscience and AI research into practical knowledge through interactive workshops, training sessions, conferences, and educational resources. Our programs help educators, families, companies, and young people understand AI's opportunities and challenges, with a focus on learning, critical thinking, and well-being.\"")
patch("Home.dc.html", why, r"p3d: '[^']*'", "p3d: 'Advancing independent, science-based evaluation of how AI systems interact with children and young people. Through AïA Safety Builder, we assess developmental risk signals and provide measurable indicators to help AI developers and decision-makers improve AI safety and accountability.'")
patch("Home.dc.html", why, r"mission: \{ title:", "mission: { status: '501(c)(3) Nonprofit Organization', title:")
patch("Home.dc.html", why, r"(\{\{ t\.mission\.title \}\}</h2>\n)", "\\1<p style=\"margin:8px 0 0;font:600 14px/1.4 'Open Sans',sans-serif;color:#829bcb;text-transform:uppercase;letter-spacing:.06em\">{{ t.mission.status }}</p>\n")
patch("Home.dc.html", "Link to the Newsroom, as on the live site.", r"(<p style=\"margin:10px 0 0;font:600 14px/1\.4 'Open Sans',sans-serif;color:#829bcb;text-transform:uppercase;letter-spacing:\.06em\">)\{\{ t\.featured\.all \}\}</p>", "\\1<a href=\"Newsroom.dc.html\" style=\"color:inherit;text-decoration:none\">{{ t.featured.all }}</a></p>")

# About ---------------------------------------------------------------------------------
why = "Sections of the live About page missing from Design."
about = fragment("about-intro", f"""
<h2 style="{H2}">Who We Are</h2>
<p style="{P}">everyone.AI is an international, multidisciplinary team bringing together experts in developmental neuroscience, artificial intelligence, education, and public policy.</p>
<p style="margin:14px 0 0;font:300 17px/1.8 'Open Sans',sans-serif">Our team, contributors, and advisors combine scientific expertise, technical knowledge, and diverse perspectives to advance Beneficial AI for Children. We believe meaningful progress requires collaboration across disciplines, generations, and sectors, including the active participation of young people.</p>
<h2 style="{H2};margin-top:56px">Our Nonprofit Status</h2>
<p style="{P}">We are a California nonprofit public benefit corporation recognized by the Internal Revenue Service (IRS) as a 501(c)(3) tax-exempt public charity.</p>
<p style="margin:14px 0 0;font:300 17px/1.8 'Open Sans',sans-serif"><strong {STRONG}>EIN (Tax ID):</strong> 99-2317785</p>
<p style="margin:14px 0 0;font:300 17px/1.8 'Open Sans',sans-serif">Donations to everyone.AI are tax-deductible to the extent permitted by U.S. law.</p>
<h2 style="{H2};margin-top:56px">Our Values</h2>
<p style="{P}">Our work is grounded in the core principles of ethical AI. AI must be <strong {STRONG}>safe</strong>, protecting children from AI-related risks; <strong {STRONG}>ethical</strong>, respecting their rights and well-being; <strong {STRONG}>fair</strong>, actively addressing discriminatory bias; <strong {STRONG}>inclusive</strong>, offering equitable access to all; <strong {STRONG}>transparent</strong>, with clear and understandable processes; and <strong {STRONG}>privacy-respecting</strong>, protecting children’s data.</p>
<p style="margin:14px 0 0;font:300 17px/1.8 'Open Sans',sans-serif">At everyone.AI, we bring an additional perspective by placing children’s cognitive, social, and emotional development at the heart of our approach. Children are not simply younger adults: their needs and capacities evolve from early childhood through adolescence and into young adulthood. AI systems must be designed, evaluated, and governed with these differences in mind.</p>
""")
patch("About.dc.html", why, r"<h2 [^>]*>Our Values</h2>\n<p [^\n]*\n<p [^\n]*\n", replace_file=about)
YOUTH = [("Alex King", "alex-king-61340b363", "2026/10/IMG_5819-scaled.png"), ("Isabella Schlarb", "isabella-schlarb-916863277", "2026/10/1771351134762.webp"),
         ("Cece Sharp", "cece-sharp-7538773a3", "2026/10/1789621856247.webp"), ("Annika Singh", "annika-singh-459363359", "2026/10/P1467625-scaled.webp"),
         ("Erika Khov", "erikamolikhov", "2026/10/1754457024095.webp"), ("Deborah Hanoh", "deborah-hanoh-39055b238", "2026/10/1785516589549.webp"),
         ("Hannah Griswold", "hannah-griswold", "2026/09/Hannah.webp"), ("Nino Shamoyan", "nino-shamoyan-85b120387", "2026/10/1782810106197.webp"),
         ("Upendo Naware", "upendonawire", "2026/10/Upendo-Nawire.webp"), ("Ombeline Latour", "ombeline-latour-696829341", "2026/10/IMG_3299.webp"),
         ("Allegra Cuomo", "allegracuomo", "2026/10/1782311630267.webp"), ("Alan Gourvès", "alan-gourvès", "2026/10/1685649749273.webp"),
         ("Tom Jouvet", "tom-jouvet", "2026/10/1769503460917.webp")]
rows = []
for n, li, f in YOUTH:
    photo = image("https://everyone.ai/wp-content/uploads/" + f, "team", n, 400)
    rows.append(", [['%s', '%s', '', '%s'], '']" % (n, li, photo))
patch("About.dc.html", "13 Youth Contributors of the live page missing from Design.", r"(\[\['Victor Delvat', 'delvatvictor'\], ''\])\]\]", "\\1" + "".join(rows) + "]]")

# Donate --------------------------------------------------------------------------------
why = "Sections of the live Donate page missing from Design."
donate = fragment("donate-sections", f"""
<section style="{SEC}">
<h2 style="{SECH2}">Play A Role In Beneficial AI For The Next Generation</h2>
<div data-g2="" style="display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:22px;margin-top:28px">
<div style="{CARD}"><h3 style="{H3}">Social Impact</h3><p style="margin:12px 0 0;font:300 15px/1.7 'Open Sans',sans-serif">Actively participate in the protection of children and future generations by contributing to the development of a responsible and positive AI.</p></div>
<div style="{CARD}"><h3 style="{H3}">Thought Leadership</h3><p style="margin:12px 0 0;font:300 15px/1.7 'Open Sans',sans-serif">Join a select community of forward-thinking leaders, top researchers, and visionary AI experts shaping the future. Connect with those who are not only ahead of the curve but are actively defining it.</p></div>
<div style="{CARD}"><h3 style="{H3}">Public Recognition</h3><p style="margin:12px 0 0;font:300 15px/1.7 'Open Sans',sans-serif">Showcase your commitment to AI safety and the protection of children through your partnership with us.</p></div>
</div>
</section>
<section style="{SEC}">
<h2 style="{SECH2}">How to contribute?</h2>
<div data-g2="" style="display:grid;grid-template-columns:minmax(0,1fr) minmax(0,2fr);gap:22px;margin-top:28px">
<div style="{CARD}"><h3 style="{H3}">Become a Donor</h3><a href="#donate" style="{BTN}" {HOVER}>Donate</a></div>
<div style="{CARD}"><h3 style="{H3}">Invite your Network to Support Us</h3><p style="margin:12px 0 0;font:300 15px/1.7 'Open Sans',sans-serif">By clicking on one of those buttons, it will share our Call to action to your audience</p><div>{shares("donate", "Donate")}</div></div>
</div>
</section>
<section style="{SEC}">
<h2 style="{SECH2}">Connect with us</h2>
<p style="margin:18px auto 0;max-width:760px;text-align:center;font:300 16px/1.7 'Open Sans',sans-serif">By being signed up to our Newsletter, this is the best way to stay in touch with the mission that matters to you. Make sure you’ll accept our confirmation email so we won’t be blocked in your Spam.</p>
<p style="margin:12px auto 0;max-width:760px;text-align:center;font:300 16px/1.7 'Open Sans',sans-serif">If you want to start a separate conversation, please <a href="Contact.dc.html">contact us</a> and we will get back to you shortly.</p>
</section>
""")
patch("Donate.dc.html", "The live page shows the dollar card first.", r"(<div [^\n]*Make a donation in Euros[^\n]*)\n(<div [^\n]*Donation in Dollars[^\n]*|<div [^\n]*donation in Dollars[^\n]*)\n", "\\2\n\\1\n")
patch("Donate.dc.html", "Anchor for the Donate button.", r'<div data-g2="" style="display:grid;grid-template-columns:repeat\(2', '<div id="donate" data-g2="" style="display:grid;grid-template-columns:repeat(2')
patch("Donate.dc.html", why + " The 501(c)(3) paragraph is already in the footer.", r"<p [^\n]*<strong [^>]*>everyone\.AI</strong> is a 501[^\n]*\n", replace_file=donate)

# Open Letter ---------------------------------------------------------------------------
t = live("open-letter")
f = flat(t)
f = f[f.find("{https://www.commonsensemedia.org}"):f.find("Do you think more people would like")]
pairs = re.findall(r"(?:\{(\S+)\}\s*)?\[IMG ([^\]]+)\]", f)
logos = []
for index, (href, src) in enumerate(pairs):
    host = re.sub(r"^https?://(www\.)?", "", href).split("/")[0] or src.split("/")[-1].split(".")[0]
    box = "display:flex;align-items:center;justify-content:center;background:#fff;border-radius:8px;padding:14px;height:84px;box-sizing:border-box"
    img = '<img src="%s" alt="%s" loading="lazy" style="max-width:100%%;max-height:100%%;object-fit:contain">' % (image(src, "logos", "letter-%d-%s" % (index, host), 400), host)
    logos.append('<a href="%s" target="_blank" rel="noopener" aria-label="%s" style="%s">%s</a>' % (href, host, box, img) if href else '<div style="%s">%s</div>' % (box, img))
print("open letter logos:", len(logos))
letter = fragment("open-letter-logos", f"""
<section style="margin-top:56px">
<div data-g2="" style="display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px">{"".join(logos)}</div>
</section>
""")
patch("Open Letter.dc.html", "Supporter logos and share block of the live page.", r'(<section style="margin-top:\d+px[^"]*">\n<h2 [^>]*>How to contribute\?)', replace_file=letter)
patch("Open Letter.dc.html", "Donate call of the live page.", r'(<h3 [^>]*>Become a Donor</h3><a [^>]*>)Donate</a>', "\\1Make a Tax-Deductible Donation</a>")
# AIA -----------------------------------------------------------------------------------
aifg = image("https://everyone.ai/wp-content/uploads/2025/03/AI4Good-Logo-Ukraine-2022.png", "logos", "ai4good-aia", 600)
patch("AIA.dc.html", "AI4Good logo of the live gallery.", r'(<div[^\n]*<image-slot id="aia-photo-3"[^\n]*\n)', '\\1<div style="display:flex;align-items:center;justify-content:center;background:#fff;border-radius:8px;padding:20px"><img src="%s" alt="AI for Good" loading="lazy" style="max-width:100%%;max-height:160px;object-fit:contain"></div>\n' % aifg)
patch("AIA.dc.html", "White Label had no contact link.", r"If interested, contact us\.", 'If interested, <a href="mailto:partners@everyone.ai">contact us</a>.')

# Coalition -----------------------------------------------------------------------------
t = live("international-coalition")
key = lambda h: re.sub(r"^(https?://)+(www\.)?", "", h.strip()).split("/")[0].lower()
logo = {}
for href, src, in re.findall(r'<a [^>]*href="([^"]+)"[^>]*>\s*(?:<span[^>]*>\s*)?<img[^>]*?data-src="([^"]+)"', t):
    k = key(href)
    if k in ("everyone.ai", "i-raise.org", "youtu.be", "linkedin.com") or k in logo or "Banner" in src:
        continue
    logo[k] = image(src, "logos", k, 400)
print("coalition logos:", len(logo))
base = "https://everyone.ai/wp-content/uploads/"
COMP = [("Google", "https://about.google", "2025/03/580b57fcd9996e24bc43c51f.png"), ("OpenAI", "https://openai.com", "2025/10/OpenAI-black-wordmark.png"),
        ("Microsoft", "https://www.microsoft.com", "2025/10/RE1Mu3b.png"), ("Anthropic", "https://www.anthropic.com", "2025/03/Anthropic_logo.svg.png"),
        ("Plug and Play", "https://www.plugandplaytechcenter.com", "2025/03/Plug_and_Play_Logo_HR.png"), ("Hugging Face", "https://huggingface.co", "2025/03/hf-logo-with-title.png"),
        ("Vivendi", "https://www.vivendi.com", "2025/03/Vivendi_logo.svg.png"), ("Orange", "https://www.orange.com", "2025/10/images-1.png")]
for n, u, f in COMP:
    logo[key(u)] = image(base + f, "logos", n, 400)
comp = ", ".join("o('%s', '%s')" % (n, u) for n, u, _ in COMP)
li = {}
norm = lambda n: re.sub(r"^(Dr\.|Pr\.|Prof\.)\s*", "", n.strip()).replace("Gregory", "Grégory").lower()
for href, name in re.findall(r"\{(https://www\.linkedin\.com/in/[^}]+)\}\s*([^,{]+?)\s*,", flat(t)):
    li[norm(name)] = href.split("?")[0]
print("coalition linkedin:", len(li))
photo = {}
print(sorted(set(re.findall(r'alt="([^"]{6,40})"', t)))[:60])
for alt, src in [(a, b) for b, a in re.findall(r'<img[^>]*?data-src="([^"]+)"[^>]*?alt="([^"]+)"', t)]:
    if alt in ("Stuart Russell", "Isabelle C. Hau", "Teddy Nalubega", "Michael Preston", "Laurence Devilliers", "David Evan Harris", "Isabella Henriques") and alt not in photo:
        alt = alt.replace("Devilliers", "Devillers")
        photo[alt] = image(src, "people", alt, 240)
print("coalition photos:", len(photo))
J = lambda d: json.dumps(d, ensure_ascii=False)
patch("Coalition.dc.html", "Logos, LinkedIn links of the live page.",
      r"const o = \(n, href\) => \(\{ n, href \}\);\nconst ex = s => s\.split\('\|'\)\.map\(x => \{ const \[n, r\] = x\.split\('~'\); return \{ n, r \}; \}\);",
      "const LOGO = %s;\nconst LI = %s;\nconst host = h => h.replace(/^(https?:\\/\\/)+(www\\.)?/, '').split('/')[0].toLowerCase();\nconst o = (n, href) => { const logo = LOGO[host(href)] || ''; return { n, href, logo, hasLogo: !!logo, noLogo: !logo }; };\nconst ex = s => s.split('|').map(x => { const [n, r] = x.split('~'); const li = LI[n.replace(/^(Dr|Pr|Prof)[.] */, '').trim().toLowerCase()] || ''; return { n, r, li, hasLi: !!li, noLi: !li }; });" % (J(logo).replace("\\", "\\\\"), J(li).replace("\\", "\\\\")))
patch("Coalition.dc.html", "Company links and the Orange logo.", r"items: \[o\('Google', '#'\).*?o\('Vivendi', '#'\)\]", "items: [" + comp + "]")
patch("Coalition.dc.html", "Logos instead of text chips.", r'(<a href="\{\{ o\.href \}\}"[^>]*?)style="[^"]*"([^>]*>)\{\{ o\.n \}\}</a>',
      '\\1aria-label="{{ o.n }}" style="display:flex;align-items:center;justify-content:center;background:#fff;border-radius:8px;padding:12px;height:76px;box-sizing:border-box;font:400 14px/1.3 \'Open Sans\',sans-serif;color:#333;text-decoration:none;text-align:center"\\2<sc-if value="{{ o.hasLogo }}" hint-placeholder-val="{{ true }}"><img src="{{ o.logo }}" alt="{{ o.n }}" loading="lazy" style="max-width:100%;max-height:100%;object-fit:contain"></sc-if><sc-if value="{{ o.noLogo }}" hint-placeholder-val="{{ false }}">{{ o.n }}</sc-if></a>')
patch("Coalition.dc.html", "LinkedIn links of the experts.", r"<strong([^>]*)>\{\{ p\.n \}\}</strong>",
      '<sc-if value="{{ p.hasLi }}" hint-placeholder-val="{{ true }}"><a href="{{ p.li }}" target="_blank" rel="noopener"><strong\\1>{{ p.n }}</strong></a></sc-if><sc-if value="{{ p.noLi }}" hint-placeholder-val="{{ false }}"><strong\\1>{{ p.n }}</strong></sc-if>')
for n, p in photo.items():
    patch("Coalition.dc.html", "Photo of the quoted person.", r"\{ n: '%s', r:" % re.escape(n), "{ n: '%s', photo: '%s', r:" % (n, p))
patch("Coalition.dc.html", "Photo of the quoted person.", r"(<figcaption[^>]*>)", '\\1<img src="{{ q.photo }}" alt="{{ q.n }}" loading="lazy" style="width:72px;height:72px;border-radius:50%;object-fit:cover;display:block;margin:0 0 10px">')

path = os.path.join(HERE, "page-patches.json")
data = json.load(open(path, encoding="utf-8"))
data["patches"] = [p for p in data["patches"] if not p.get("ported")] + patches
json.dump(data, open(path, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
open(path, "a").write("\n")
print("patches:", len(patches))
