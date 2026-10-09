#!/usr/bin/env bash
# verify.sh — post-deploy sanity gates. Exits non-zero if anything is wrong.
# Safe to run standalone:  bash .claude/skills/sync-site/verify.sh
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$(cd "$SKILL_DIR/../../.." && pwd)"
exec python3 "$SKILL_DIR/verify.py"
