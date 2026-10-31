# Everyone.AI website: what was adapted

Status on 2026-10-31. This report lists everything changed compared with the Claude Design export, and what is still open. Preview: https://gregrenard.github.io/everyone-ai-site/

Claude Design stays the source of the pages and is read-only from this repository. Every change below is applied at deploy time by the `sync-site` pipeline, so a new Design export does not lose it. Most changes switch themselves off once Design contains the same fix. To check a future version, use the `site-release-check` skill.

## Result

| Measure (home page, throttled mobile, local test) | Before | After |
|---|---|---|
| Layout shift (CLS, target under 0.1) | 1.02 | 0.02 |
| Console errors | 2 | 0 |
| Images over 200 KiB | 13 | 0 |
| Heaviest image | 1,278 KiB | under 200 KiB |
| Ways to donate that work | 0 | 2 |
| Pages | 15 | 18 |

The "before" CLS matches the 1.0 measured on PageSpeed on 2026-10-29. These figures come from a local Chrome test, not from PageSpeed, so PageSpeed still has to be run again.

## Google Ad Grants blockers (email of 2026-10-29)

| # | Item | What was done | Status |
|---|---|---|---|
| 1 | Donations | The USD button linked to its own page. It is replaced by the Givebutter widget used on the current site. The euro link was a 404, also on the current site; it now goes to the Globale Philanthropie donation page, which carries the "Devenez acteur de l'IA responsable" campaign. | Done, to confirm by the team |
| 2 | Forms | Newsletter forms now post to the MailerLite list of the current site. Contact, press and open-letter forms used to show "Thank you" and drop the message; they now open the visitor's email app, addressed to `website@everyone.ai`. | Partly done |
| 3 | Contact | New `/contact/` page with form, email and postal address. Contact added to the main menu in 8 languages, and to the footer. Address added to the footer of every page. | Done, to confirm by the team |
| 4 | Layout shift | The email blamed the top banner. The measured cause was the pre-rendered copy of the page: it was pushed out of the screen when the live page mounted. It is now out of the page flow and removed at mount. | Done |
| 5 | Photos | The 13 images over 200 KiB were recompressed to WebP at quality 82 or higher, with no visible loss expected. Rule added to the build: 1600 px maximum, under 200 KiB. | Weight done, small images open |
| 6 | Console errors | They were not bad images. The browser was loading the page templates literally (`{{ m.photo }}`, `{{ f.src }}`). Those attributes are now neutralized until the page renders. | Done |
| 7 | Generic buttons | 7 "Learn more" and "Read More" labels replaced, in 8 languages, for example "Discover the AïA method" and "Read the Mapping report". | Done, wording to validate |

The postal address (1259 El Camino Real, Unit #1042, Menlo Park, CA 94025) and `website@everyone.ai` were taken from the privacy policy of the current site. Please confirm both are current.

## Other changes in this version

- New `/privacy-policy/` and `/accessibility-statement/` pages, copied from the current site. The footer links no longer depend on WordPress. The line "Phone: [Insert Phone Number]", a leftover placeholder on the current site, was removed.
- The accessibility statement is translated. The privacy policy stays in English until a human validates a legal translation.
- The launch video on the coalition page was broken on the new site: the build pointed it at a local file that does not exist, although the earlier reports said it was still hotlinked. It now plays from `everyone.ai/wp-content`, as decided.
- The VivaTech logo link now has an accessible name.

## Changes from earlier versions

**Content and media**

- 93 empty image slots (About, Newsroom) filled from the current site, resized to WebP (47 MB down to 2.7 MB).
- All pages translated into 8 languages: 1,083 strings were added to what Design already translated.
- Spelling fixed: CNRS, Marc Baillavoine, Grégory, and "ßeta", which displayed as "SSETA" in capitals.

**Navigation**

- Home and Contact links work from every page; they did nothing outside Home.
- Arriving on a section stops just below the menu instead of one screen too low.
- The menu bar stays visible while scrolling, on phones and desktop. The announcement banner scrolls away.
- The Home "Our Initiatives" menu with its fly-out is used on every page.
- Open letter share buttons send a real URL.
- "Contributors" on the AïA method scrolls to the top, and "Parts I–V" opens the current site.

**Mobile**

- Justified text is aligned left on phones, where it opened wide gaps between words.
- No horizontal overflow on the tested pages and widths.

## Still open

**Needs a decision or content from the team**

1. A service to receive the contact, press and open-letter forms. Opening the visitor's email app is a stopgap and fails for anyone without a mail app. Set `formEndpoint` in `site-config.json`.
2. Original files for images that are too small: the 4 mission thumbnails (215 x 140 px), the hero (1250 x 468 px), and the small research thumbnails (about 200 px). Enlarging them would not make them sharp.
3. Launch video on YouTube, and `assets/og-cover.png` exported from Design.
4. "Parts I–V" of the AïA method: only on the WordPress page, so it breaks at the DNS switch unless it is added to Design.
5. Dead partner links on the coalition page: Content & Society (404), and GSoLEN and IASEAI, which did not respond from our test machine and need a check in a real browser.
6. An annual report or Impact page in HTML, a Programs entry in the menu, a clear call to action in the hero, a button under the 3 pillars, and the Youth Voice page.
7. Native review of the translations.

**Technical follow-up**

8. Run PageSpeed again. Newsroom LCP is 3.9 s in the local test (target 2.5 s), and the home page is close to the limit at 2.0 s.
9. The newsletter thank-you line stays in English on pages other than Home.
10. Move the deploy-time fixes into Claude Design over time, starting with `page-patches.json`.
11. Create the everyone.ai repository, give Gaëlle access, then switch the DNS. None of this has been done.

The order proposed by the team stands: one list of fixes, one content validation, DNS switch, then a new Google Ad Grants submission. Google requires the organization's own domain, so the submission cannot happen before the switch.

## Files to know

All under `.claude/skills/`.

| File | Role |
|---|---|
| `sync-site/deploy.sh` | Runs the full pipeline |
| `sync-site/site-config.json` | Address, contact email, form and donation settings |
| `sync-site/page-patches.json` | Content overrides on Design pages |
| `sync-site/extra-pages/` | Pages Design does not have yet |
| `sync-site/optimize-images.py` | Image weight and size rule |
| `sync-site/verify.py` | Automatic gates, including images and Ad Grants items |
| `site-release-check/SKILL.md` | Checklist for the next versions |
| `site-release-check/audit.mjs` | Browser audit of every page |
