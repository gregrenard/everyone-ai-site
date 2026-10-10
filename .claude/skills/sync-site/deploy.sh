#!/usr/bin/env bash
# deploy.sh — re-apply ALL deploy-only transforms after pulling the Design sources into
# src/ (via extract-pulled.py) and docs/ root files (via fetch-wp-assets.py), then verify.
# Idempotent.
#
# Pipeline order is critical (see SKILL.md):
#   fetch-wp-assets + fetch-slot-images -> build (clean URLs, static SEO head, <base>, hash shim)
#   -> bump sitemap -> prerender (LAST: mirror must carry final clean URLs) -> verify
#
# Does NOT touch src/ (Design snapshot, read-only here) or the repo-only files
# (404.html, robots.txt, llms.txt, sitemap.xml, support.js, i18n-*.js, image-slot.js,
# CNAME, .nojekyll).
#
# Translations: build.py publishes i18n/<lang>.json through the overlay. After a sync
# that changes page text, run extract-i18n.py to refresh i18n/en.json and list the
# strings that need translating (verify gate (k) warns about them).
#
# Usage:  bash .claude/skills/sync-site/deploy.sh [--media] [--preview]   (run from anywhere)
#   --media    also download hotlinked videos (large; default: leave external + WARN)
#   --preview  mark every page noindex (use while served from a github.io project path)
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$SKILL_DIR/../../.." && pwd)"
cd "$REPO"

MEDIA_FLAG=""
PREVIEW_FLAG=""
for arg in "$@"; do
  case "$arg" in
    --media) MEDIA_FLAG="--media" ;;
    --preview) PREVIEW_FLAG="--preview" ;;
    *) echo "ERROR: unknown argument '$arg'"; exit 1 ;;
  esac
done

[ -f "src/Home.dc.html" ] || { echo "ERROR: src/Home.dc.html not found — run extract-pulled.py first."; exit 1; }

echo "==> 1/5  localize hotlinked wp-content files"
python3 "$SKILL_DIR/fetch-wp-assets.py" $MEDIA_FLAG
python3 "$SKILL_DIR/fetch-slot-images.py"

echo "==> 2/5  build docs/ from src/ (clean URLs, static SEO head, <base>, hash shim)"
python3 "$SKILL_DIR/build.py" $PREVIEW_FLAG

echo "==> 3/5  bump sitemap <lastmod> to today"
TODAY="$(date +%F)"
sed -i '' "s|<lastmod>[^<]*</lastmod>|<lastmod>$TODAY</lastmod>|g" docs/sitemap.xml

echo "==> 4/5  static pre-render (headless): real content for no-JS / non-JS crawlers"
python3 "$SKILL_DIR/prerender.py"

echo "==> 5/5  verify"
python3 "$SKILL_DIR/verify.py"
