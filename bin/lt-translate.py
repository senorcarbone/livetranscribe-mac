#!/usr/bin/env python3
"""Swedish -> English text translation via a local llama-server.

Second stage of the pipeline. Whisper's own --translate head renders Swedish
business idiom literally ("skjuta upp nyanställningarna" -> "shoot up the new
employees"), so instead we transcribe Swedish accurately and translate the
*text* here, with the meeting's preceding lines as context.

  lt-translate.py --port 8080 "svensk text" [--prev-sv X --prev-en Y]
  lt-translate.py --port 8080 --file transcript_sv.txt
  lt-translate.py --port 8080 --srt final_sv.srt
"""
import argparse, json, re, sys, urllib.error, urllib.request

SYSTEM = (
    "You are a professional Swedish-to-English interpreter for a corporate board "
    "meeting. Translate the Swedish into natural, formal English.\n"
    "Rules:\n"
    "- Output ONLY the translation. No commentary, no quotation marks, no notes.\n"
    "- Preserve every number, percentage, currency amount, date and proper name exactly.\n"
    "- Render Swedish business idiom by MEANING, never word-for-word. For example "
    "'skjuta upp' means postpone (not shoot), 'lägga ner' means discontinue, "
    "'ta upp' means raise a topic, 'gå igenom' means review.\n"
    "- If the Swedish is a mid-sentence fragment, translate it as a fragment. "
    "Never invent content that is not there.\n"
    "- If the Swedish is already English or is empty, return it unchanged."
)

def translate(text, port, prev_sv=None, prev_en=None, timeout=60):
    text = (text or "").strip()
    if not text:
        return ""
    msgs = [{"role": "system", "content": SYSTEM}]
    if prev_sv and prev_en:
        # prior turn as an example keeps terminology and names consistent
        msgs += [{"role": "user", "content": prev_sv.strip()},
                 {"role": "assistant", "content": prev_en.strip()}]
    msgs.append({"role": "user", "content": text})

    body = json.dumps({
        "messages": msgs,
        "temperature": 0.1,
        "top_p": 0.9,
        "max_tokens": 512,
        "stream": False,
    }).encode()

    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/v1/chat/completions",
        data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        out = json.load(r)["choices"][0]["message"]["content"]

    out = out.strip()
    # models occasionally wrap output in quotes or add a lead-in despite the rules
    out = re.sub(r'^(translation|english)\s*:\s*', '', out, flags=re.I).strip()
    if len(out) > 1 and out[0] in '"“' and out[-1] in '"”':
        out = out[1:-1].strip()
    return " ".join(out.split())

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("text", nargs="?", default="")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--prev-sv", default="")
    ap.add_argument("--prev-en", default="")
    ap.add_argument("--file", help="translate a whole file, line by line")
    ap.add_argument("--srt", help="translate an .srt, keeping indices and timings")
    a = ap.parse_args()

    try:
        if a.srt:
            prev_sv = prev_en = ""
            blocks = re.split(r"\n\s*\n", open(a.srt).read().strip())
            out_blocks = []
            for b in blocks:
                lines = b.splitlines()
                if len(lines) < 3:
                    out_blocks.append(b); continue
                idx, timing, text = lines[0], lines[1], " ".join(lines[2:]).strip()
                en = translate(text, a.port, prev_sv, prev_en)
                if en:
                    prev_sv, prev_en = text, en
                out_blocks.append(f"{idx}\n{timing}\n{en or text}")
            print("\n\n".join(out_blocks) + "\n")
        elif a.file:
            prev_sv = prev_en = ""
            with open(a.file) as fh:
                for line in fh:
                    line = line.rstrip("\n")
                    if not line.strip():
                        print(); continue
                    # keep a leading [hh:mm:ss] stamp out of the translation
                    m = re.match(r'^(\[\d\d:\d\d:\d\d\]\s*)(.*)$', line)
                    stamp, body = (m.group(1), m.group(2)) if m else ("", line)
                    en = translate(body, a.port, prev_sv, prev_en)
                    print(f"{stamp}{en}", flush=True)
                    if en:
                        prev_sv, prev_en = body, en
        else:
            # Live line: better to drop one translation than freeze the screen.
            print(translate(a.text, a.port, a.prev_sv, a.prev_en, timeout=15))
    except TimeoutError:
        print("lt-translate: translation timed out", file=sys.stderr)
        sys.exit(4)
    except urllib.error.URLError as e:
        print(f"lt-translate: cannot reach llama-server on port {a.port}: {e}",
              file=sys.stderr)
        sys.exit(3)

if __name__ == "__main__":
    main()
