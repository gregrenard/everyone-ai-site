#!/usr/bin/env python3
"""
extract-pulled.py — write every file pulled from Claude Design to disk, byte-exact.

Reads the session transcripts (JSONL) and reconstructs each file from the
DesignSync get_file results: inline results, large results persisted to a
tool-results/<toolu>.txt file, text and base64 binaries alike. The freshest pull
per path wins. No hand-retyping = no corruption risk.

Differences from the gregory-renard-site original:
  - writes ANY pulled path (pages, shared components, JS modules, assets), not
    only the pages in pages.json, because this site has runtime dependencies
    (SiteHeader/SiteFooter, i18n-*.js, image-slot.js) the pages cannot render without;
  - scans subagent transcripts too, so bulk pulls can be delegated;
  - pages and components land in src/ (build input); everything else in docs/
    (the published folder), pages.json next to this script;
  - refuses to write a truncated result (get_file caps at 256 KiB).

Usage (from the repo root):
    python3 .claude/skills/sync-site/extract-pulled.py            # everything pulled
    python3 .claude/skills/sync-site/extract-pulled.py --list     # report only
    python3 .claude/skills/sync-site/extract-pulled.py --transcripts DIR
"""
import base64, glob, json, os, re, sys

REPO = os.getcwd()
SRC = "src"            # Design-side pages + components: the input of build.py, never served
OUT = "docs"           # the published site (GitHub Pages serves this folder)
KEY = '{"method":"get_file"'
# Design files that are the repo's own business, never taken from a pull.
SKIP = {"index.html", "DEPLOY.md", "github.md", ".thumbnail"}


def transcript_dirs():
    if "--transcripts" in sys.argv:
        return [sys.argv[sys.argv.index("--transcripts") + 1]]
    base = os.path.expanduser("~/.claude/projects/")
    enc = lambda p: re.sub(r"[^A-Za-z0-9]", "-", p)
    # The session may have been started in the parent directory.
    cands = [os.path.join(base, enc(REPO)), os.path.join(base, enc(os.path.dirname(REPO)))]
    return [d for d in cands if os.path.isdir(d)]


def extract_objs(text):
    """Every COMPLETE {"method":"get_file"...} object in text (string-aware brace scan,
    so truncated previews are skipped rather than partially matched)."""
    out, i = [], 0
    while True:
        j = text.find(KEY, i)
        if j < 0:
            break
        depth, k, instr, esc, ok = 0, j, False, False, False
        while k < len(text):
            c = text[k]
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                instr = not instr
            elif not instr:
                if c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        k += 1
                        ok = True
                        break
            k += 1
        if ok:
            try:
                o = json.loads(text[j:k])
                if o.get("method") == "get_file" and "content" in o:
                    out.append(o)
            except Exception:
                pass
            i = k
        else:
            i = j + len(KEY)
    return out


def walk_strings(o):
    if isinstance(o, str):
        yield o
    elif isinstance(o, dict):
        for v in o.values():
            yield from walk_strings(v)
    elif isinstance(o, list):
        for v in o:
            yield from walk_strings(v)


def collect():
    """path -> (sort_key, object). sort_key = (timestamp, sequence): freshest wins."""
    best, seq = {}, 0
    files = []
    for d in transcript_dirs():
        files += glob.glob(os.path.join(d, "**", "*.jsonl"), recursive=True)
    for jf in sorted(set(files), key=os.path.getmtime):
        with open(jf, encoding="utf-8") as f:
            for line in f:
                if KEY not in line and "Full output saved to:" not in line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                ts = rec.get("timestamp") or ""
                for s in walk_strings(rec):
                    objs = []
                    if "Full output saved to:" in s and KEY in s:
                        m = re.search(r"Full output saved to:\s*(\S+\.txt)", s)
                        if m and os.path.exists(m.group(1)):
                            objs = extract_objs(open(m.group(1), encoding="utf-8").read())
                    elif KEY in s:
                        objs = extract_objs(s)
                    for o in objs:
                        seq += 1
                        k = (ts, seq)
                        if o["path"] not in best or best[o["path"]][0] < k:
                            best[o["path"]] = (k, o)
    return {p: o for p, (_, o) in best.items()}


def target(path):
    """Where a Design path lands in the repo."""
    if path == "pages.json":
        return os.path.join(os.path.dirname(os.path.relpath(__file__, REPO)), path)
    if "/" not in path and path.endswith(".dc.html"):
        return os.path.join(SRC, path)          # pages + shared components
    return os.path.join(OUT, path)              # assets, JS modules, SEO files


def main():
    list_only = "--list" in sys.argv
    pulled = collect()
    wrote, bad = 0, []
    for path in sorted(pulled):
        o = pulled[path]
        if path in SKIP:
            continue
        if o.get("truncated"):
            bad.append(path + " (truncated: over the 256 KiB get_file cap)")
            continue
        data = base64.b64decode(o["content"]) if o.get("isBase64") else o["content"].encode("utf-8")
        dest = target(path)
        if not list_only:
            full = os.path.join(REPO, dest)
            os.makedirs(os.path.dirname(full) or ".", exist_ok=True)
            with open(full, "wb") as out:
                out.write(data)
        wrote += 1
        print("%s  %-64s %8d bytes" % ("FOUND" if list_only else "WROTE", dest, len(data)))
    print("\n%d files %s." % (wrote, "found" if list_only else "written"))
    if bad:
        print("NOT WRITTEN:")
        for b in bad:
            print("  ", b)
        sys.exit(1)


if __name__ == "__main__":
    main()
