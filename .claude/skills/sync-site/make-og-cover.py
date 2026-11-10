#!/usr/bin/env python3
"""Make the social sharing image (og:image), 1200 x 630, from the Home hero.

Every page pointed at assets/og-cover.png, a file Claude Design holds but DesignSync cannot
export (it truncates at 256 KiB), so links shared on LinkedIn or WhatsApp showed no picture
(Julien's fixes kanban, card S4). This builds one from the hero the site already shows: the
hero (1250 x 468) is kept at its own size, never enlarged, and its plain blue background is
extended upwards to reach 630 px; the title goes in the empty right half. JPEG, because some
networks still ignore WebP previews.

Fonts: Poppins (the site's heading font, SIL Open Font License, fonts/OFL.txt).
Idempotent: an existing file is kept; delete it to rebuild.

Usage:  python3 .claude/skills/sync-site/make-og-cover.py   (from the repo root)
"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.getcwd(), "docs")
DEST = os.path.join(OUT, "assets", "og-cover.jpg")
W, H = 1200, 630
TITLE = ["Shaping beneficial AI", "for children"]
TAGLINE = ["For children today,", "for everyone tomorrow"]
BLUE = (130, 155, 203)   # #829BCB, the accent Gaelle gave for the Home banner


def font(weight, size):
    return ImageFont.truetype(os.path.join(HERE, "fonts", "Poppins-%s.ttf" % weight), size)


def main():
    if os.path.exists(DEST):
        print("og cover: kept %s" % os.path.relpath(DEST, OUT))
        return 0
    hero = Image.open(os.path.join(OUT, "assets", "hero-child.jpg")).convert("RGB")
    hero = hero.crop((4, 4, hero.width, hero.height))   # 1 px light frame plus JPEG ringing on the top and left edges
    hero = hero.resize((W, round(hero.height * W / hero.width)), Image.LANCZOS)   # 1246 -> 1200: a slight reduction
    canvas = Image.new("RGB", (W, H))
    top = H - hero.height
    # The hero's top rows are plain background: repeat one upwards so the join does not show.
    canvas.paste(hero.crop((0, 6, W, 7)).resize((W, top)), (0, 0))
    canvas.paste(hero, (0, top))

    d = ImageDraw.Draw(canvas)
    x, y = 560, 150
    d.text((x, y), "everyone.AI", font=font("SemiBold", 30), fill=(255, 255, 255))
    y += 70
    for line in TITLE:
        d.text((x, y), line, font=font("SemiBold", 50), fill=(255, 255, 255))
        y += 64
    y += 22
    for line in TAGLINE:
        d.text((x, y), line, font=font("Regular", 32), fill=BLUE)
        y += 44

    os.makedirs(os.path.dirname(DEST), exist_ok=True)
    canvas.save(DEST, "JPEG", quality=86, optimize=True, progressive=True)
    print("og cover: made %s (%d KiB)" % (os.path.relpath(DEST, OUT), os.path.getsize(DEST) // 1024))
    return 0


if __name__ == "__main__":
    sys.exit(main())
