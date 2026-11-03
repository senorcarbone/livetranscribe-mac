#!/usr/bin/env python3
"""Follow a growing raw PCM stream and cut it into utterances.

Emits one line per completed utterance: "<index> <start_seconds>", having
written that utterance to <workdir>/.utt_<index>.wav. Boundaries fall in
silence, so the transcriber always sees a whole phrase — no fixed-interval
chunking, no mid-word cuts, and nothing to deduplicate afterwards.

Exits once the stream stops growing, flushing whatever speech is in hand.
"""
import argparse, os, sys, time, wave
import numpy as np

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("raw")
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--rate", type=int, default=48000)
    ap.add_argument("--frame-ms", type=int, default=20)
    ap.add_argument("--silence-ms", type=int, default=700,
                    help="silence needed to close an utterance")
    ap.add_argument("--min-speech-ms", type=int, default=300,
                    help="shorter bursts are treated as noise")
    ap.add_argument("--max-ms", type=int, default=12000,
                    help="force a cut so latency stays bounded")
    ap.add_argument("--soft-ms", type=int, default=0,
                    help="past this length, a short pause is enough to cut (0 = off)")
    ap.add_argument("--soft-silence-ms", type=int, default=160,
                    help="the short pause that --soft-ms accepts")
    ap.add_argument("--pad-ms", type=int, default=200,
                    help="keep this much either side of the speech")
    ap.add_argument("--eof-idle", type=float, default=3.0,
                    help="seconds without growth that mean recording ended")
    a = ap.parse_args()

    fsz = int(a.rate * a.frame_ms / 1000)          # samples per frame
    need_sil = max(1, a.silence_ms // a.frame_ms)
    need_speech = max(1, a.min_speech_ms // a.frame_ms)
    max_frames = max(1, a.max_ms // a.frame_ms)
    soft_frames = a.soft_ms // a.frame_ms if a.soft_ms else 0
    need_soft_sil = max(1, a.soft_silence_ms // a.frame_ms)
    pad = int(a.rate * a.pad_ms / 1000)

    # Wait for the recorder to create the file.
    t0 = time.time()
    while not os.path.exists(a.raw):
        if time.time() - t0 > 30:
            print("lt-segment: raw stream never appeared", file=sys.stderr)
            return 1
        time.sleep(0.1)

    fh = open(a.raw, "rb")
    buf = np.zeros(0, dtype=np.int16)   # audio held for the current utterance
    buf_start = 0                       # sample index of buf[0] in the stream
    consumed = 0                        # samples read from the file so far
    tail = np.zeros(0, dtype=np.int16)  # pre-speech padding carried along
    in_speech = False
    sil_run = 0
    speech_frames = 0
    idx = 0
    floor_db = -60.0
    last_growth = time.time()

    def emit(audio, start_sample):
        nonlocal idx
        if audio.size < int(a.rate * a.min_speech_ms / 1000):
            return
        idx += 1
        path = os.path.join(a.workdir, f".utt_{idx:05d}.wav")
        with wave.open(path, "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(a.rate)
            w.writeframes(audio.tobytes())
        print(f"{idx} {start_sample / a.rate:.2f}", flush=True)

    while True:
        chunk = fh.read(fsz * 2)
        if len(chunk) < fsz * 2:
            # Partial frame: rewind so we re-read it once it is complete.
            if chunk:
                fh.seek(-len(chunk), os.SEEK_CUR)
            if time.time() - last_growth > a.eof_idle:
                if in_speech and speech_frames >= need_speech:
                    emit(buf, buf_start)
                break
            time.sleep(0.05)
            continue

        last_growth = time.time()
        frame = np.frombuffer(chunk, dtype=np.int16)
        consumed += frame.size

        rms = float(np.sqrt(np.mean(frame.astype(np.float64) ** 2))) + 1e-9
        db = 20 * np.log10(rms / 32768.0)

        # Track the quiet background and sit a margin above it, so this works
        # in a silent room and a noisy one without tuning.
        if not in_speech:
            floor_db = min(floor_db + 0.05, 0.9 * floor_db + 0.1 * db)
        thresh = max(floor_db + 9.0, -52.0)

        if db > thresh:
            if not in_speech:
                in_speech = True
                sil_run = 0
                speech_frames = 0
                buf = tail.copy()
                buf_start = consumed - frame.size - tail.size
            buf = np.concatenate((buf, frame))
            speech_frames += 1
            sil_run = 0
            if speech_frames >= max_frames:
                emit(buf, buf_start)
                in_speech = False
                buf = np.zeros(0, dtype=np.int16)
                tail = frame[-pad:] if pad else np.zeros(0, dtype=np.int16)
        else:
            if in_speech:
                buf = np.concatenate((buf, frame))
                sil_run += 1
                # A long utterance closes on a breath rather than a full pause,
                # so text keeps flowing during continuous speech.
                long_enough = soft_frames and speech_frames >= soft_frames
                if sil_run >= need_sil or (long_enough and sil_run >= need_soft_sil):
                    if speech_frames >= need_speech:
                        emit(buf, buf_start)
                    in_speech = False
                    buf = np.zeros(0, dtype=np.int16)
                    tail = frame[-pad:] if pad else np.zeros(0, dtype=np.int16)
            else:
                tail = np.concatenate((tail, frame))[-pad:] if pad else tail

    fh.close()
    return 0

if __name__ == "__main__":
    sys.exit(main())
