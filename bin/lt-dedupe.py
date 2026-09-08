#!/usr/bin/env python3
"""Strip from NEW the leading words already emitted at the tail of PREV.

Overlapping audio windows re-transcribe the last seconds, so the same words
arrive twice — but rarely identically: a word clipped by the old window's edge
comes back complete ("dagens" -> "dagordningen"), and casing/punctuation move.
So the overlap is matched by best word-agreement ratio, not exact equality.

Usage: lt-dedupe.py <prev> <new>
"""
import re, sys

def norm(w):
    return re.sub(r"[^0-9a-zà-öø-ÿ]", "", w.lower())

prev = sys.argv[1] if len(sys.argv) > 1 else ""
new  = sys.argv[2] if len(sys.argv) > 2 else ""

pw, nw = prev.split(), new.split()
if not pw or not nw:
    print(new.strip()); raise SystemExit

pn = [norm(w) for w in pw]
nn = [norm(w) for w in nw]

MAXK = min(len(pn), len(nn), 40)
best_k, best_score = 0, 0.0
for k in range(MAXK, 1, -1):
    tail, head = pn[-k:], nn[:k]
    hits = sum(1 for a, b in zip(tail, head) if a == b and a)
    ratio = hits / k
    # long, mostly-agreeing overlaps win; short ones must be near-exact
    need = 0.6 if k >= 4 else 1.0
    if ratio >= need and ratio * k > best_score:
        best_k, best_score = k, ratio * k

out = " ".join(nw[best_k:]).strip()
print(out if len(out) > 1 else "")
