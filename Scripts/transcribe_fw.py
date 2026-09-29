#!/usr/bin/env python3
"""
transcribe_fw.py - word-level transcription of one speaker's recording.

Transcribes a .wav with faster-whisper (word-level timestamps) and writes a
flat JSON word list that the rest of the pipeline reads directly.

The language is forced rather than auto-detected in this pipeline.

Output JSON: a top-level list of {"text": word, "timestamp": "HH:MM:SS,mmm-HH:MM:SS,mmm"}.
The speaker is set by the pipeline, so no diarization is needed here.

Can also be run on its own, on a single file:
    ./venv/bin/python transcribe_fw.py  INPUT.wav  OUTPUT.json
    ./venv/bin/python transcribe_fw.py  INPUT.wav  OUTPUT.json  --no-vad
"""
import argparse, json, sys


def _seconds_to_timestamp(s):
    """Turns a number of seconds into a written time, as 'HH:MM:SS,mmm'."""
    h = int(s // 3600); s -= 3600 * h
    m = int(s // 60);   s -= 60 * m
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")


def main():
    ap = argparse.ArgumentParser(
        description="Transcribe a .wav to word-level JSON with faster-whisper.")
    ap.add_argument("wav")
    ap.add_argument("out_json")
    ap.add_argument("--model", default="large-v3-turbo",
                    help="faster-whisper model (default: large-v3-turbo)")
    ap.add_argument("--language", default="en")
    ap.add_argument("--speaker", default=None,
                    help="optional speaker label to embed (pipeline sets it anyway)")
    ap.add_argument("--no-vad", action="store_true",
                    help="transcribe the silences too. Slower, but keeps short "
                         "words said alone in a pause, which the speech "
                         "detector can otherwise drop")
    ap.add_argument("--channel", default="1", choices=["1", "2", "mix"],
                    help="which channel to transcribe (default: 1). Do not use "
                         "'mix' on a balanced two-microphone recording: "
                         "averaging the channels can cancel the signal")
    ap.add_argument("--compute-type", default="int8",
                    help="int8 (fast, CPU) / float32 / float16")
    args = ap.parse_args()

    from faster_whisper import WhisperModel, decode_audio

    print(f"Decoding {args.wav} (channel {args.channel}) ...", flush=True)
    if args.channel == "mix":
        # average channels
        audio = decode_audio(args.wav, sampling_rate=16000)
    else:
        # split_stereo returns (left, right); for a mono file both equal the signal
        left, right = decode_audio(args.wav, sampling_rate=16000, split_stereo=True)
        audio = left if args.channel == "1" else right

    print(f"Loading model '{args.model}' and transcribing ...", flush=True)
    model = WhisperModel(args.model, device="cpu", compute_type=args.compute_type)
    segments, info = model.transcribe(
        audio, language=args.language, word_timestamps=True,
        vad_filter=not args.no_vad,
    )

    words = []
    for seg in segments:
        for w in (seg.words or []):
            item = {"text": w.word.strip(),
                    "timestamp": f"{_seconds_to_timestamp(w.start)}-{_seconds_to_timestamp(w.end)}"}
            if args.speaker:
                item["speaker"] = args.speaker
            words.append(item)
        # progress: print each finished segment's end time so long files show life
        print(f"  ... {seg.end:7.1f}s", end="\r", flush=True)

    with open(args.out_json, "w", encoding="utf-8") as f:
        json.dump(words, f, ensure_ascii=False, indent=1)
    print(f"\nWrote {len(words)} words -> {args.out_json}")


if __name__ == "__main__":
    main()
