"""Reads a transcript file and turns it into a list of words with their
times.

The file is the one transcribe_fw.py writes: a flat list of
{"text": word, "timestamp": "HH:MM:SS,mmm-HH:MM:SS,mmm"}.

Gives back one entry per word: {speaker, word, tStart, tEnd}.
"""
import json


def _timestamp_to_seconds(v):
    """Turns a written time into a number of seconds.

    Accepts the usual ways of writing one: '11,580', '00:11,580',
    '00:01:23,450' or '1:23.45'.
    """
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(",", ".")
    parts = [float(p) for p in s.split(":")]
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    return parts[0] * 3600 + parts[1] * 60 + parts[2]


def _append(out, item, default_speaker):
    word = str(item.get("word", item.get("text", ""))).strip()
    if "start" in item and "end" in item:
        t1, t2 = float(item["start"]), float(item["end"])
    elif "timestamp" in item:
        parts = str(item["timestamp"]).split("-")
        if len(parts) != 2:
            return
        t1, t2 = _timestamp_to_seconds(parts[0]), _timestamp_to_seconds(parts[1])
    else:
        return
    spk = str(item.get("speaker") or default_speaker)
    out.append({"speaker": spk, "word": word, "tStart": t1, "tEnd": t2})


def import_transcript(path, default_speaker):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError(
            f"{path} is not a transcript this pipeline can read: it should be "
            "a list of words, as written by transcribe_fw.py.")

    out = []
    for item in data:
        _append(out, item, default_speaker)

    out = [t for t in out if t["word"]]
    out.sort(key=lambda t: t["tStart"])
    print(f"Imported {len(out)} words from {path} (speaker: {default_speaker})")
    return out
