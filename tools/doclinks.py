#!/usr/bin/env python3
"""doclinks.py -- offline link and reference checker for the documentation set.

Status / last verified: 2026-10-10.  Read next: docs/INDEX.md (once it exists), tools/docaudit.py.

Scans docs/**/*.md, README.md, tools/README.md, build/README.md, CLAUDE.md (those present).
Extracts three kinds of reference (fenced code blocks are skipped):
  1. Markdown links  [text](path#anchor)       (http/mailto/pure-#anchor handled)
  2. Backtick repo paths  `docs/x.md`, `tools/y.py`, `build/hook/z.dfu`  (optional :NNN, #anchor)
  3. Line references  field-log.md:NNN  or  field-log.md:NNN-MMM  (docs/field-log.md)

Findings:
  BROKEN            target file/dir is missing
  ANCHOR-MISSING    .md target exists but has no such heading (warning)
  LINE-OUT-OF-RANGE field-log line number beyond the file length (warning)
  NOTE              target missing but lives in a git-ignored generated dir (warning)

Exit status is 1 only if BROKEN > 0.  With --strict, NOTE, ANCHOR-MISSING and
LINE-OUT-OF-RANGE also count and make the exit status 1.

Options: --list-orphans, --direct, --json, --strict, --root DIR, --selftest.
Pure standard library; makes no network or device access.


NOTE (this public export): this tool was written for, and hard-codes paths into, the original private research repository (CLAUDE.md, docs/RESUME-HERE.md, docs/field-log.md, and others not included here). It will not run cleanly against this export; it is kept for provenance, not as a tool this export expects you to run."""
import argparse
import json
import os
import re
import sys
import tempfile

# Missing targets under these prefixes are NOTE (generated / git-ignored), not BROKEN.
GENERATED_PREFIXES = (
    "build/analysis/",
    "adk/",
    "firmware/bose/extracted/",
    "firmware/bose/probe/",
    "RADIOACTIVE_DO_NOT_FLASH/",
    "repo/",
    "BT STUFF/",
    "tools/innoextract/",
    "fw/build/",
)
GENERATED_SUFFIXES = (".fs", ".xuv")  # build/**/*.fs|*.xuv are git-ignored

TOP_FILES = ("README.md", "tools/README.md", "build/README.md", "CLAUDE.md")
FIELD_LOG = "docs/field-log.md"

LINK_RE = re.compile(r"(?<!\!)\[(?:[^\]\n]*)\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
IMG_RE = re.compile(r"\!\[(?:[^\]\n]*)\]\(\s*<?([^)\s>]+)>?[^)]*\)")
TICK_RE = re.compile(r"`([^`\n]+)`")
PATH_START = ("docs/", "tools/", "build/hook/", "build/analysis/", "adk/", "firmware/bose/extracted/")
PATH_OK = re.compile(r"^[A-Za-z0-9_./+-]+$")
LINEREF_RE = re.compile(r"(?<![A-Za-z0-9_-])(?:docs/)?field-log\.md:(\d+)(?:-(\d+))?")
FENCE_RE = re.compile(r"^\s*(```|~~~)")
HEAD_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$")


def norm(p):
    return os.path.normpath(p).replace("\\", "/")


def is_generated(rel):
    rel = norm(rel)
    if rel.startswith(GENERATED_PREFIXES):
        return True
    return rel.startswith("build/") and rel.endswith(GENERATED_SUFFIXES)


def slugify(text):
    t = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)  # links -> text
    t = re.sub(r"<[^>]+>", "", t)
    t = t.replace("`", "").replace("*", "")
    t = t.strip().lower()
    t = re.sub(r"[^\w\- ]", "", t, flags=re.UNICODE)
    return t.replace(" ", "-")


_anchor_cache = {}


def anchors_of(path):
    if path in _anchor_cache:
        return _anchor_cache[path]
    out, seen = set(), {}
    try:
        in_fence = False
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                if FENCE_RE.match(line):
                    in_fence = not in_fence
                    continue
                if in_fence:
                    continue
                m = HEAD_RE.match(line)
                if m:
                    s = slugify(m.group(2))
                    n = seen.get(s, 0)
                    seen[s] = n + 1
                    out.add(s if n == 0 else "%s-%d" % (s, n))
                for hm in re.finditer(r"<a\s+(?:name|id)=[\"']([^\"']+)[\"']", line):
                    out.add(hm.group(1).lower())
    except OSError:
        pass
    _anchor_cache[path] = out
    return out


def count_lines(path):
    try:
        with open(path, "rb") as f:
            return sum(1 for _ in f)
    except OSError:
        return None


def md_files(root):
    found = []
    droot = os.path.join(root, "docs")
    for dp, dn, fn in os.walk(droot):
        dn.sort()
        for n in sorted(fn):
            if n.lower().endswith(".md"):
                found.append(norm(os.path.relpath(os.path.join(dp, n), root)))
    for t in TOP_FILES:
        if os.path.isfile(os.path.join(root, t)):
            found.append(t)
    return found


def extract(text):
    """Yield (lineno, kind, raw). kind in link|tick|line."""
    in_fence = False
    for i, line in enumerate(text.splitlines(), 1):
        if FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        for m in LINK_RE.finditer(line):
            yield i, "link", m.group(1)
        for m in IMG_RE.finditer(line):
            yield i, "link", m.group(1)
        for m in TICK_RE.finditer(line):
            tok = m.group(1).strip()
            if LINEREF_RE.search(tok):
                continue  # handled as a line reference
            if tok.startswith(PATH_START):
                yield i, "tick", tok
        for m in LINEREF_RE.finditer(line):
            yield i, "line", (int(m.group(1)), int(m.group(2)) if m.group(2) else None)


def split_target(raw):
    """Return (path, anchor) with :NNN suffix removed from path."""
    anchor = ""
    if "#" in raw:
        raw, anchor = raw.split("#", 1)
    raw = re.sub(r":\d+(?:-\d+)?$", "", raw)
    return raw, anchor


def check(root):
    findings = []  # dicts
    edges = {}  # src md -> set of target md
    files = md_files(root)
    fl_path = os.path.join(root, FIELD_LOG)
    fl_len = count_lines(fl_path)

    def add(kind, src, line, target, detail=""):
        findings.append({"class": kind, "file": src, "line": line, "target": target, "detail": detail})

    for src in files:
        edges.setdefault(src, set())
        try:
            with open(os.path.join(root, src), encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError:
            continue
        srcdir = os.path.dirname(src)
        for lineno, kind, raw in extract(text):
            if kind == "line":
                n, m = raw
                edges[src].add(FIELD_LOG)
                if fl_len is None:
                    add("BROKEN", src, lineno, FIELD_LOG, "field-log.md missing")
                elif max(n, m or 0) > fl_len or n < 1:
                    add("LINE-OUT-OF-RANGE", src, lineno, "%s:%d%s" % (FIELD_LOG, n, "-%d" % m if m else ""),
                        "file has %d lines" % fl_len)
                continue
            if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", raw) and not re.match(r"^[A-Za-z]:[\\/]", raw):
                continue  # http:, mailto:, etc.
            path, anchor = split_target(raw)
            if kind == "tick":
                if not PATH_OK.match(path) or ".." in path.replace("../", ""):
                    continue  # globs, placeholders, ranges
                rel = norm(path)  # backtick paths are repo-root relative
            else:
                if path == "":
                    rel = src  # same-file anchor
                elif path.startswith("/"):
                    rel = norm(path.lstrip("/"))
                else:
                    rel = norm(os.path.join(srcdir, path))
            if rel.startswith(".."):
                continue  # leaves the repo: not checked, never opened
            full = os.path.join(root, rel)
            if not os.path.exists(full):
                if is_generated(rel):
                    add("NOTE", src, lineno, raw, "generated/git-ignored path absent")
                else:
                    add("BROKEN", src, lineno, raw, "missing: " + rel)
                continue
            if rel.endswith(".md") and os.path.isfile(full):
                if rel in set(files):
                    edges[src].add(rel)
                if anchor and anchor.lower() not in anchors_of(full):
                    add("ANCHOR-MISSING", src, lineno, raw, "no heading '#%s' in %s" % (anchor, rel))
    return files, findings, edges


def orphans(root, files, edges, direct):
    idx = "docs/INDEX.md"
    if os.path.isfile(os.path.join(root, idx)):
        roots = [idx]
    else:
        roots = [r for r in ("README.md", "docs/RESUME-HERE.md") if r in files]
    reached = set()
    if direct:
        for r in roots:
            reached |= edges.get(r, set())
    else:
        stack = list(roots)
        while stack:
            cur = stack.pop()
            for t in edges.get(cur, ()):
                if t not in reached:
                    reached.add(t)
                    stack.append(t)
    reached |= set(roots)
    return roots, sorted(f for f in files if f.startswith("docs/") and f not in reached)


def render(files, findings, orph, roots):
    lines = []
    order = ["BROKEN", "ANCHOR-MISSING", "LINE-OUT-OF-RANGE", "NOTE"]
    for c in order:
        for f in findings:
            if f["class"] == c:
                lines.append("%s %s:%d -> %s (%s)" % (c, f["file"], f["line"], f["target"], f["detail"]))
    if orph is not None:
        lines.append("ORPHANS (docs not reachable from %s): %d" % (", ".join(roots), len(orph)))
        lines.extend("  " + o for o in orph)
    cnt = counts(findings)
    lines.append("SUMMARY files=%d BROKEN=%d ANCHOR-MISSING=%d LINE-OUT-OF-RANGE=%d NOTE=%d"
                 % (len(files), cnt["BROKEN"], cnt["ANCHOR-MISSING"], cnt["LINE-OUT-OF-RANGE"], cnt["NOTE"]))
    return "\n".join(lines)


def counts(findings):
    c = {"BROKEN": 0, "ANCHOR-MISSING": 0, "LINE-OUT-OF-RANGE": 0, "NOTE": 0}
    for f in findings:
        c[f["class"]] += 1
    return c


def run(root, strict=False, list_orphans=False, direct=False, as_json=False):
    _anchor_cache.clear()
    files, findings, edges = check(root)
    if strict:
        for f in findings:
            if f["class"] == "NOTE":
                f["class"] = "BROKEN"
                f["detail"] += " (--strict)"
    orph, roots = None, []
    if list_orphans:
        roots, orph = orphans(root, files, edges, direct)
    cnt = counts(findings)
    if as_json:
        out = json.dumps({"files": len(files), "counts": cnt, "findings": findings,
                          "orphans": orph, "orphan_roots": roots}, indent=1)
    else:
        out = render(files, findings, orph, roots)
    strict_fail = strict and (cnt["ANCHOR-MISSING"] or cnt["LINE-OUT-OF-RANGE"])
    return out, (1 if cnt["BROKEN"] or strict_fail else 0), findings, orph


def selftest():
    def w(root, rel, text):
        p = os.path.join(root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)

    with tempfile.TemporaryDirectory() as root:
        w(root, "README.md", "[ok](docs/a.md) [bad](docs/missing.md) [anc](docs/a.md#real-head) "
                             "[anc2](docs/a.md#nope) `docs/b.md` `tools/gone.py` `build/analysis/x.txt` "
                             "`docs/*.md` [web](https://x.org)\n```\n[fenced](docs/zzz.md)\n```\n")
        w(root, "docs/a.md", "# A\n## Real Head\nsee docs/field-log.md:3 and field-log.md:99 and "
                             "`docs/field-log.md:2-4`\n[up](../README.md) [self](#a)\n")
        w(root, "docs/b.md", "# B\n")
        w(root, "docs/orphan.md", "# O\n")
        w(root, "docs/field-log.md", "1\n2\n3\n4\n5\n")
        out, rc, fnd, orph = run(root, list_orphans=True)
        cls = {}
        for f in fnd:
            cls.setdefault(f["class"], []).append(f["target"])
        assert cls["BROKEN"] == ["docs/missing.md", "tools/gone.py"], cls
        assert cls["ANCHOR-MISSING"] == ["docs/a.md#nope"], cls
        assert [t.split(":")[1] for t in cls["LINE-OUT-OF-RANGE"]] == ["99"], cls
        assert cls["NOTE"] == ["build/analysis/x.txt"], cls
        assert rc == 1
        assert orph == ["docs/orphan.md"], orph
        assert "zzz" not in out
        _, rc2, f2, _ = run(root, strict=True)
        assert rc2 == 1 and sum(1 for f in f2 if f["class"] == "BROKEN") == 3
        # clean tree exits 0; NOTE alone does not fail
        w(root, "README.md", "[ok](docs/a.md) `build/analysis/x.txt`\n")
        w(root, "docs/a.md", "# A\n")
        _, rc3, f3, _ = run(root)
        assert rc3 == 0 and [f["class"] for f in f3] == ["NOTE"], f3
        _, rc4, _, _ = run(root, strict=True)
        assert rc4 == 1
        # INDEX.md becomes the orphan root once it exists
        w(root, "docs/INDEX.md", "# I\n[b](b.md)\n")
        _, _, _, o2 = run(root, list_orphans=True)
        assert "docs/b.md" not in o2 and "docs/a.md" in o2, o2
        json.loads(run(root, as_json=True)[0])
    print("selftest OK")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Offline link/reference checker for the docs.")
    ap.add_argument("--root", default=None, help="repo root (default: parent of tools/)")
    ap.add_argument("--strict", action="store_true", help="NOTE, ANCHOR-MISSING, LINE-OUT-OF-RANGE also fail")
    ap.add_argument("--list-orphans", action="store_true", help="list docs not reachable from docs/INDEX.md "
                    "(or README.md/docs/RESUME-HERE.md before INDEX exists)")
    ap.add_argument("--direct", action="store_true", help="orphans: only direct links from the root count")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    root = a.root or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out, rc, _, _ = run(root, a.strict, a.list_orphans, a.direct, a.json)
    sys.stdout.write(out + "\n")
    return rc


if __name__ == "__main__":
    sys.exit(main())
