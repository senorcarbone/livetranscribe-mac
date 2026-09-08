#!/usr/bin/env python3
"""Summarise a meeting transcript and write a .docx via macOS textutil.

Map-reduce so it works for a meeting of any length: each slice of the
transcript is condensed to notes, then the notes are merged into one summary.
Talks to a local llama-server; nothing leaves the machine.
"""
import argparse, html, json, os, re, subprocess, sys, tempfile
import urllib.error, urllib.request

MAP_SYS = (
    "You are reading part of a meeting transcript. Extract only what is actually "
    "stated. Produce short bullets under these headings, omitting any heading with "
    "nothing under it: Points, Decisions, Actions (who does what, and by when if "
    "said), Figures (numbers, money, percentages, dates), Questions.\n"
    "Never invent names, numbers or commitments. The transcript is machine-generated "
    "and may contain errors; do not smooth them into false specifics."
)
REDUCE_SYS = (
    "You are writing the summary of a meeting from notes taken across it. Output "
    "GitHub-flavoured Markdown with these sections, skipping any that would be empty:\n"
    "## Summary  — three to five sentences of plain prose.\n"
    "## Key points — bullets.\n"
    "## Decisions — bullets; only things actually decided.\n"
    "## Action items — bullets as **owner** — task — due date if stated.\n"
    "## Figures mentioned — bullets, exactly as stated.\n"
    "## Open questions — bullets.\n"
    "Be faithful to the notes. Do not invent owners, dates or numbers. Do not add "
    "commentary about the transcript itself."
)

def call(port, system, user, max_tokens=1400, timeout=600):
    body = json.dumps({
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "temperature": 0.2, "top_p": 0.9, "max_tokens": max_tokens, "stream": False,
    }).encode()
    req = urllib.request.Request(f"http://127.0.0.1:{port}/v1/chat/completions",
                                 data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)["choices"][0]["message"]["content"].strip()

def slices(text, limit=5000):
    """Split on line boundaries into pieces of at most ~limit characters."""
    out, cur = [], ""
    for line in text.splitlines():
        if len(cur) + len(line) + 1 > limit and cur:
            out.append(cur); cur = ""
        cur += line + "\n"
    if cur.strip():
        out.append(cur)
    return out

def md_to_html(md):
    """Minimal Markdown -> HTML: headings, bullets, bold. Enough for textutil."""
    out, in_ul = [], False
    for raw in md.splitlines():
        line = raw.rstrip()
        if not line.strip():
            if in_ul: out.append("</ul>"); in_ul = False
            continue
        m = re.match(r'^(#{1,4})\s+(.*)$', line)
        if m:
            if in_ul: out.append("</ul>"); in_ul = False
            lvl = len(m.group(1)) + 1
            out.append(f"<h{lvl}>{inline(m.group(2))}</h{lvl}>")
            continue
        m = re.match(r'^\s*[-*•]\s+(.*)$', line)
        if m:
            if not in_ul: out.append("<ul>"); in_ul = True
            out.append(f"<li>{inline(m.group(1))}</li>")
            continue
        if in_ul: out.append("</ul>"); in_ul = False
        out.append(f"<p>{inline(line)}</p>")
    if in_ul: out.append("</ul>")
    return "\n".join(out)

def inline(s):
    s = html.escape(s)
    s = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', s)
    s = re.sub(r'(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)', r'<i>\1</i>', s)
    return s

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("transcript")
    ap.add_argument("--port", type=int, default=8130)
    ap.add_argument("--title", default="Meeting")
    ap.add_argument("--outdir", default=None)
    ap.add_argument("--no-doc", action="store_true")
    a = ap.parse_args()

    text = open(a.transcript, encoding="utf-8").read().strip()
    if not text:
        print("Transcript is empty — nothing to summarise.", file=sys.stderr)
        return 2
    outdir = a.outdir or os.path.dirname(os.path.abspath(a.transcript))
    os.makedirs(outdir, exist_ok=True)

    # timestamps help nobody summarise; keep them only for the document body
    plain = re.sub(r'^\[\d\d:\d\d:\d\d\]\s*', '', text, flags=re.M)

    parts = slices(plain)
    try:
        if len(parts) == 1:
            summary = call(a.port, REDUCE_SYS, "Notes:\n\n" + parts[0])
        else:
            notes = []
            for i, p in enumerate(parts, 1):
                print(f"  summarising part {i}/{len(parts)}…", flush=True)
                notes.append(call(a.port, MAP_SYS, p, max_tokens=700))
            print("  merging…", flush=True)
            summary = call(a.port, REDUCE_SYS, "Notes:\n\n" + "\n\n---\n\n".join(notes))
    except urllib.error.URLError as e:
        print(f"lt-summarize: cannot reach llama-server on {a.port}: {e}", file=sys.stderr)
        return 3

    md_path = os.path.join(outdir, "summary.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# {a.title}\n\n{summary}\n")
    print(f"  wrote {md_path}")

    if a.no_doc:
        return 0

    body = (f"<h1>{html.escape(a.title)}</h1>\n{md_to_html(summary)}\n"
            f"<h2>Full transcript</h2>\n"
            + "\n".join(f"<p>{html.escape(l)}</p>" for l in text.splitlines() if l.strip()))
    page = ('<html><head><meta charset="utf-8">'
            f'<title>{html.escape(a.title)}</title></head><body>{body}</body></html>')
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as t:
        t.write(page); tmp = t.name
    docx = os.path.join(outdir, "meeting.docx")
    r = subprocess.run(["textutil", "-convert", "docx", "-output", docx, tmp],
                       capture_output=True, text=True)
    os.unlink(tmp)
    if r.returncode != 0:
        print(f"  textutil failed: {r.stderr.strip()}", file=sys.stderr)
        return 4
    print(f"  wrote {docx}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
