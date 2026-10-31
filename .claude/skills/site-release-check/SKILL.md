---
name: site-release-check
description: Release checklist for the Everyone.AI website. Run before publishing a new version, before the DNS switch, and before submitting to Google Ad Grants. Covers the sync-site verify gates, a browser audit of every page on desktop and phones, performance, Ad Grants requirements, images, donations, forms, translations and links, and says what still needs a human. Triggers: "check the site", "release check", "is the site ready", "before we publish", "before the DNS switch", "Google Ad Grants", "vérifie le site", "le site est prêt ?", "avant de publier", "avant la bascule".
---

# Site release check

Use this skill to decide whether a version of the Everyone.AI site can go out. It reports; it does not fix. Fix through the `sync-site` pipeline, then run the check again.

Report each section as PASS, FAIL or NOT CHECKED, with the measured number. Never mark something PASS because it passed last time: a section that was not run this time is NOT CHECKED.

## Rules for running it

- Do not submit a form from a browser on the user's machine. The contact forms open the local mail app (`mailto:`), and this has already opened a real Mail window with test data. `audit.mjs` never submits. To test a form, intercept the request or read the code.
- Do not subscribe a real address to the MailerLite list. To check that the endpoint is alive, post an invalid email: it answers `"The email field must be a valid email address."`.
- Measure with an empty cache. A reused Chrome profile hid a CLS of 1.02 and reported 0.
- A test that does not use the visitor's conditions proves little. Layout shift must be measured on a throttled mobile with the cache disabled.
- Treat HTTP 403, 429 and 999 from external sites as bot blocking, not as dead links. Open those in a real browser before reporting them.

## 1. Build and gates

From the `website/` folder:

```bash
bash .claude/skills/sync-site/deploy.sh --preview
python3 .claude/skills/sync-site/extract-i18n.py
```

Drop `--preview` only when the site is served from its final domain. `verify.py` must end with no BAD, apart from the accepted items below. Read every WARN.

Accepted until decided otherwise: `assets/og-cover.png` is missing until someone exports it from Claude Design (`DesignSync` truncates it at 256 KiB).

## 2. Browser audit

Serve the build under the production path, so that relative links behave as they do online:

```bash
mkdir -p /tmp/eai-srv && ln -sfn "$PWD/docs" /tmp/eai-srv/everyone-ai-site
(cd /tmp/eai-srv && python3 -m http.server 8791) &
node .claude/skills/site-release-check/audit.mjs http://127.0.0.1:8791/everyone-ai-site/
```

After publishing, run it again on `https://gregrenard.github.io/everyone-ai-site/`. All pages at 1280, 390 and 360 px, in English, French and German. A run takes about 6 minutes for 18 pages.

It fails on: horizontal overflow, H1 count other than one, menu not sticky, pre-render mirror still present, wrong `<html lang>`, empty image slots, text under 12 px, broken images, missing alt text, unresolved `{{ }}`, any console error or failed request, links without a name, dead anchors, dead internal links, CLS over 0.1.

It warns on: distorted images, images shown larger than their file, generic button labels, links that depend on the old site, LCP over 2.5 s.

## 3. Performance on PageSpeed

Run https://pagespeed.web.dev/ by hand on the home page, mobile and desktop. The local audit only estimates these figures.

| Measure | Target |
|---|---|
| Mobile Performance score | 70 or more |
| LCP | under 2.5 s |
| CLS | under 0.1 |
| Accessibility score | 90 or more |

## 4. Google Ad Grants requirements

Policy: https://support.google.com/nonprofits/answer/1657899

- HTTPS on a domain the organization owns. The github.io preview does not qualify, so submit only after the DNS switch.
- Mission clear at the top of the home page.
- Mission, Programs and Contact reachable in one click from every page.
- `/contact/` works and shows a form, an email and a postal address.
- Postal address and EIN (99-2317785) in the footer of every page.
- A donation can really be made. Open the Givebutter widget and the euro link by hand, stop before paying.
- No AdSense or other paid advertising.
- Every button says what it does. No "Learn more" or "Read more".
- A real annual report or Impact page in HTML, not only a PDF.

## 5. Images

Team rule of 2026-10-29: at most 1600 px on the long side, WebP, under 200 KiB; thumbnails at twice their displayed size. `optimize-images.py` and verify gate (l) enforce weight and size. Enlarging a small file adds no detail, so an image that is too small needs its original: list it for the team. Look at the photos on a real phone, because automated checks do not see blur.

## 6. Donations, forms, translations

- USD: `<givebutter-widget>` renders on `/donate/`.
- EUR: the link lands on the campaign page of Globale Philanthropie and not on a 404.
- Newsletter: the request goes to MailerLite with `fields[email]`.
- Contact, press and open-letter forms: `formEndpoint` in `site-config.json`. While it is empty they open the visitor's email app, which is not good enough for a Google submission.
- Every page exists in the 8 languages. `extract-i18n.py --missing <lang>` lists what is left. Legal text stays in English until a human validates it.

## 7. Before the DNS switch

These break or change when `everyone.ai` stops pointing at WordPress:

- Launch video: hotlinked to `everyone.ai/wp-content`. Move it to YouTube first.
- "Parts I–V" on the AïA method: only exists on the WordPress page (verify gate (j) warns).
- Any other link reported by the audit as depending on the old site.
- Run `deploy.sh` without `--preview`, otherwise every page stays `noindex`.
- Add `CNAME`, then check the sitemap, `robots.txt` and `llms.txt` on the final domain.

The DNS switch, a CNAME and any change of repository need an explicit go from the user.

## 8. Human review

- Native reading of the machine translations, including the AïA method vocabulary and gendered job titles.
- Team and partner lists up to date.
- External links that automated checks cannot confirm.
- One pass on a real iPhone and a real Android phone. Everything above is emulation.

## Known traps

- The ids of sections exist twice before the runtime mounts. Measure after mount.
- `<base href="../">` makes `a.href` of a bare `#anchor` resolve to the site root. Compare the raw `href` with the current page's ids.
- A bare `#x` link to Home is swallowed by the hash shim on other pages. It must stay `./#x`.
- An absolute everyone.ai URL held in a JS constant must not be rewritten: share buttons need it.
- A padded image looks distorted if you compare its box with the file. Subtract the padding.
- The header overlay does not translate: nav labels live in `i18n-home.js`, which `build.py` patches.
