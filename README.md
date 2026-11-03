# livetranscribe-mac

Live meeting transcription on an Apple Silicon Mac, **fully offline** — no audio or
text ever leaves the machine, which is what makes it usable for a confidential board
meeting.

Two modes:

| | Command | What you get |
|---|---|---|
| **Swedish** | `livetranscribe` | Swedish + English side by side |
| **English** | `livetranscribe -E` | English text only, then a summary + `.docx` |

Both emit **one line per utterance**, cut in the silence around each phrase rather than
on a fixed timer, so every line is a whole thought.

Swedish→English does **not** use Whisper's own translation, which renders business
idiom literally ("skjuta upp nyanställningarna" → "shoot up the new employees").
Instead Whisper transcribes the Swedish and a local Gemma 3 12B translates the text.
See [About the English](#about-the-english).

## Requirements

- macOS on Apple Silicon. Developed and tested on an **M4 Pro / 24 GB**, macOS 26.
  Not tested on Intel, on other Apple Silicon tiers, or on Linux.
- [Homebrew](https://brew.sh)
- ~8.4 GB of disk for models, ~8 GB of RAM free while running
- Microphone access for your terminal application

## Install

```sh
git clone https://github.com/<you>/livetranscribe-mac.git
cd livetranscribe-mac
./bin/lt-setup
```

`lt-setup` installs `ffmpeg`, `whisper-cpp` and `llama.cpp` via Homebrew, then fetches
the models into `~/.whisper-models`. It is safe to re-run and skips whatever is already
present. The Gemma download is 7.3 GB and HuggingFace throttles anonymous connections
to near zero after about a minute, so the script reconnects and resumes in a loop
rather than trusting one long transfer.

Then grant your terminal microphone access under
**System Settings → Privacy & Security → Microphone**, and do a dry run:

```sh
./bin/livetranscribe -E        # talk for 30 seconds, Ctrl-C
./bin/lt-checkaudio            # confirm the recording is clean
```

## Status

Working and used, with one honest caveat: every automated test was driven through the
file-rehearsal path (`-i FILE`), because the microphone stopped returning audio to the
test harness partway through development. The live microphone path is exercised by
hand, not by tests. Run the dry run above before trusting it with a real meeting.

Output goes to `~/Documents/livetranscribe/<date>_<time>/` — deliberately outside this
repository so recordings can never be committed. Override with `-o` or `$LT_OUTDIR`.

## Swedish mode

```sh
./bin/livetranscribe
```

One line per utterance. The Swedish appears about a second after the speaker pauses and
the English follows roughly 1.6 s later, because it is not held back waiting for the
translation.

Continuous speech does not stall the screen: once an utterance passes 4 s, any short
breath ends the line, and none runs past 7 s. On a 37 s unbroken monologue that gives an
English line every 4–7 s (first after ~8.5 s), where a 12 s cap left gaps of 10–13 s.

If the microphone delivers pure silence — what macOS does when the terminal lacks
microphone permission — a red warning appears a few seconds in instead of an empty run.

Segmenting on speech helps the translation as much as the transcription: a whole
sentence translates correctly where a fragment does not. On fixed intervals the
fragment "Framför" (the start of "framför allt personalkostnaderna") was rendered as
"Moving on"; as part of a complete utterance it becomes "Primarily personnel costs".

A running transcript prints with Swedish (blue) above English (green). `Ctrl-C` stops
and saves.

The Swedish appears as soon as it is transcribed, roughly **5 s** behind the room; the
English follows about **1.6 s** later. It is not word-by-word streaming — Whisper needs
a block of audio to be accurate — but you see the Swedish without waiting on the
translation. `-s 3` shaves another second at the cost of more mid-sentence breaks; if
the Mac cannot keep up at your chosen step, it says so and you should raise `-s`.

| Flag | Meaning | Default |
|---|---|---|
| `-d N` | audio input device index | `0` (MacBook Pro Microphone) |
| `-s N` | seconds of new audio per step — lower = faster, more chopped | `4` |
| `-o DIR` | output directory | `~/Documents/livetranscribe` (or `$LT_OUTDIR`) |
| `-i FILE` | rehearse from an audio file instead of the mic | — |
| `-w` | use Whisper's own translation instead of stage 2 (not recommended) | off |
| `-E` | English-audio mode (see below) | off |
| `-S` | skip the automatic summary in English mode | off |
| `-T` | fixed-interval chunks instead of utterance segmentation | off |
| `-N` | discard the audio on exit — text only | off (audio kept) |

List devices: `./bin/livetranscribe -l`

On startup it loads the translation model once (a few seconds); it stays resident for
the whole meeting rather than reloading per chunk.

## English mode

For meetings held in English. There is no translation stage, so it is the faster of
the two.

```sh
./bin/livetranscribe -E
```

One line per utterance, appearing roughly a second after the speaker pauses.

That is what fixes the fragmenting: on a timer, "forty two million" straddled a boundary
and came out as `Revenue came in at $42.` / `up 12% Euro`. Segmented on speech, the same
audio gives `Revenue came in at 42 million, up 12% year over year.` — identical to what
Whisper produces from the whole file at once.

### Utterance segmentation, in both modes

Speech detection tracks the room's noise floor and sits a margin above it, so it needs
no tuning for a quiet or a noisy room. A phrase running longer than 12 s is cut anyway
to keep latency bounded; that cut can mangle the word it lands on, but nothing is lost
either side of it. In practice only unbroken monologue reaches that limit.

`-T` reverts to fixed intervals, and `-s` sets their length. Under utterance
segmentation `-s` has no meaning and the tool says so rather than ignoring it.

On `Ctrl-C` it transcribes, then automatically writes a summary and a Word document:

- `transcript.txt` — timestamped text
- `summary.md` — Summary, Key points, Decisions, Action items, Figures, Open questions
- `meeting.docx` — the summary **and** the full transcript, openable in Word/Pages
- `full_audio.wav`

The summary is produced by the same local Gemma 3 12B, so it loads the 7.3 GB model
after recording stops — about a minute. `-S` skips it; `Ctrl-C` during it also skips it,
and the transcript is already safely on disk by then.

Summarise any transcript later, including a Swedish one:

```sh
./bin/lt-summary <transcript.txt> "Board meeting 12 Sept"
```

It map-reduces, so meeting length is not a limit.

### On step size

`-s` applies to Swedish mode and to English `-T`, setting how often text is emitted.
Shorter is not automatically better: at `-s 2` Whisper sees too little context and
starts inventing. English mode's default utterance segmentation sidesteps the question
entirely, which is why it is the default.

## Zoom, Teams and other calls

It records from a **CoreAudio input device**, so it works with any microphone
(`-l` to list, `-d N` to pick). Capturing a video call needs one more piece, because
remote participants come out of your speakers — they are not on your mic.

`ZoomAudioDevice` and `Microsoft Teams Audio` appear in the device list, but they are
those apps' own private drivers, not general loopback. Do not expect meeting audio
from them.

**Live transcription of a call** — install a loopback device once:

```sh
brew install --cask blackhole-2ch      # needs your admin password; log out/in after
```

Then in **Audio MIDI Setup** (in /Applications/Utilities):

1. **Aggregate Device** — tick your microphone **and** BlackHole 2ch. This is what you
   pass to `-d`; it carries both your room and the remote voices.
2. **Multi-Output Device** — tick your speakers/headphones **and** BlackHole 2ch. Select
   it as the system output so you still hear the call while it is being captured.
3. In Zoom, leave speaker set to the Multi-Output Device.

Then `livetranscribe -l` to find the aggregate device's number and run with `-d N`.

**Without installing anything** — use the call's own recording, then process it after:

```sh
# Zoom: "Record to this Computer" -> ~/Documents/Zoom/<meeting>/audio_only.m4a
./bin/lt-final ~/Documents/Zoom/<meeting>/audio_only.m4a
./bin/lt-summary <that folder>/final/final_en.txt "Board meeting"
```

Any format ffmpeg reads works — `.m4a`, `.mp3`, `.mp4`, `.wav`. Verified with an
`.m4a`. This is not live, but the audio is cleaner than anything a room mic captures,
and each participant is recorded from their own microphone.

**Headphones caveat:** on a hybrid call with headphones and no loopback, the mic hears
only the people physically in the room. On speakers it hears the remote voices badly —
echoey and clipped by the call's own echo cancellation. Loopback or the call recording
are the only good options.

**Before you record participants:** tell them. In an EU/GDPR setting a board recording
normally needs to be announced and minuted.

## Output

Each run writes `~/Documents/livetranscribe/<date>_<time>/`. Swedish mode:

- `transcript.md` — paired Swedish + English, timestamped
- `transcript_sv.txt`, `transcript_en.txt` — one language each
- `full_audio.wav` — the whole recording (~115 MB/hour)

English mode writes `transcript.txt`, `summary.md`, `meeting.docx` and `full_audio.wav`.

## After the meeting

```sh
./bin/lt-final ~/Documents/livetranscribe/<run>/full_audio.wav
```

Re-runs the Swedish with full beam search and Silero VAD (so it splits on real pauses
rather than arbitrary 30-second cuts), then translates that transcript with the same
stage-2 model. Writes `.txt` and `.srt` into a `final/` subfolder. Use this for anything
that goes on record. Add `-w` to compare against Whisper's own translation.

## About the English
<a id="about-the-english"></a>

The English comes from a **two-stage** pipeline: Whisper transcribes the Swedish
accurately, then a local Gemma 3 12B translates that *text*. This exists because
Whisper's own `--translate` head renders Swedish business idiom literally. Measured on
the same sentence:

| | Output |
|---|---|
| Swedish | "…styrelsen beslutar att **skjuta upp** nyanställningarna" |
| Whisper translate | "…the board decides to **fire** new employees" / "to **shoot up** the new employees" |
| Two-stage (default) | "…the board decides to **postpone** new hires" |

Other idiom the two-stage pass gets right and Whisper did not: "lägga ner" →
discontinue, "ta upp frågan" → raise the matter, "invändningar" → objections
(Whisper: "changes"). Numbers, percentages and names came through exactly in testing
("12%", "42 million kronor", "Anna Lindqvist"), and a mid-sentence fragment was
translated as a fragment rather than completed with invented content.

`-w` switches back to Whisper's translation. It is kept for comparison, not for use.

### Still verify before it becomes minutes

Two-stage is much better, not infallible — it is a 12B model doing the translating.
The Swedish transcript remains the authoritative record. Check any figure or decision
against `final_sv.txt` or the audio before it goes on record.

## Other limits

- No speaker labels — one continuous stream, not "who said what".
- Overlapping speech degrades badly.
- Proper nouns and numbers are the usual error sites on the Swedish side too.

## Not keeping the audio

`-N` discards the recording when the run ends, leaving only the transcript:

```sh
./bin/livetranscribe -E -N
```

Worth knowing what you give up: `lt-final` needs the audio, so there is no
higher-accuracy second pass and no way to check a figure against what was said. The
live transcript becomes the only record, and it is the less accurate of the two. For
minutes that matter, keeping the audio until the meeting is written up is usually the
better trade.

Also note this is not the same as never writing audio to disk. The capture stream is
buffered to a file while running because the transcriber reads back from it; `-N` means
that file is deleted on exit rather than converted to `full_audio.wav`. If audio must
never touch the disk at all, that needs a different design — say so and it can be piped
instead.

## Checking a recording

```sh
./bin/lt-checkaudio          # newest meeting, or pass a .wav
```

Reports the WAV header state, level, and whether clicks cluster on buffer boundaries
(the signature of a capture glitch). Worth running once after your next real meeting.

### Two capture bugs fixed on 2026-09-08

An early recording had an audible buzz. Measured causes, both now fixed:

- **Resampling in the realtime path.** Capture forced 48 kHz→16 kHz inside the live
  ffmpeg while Whisper and a 12B model competed for the CPU. Clicks landed on exact
  buffer boundaries — 217× more concentrated than chance — giving a ~31 Hz buzz.
  Capture is now at the device's native 48 kHz with no realtime resampling and a single
  output; each chunk is resampled offline instead.
- **Unfinalised WAV header.** `full_audio.wav` was written by the live ffmpeg, which
  gets killed on Ctrl-C, leaving RIFF size at `0xFFFFFFFF` — a file claiming to be 37
  hours long. The archive is now converted from the raw stream after recording stops,
  so its header is always correct.

If the machine is ever hard-killed (`kill -9`), `stream.raw` survives in the run folder.
Recover it with:
`ffmpeg -f s16le -ar 48000 -ac 1 -i stream.raw -ar 16000 full_audio.wav`

## Disk and memory

Models live in `~/.whisper-models`, 8.4 GB total as `du` reports it: Gemma 3 12B
Q4_K_M 6.8 GB, large-v3 1.0 GB (only needed for `-w`), large-v3-turbo 547 MB,
Silero VAD 864 KB. At runtime the two resident models want roughly 8 GB of your 24 GB.

If you never intend to use `-w`, `rm ~/.whisper-models/ggml-large-v3-q5_0.bin`
reclaims 1.0 GB; the default path does not touch it.

## Before the meeting — do these

1. **Microphone permission.** The recorder fails immediately without it:
   System Settings → Privacy & Security → Microphone → enable your terminal app.
2. **Dry run.** Start it, speak Swedish for 30 seconds, confirm text appears.
3. **Mic placement beats every setting.** A table/boundary mic in the middle of the
   table is a far bigger win than any flag here. Whisper handles accents well; it does
   not handle distant, reverberant, overlapping speech.
4. **Stay on mains power** — both models run on the GPU.
5. **Allow ~90 seconds of startup** the first time each day, while the 7.3 GB
   translation model loads. Start it before people sit down.

## How it works

**Stage 1 — Swedish.** `ffmpeg` writes one continuous raw 16 kHz stream. Every 6 seconds the worker slices a
window that includes the previous 2 seconds, so no word sits on an unheard boundary,
and runs two Whisper passes: `large-v3-turbo` for the Swedish, `large-v3 --translate`
for the English. `lt-dedupe.py` removes the re-heard overlap from the front of each new
window by best word-agreement ratio — fuzzy, because a word clipped by the previous
window comes back in a different form ("dagens" → "dagordningen").

**Stage 2 — English.** `llama-server` holds Gemma 3 12B resident for the whole meeting
(loading it per chunk would be impossible), and `lt-translate.py` sends each deduped
Swedish line with the previous line-pair as context, so terminology and names stay
consistent. Because the English is derived from the already-deduped Swedish, the two
columns cannot drift apart.

Measured cost per step: ~1.1 s Whisper + ~1.6 s translation, against a 4-second
budget — it keeps up, with headroom. The Swedish is printed before the translation
starts, so it is not delayed by it.

Note that **`large-v3-turbo` cannot translate** — it was distilled on transcription
only, and `--translate` silently returns Swedish. Verified here. That model is only
used in the legacy `-w` path.

The 2-second overlap is load-bearing. Before it, fixed 6-second chunks silently dropped
"till fyrtiotvå miljoner kronor" and "framför allt personalkostnaderna" — content that
fell across boundaries vanished with no indication anything was missing.

Windows quieter than −47 dB are skipped, and a junk filter drops Whisper's
silence hallucinations ("Tack för att du tittade", "Undertexter av…").
