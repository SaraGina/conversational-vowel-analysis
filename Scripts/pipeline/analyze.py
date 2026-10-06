"""Fills in the remaining columns and writes the Excel.

Looks each word up in the vocabulary to fill its pair, vowel, tensity and
consonant environment; converts F1 and F2 to the Bark scale; numbers the
trials, the productions of each speaker and the discussion segments; and
writes everything to one spreadsheet.
"""
import csv
import os
import openpyxl
from openpyxl.styles import Font

from .words import clean

COLUMN_ORDER = [
    "Trial", "Pair", "Word", "Speaker",
    "Production_Confederate", "Production_Participant",
    "Timestamp", "Onset", "Offset", "WordDuration",
    "VowelStart", "VowelEnd", "VowelDuration", "Ratio",
    "Vowel", "Tensity", "Env", "F1", "F1_Bark", "F2", "F2_Bark",
    "BlackScreen", "Segment", "WordCheck", "Check", "LabelReview", "EchoCheck",
    "Boundaries", "HeardAs",
    "LevelDiff_dB", "AudioFile", "tStart", "tEnd",
]


def bark(f):
    return None if f is None else 26.81 / (1 + 1960 / f) - 0.53


def load_vocab(path):
    vocab = {}
    if not os.path.isfile(path):
        print(f"WARNING: vocabulary not found ({path}); "
              "Pair/Env/Vowel/Tensity will be empty.")
        return vocab
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            w = clean(row.get("word", ""))
            if w and w not in vocab:
                vocab[w] = row
    return vocab


def annotate(results, sets, set_words, core_all, vocab, speaker_a, speaker_b,
             segment_gap=45.0, blackscreen=None):
    """sets: list of (name, [core words]); set_words: list of expanded word
    lists (same order); core_all: set of all core words."""
    set_names = [s[0] for s in sets]

    for r in results:
        comp = [clean(w) for w in str(r["Word"]).split("/")]

        # A - copy the word's features from the vocabulary file
        # Taking pair, environment, vowel and tensity from the first spelling
        # that is listed there, and leaving them empty when none is.
        r.update({"Pair": "", "Env": "", "Vowel": "", "Tensity": ""})
        for c in comp:
            if c in vocab:
                v = vocab[c]
                r["Pair"] = v.get("pair") or ""
                r["Env"] = v.get("env") or ""
                r["Vowel"] = v.get("vowel") or ""
                r["Tensity"] = v.get("tensity") or ""
                break

        r["Ratio"] = (r["VowelDuration"] / r["WordDuration"]
                      if r["WordDuration"] else None)
        r["F1_Bark"] = bark(r["F1"])
        r["F2_Bark"] = bark(r["F2"])
        r["Timestamp"] = f"{int(r['Onset'] // 60):02d}:{r['Onset'] % 60:06.3f}"

        # B - number the trial: the first set that lists any of the spellings
        r["Trial"] = 0
        for i, sw in enumerate(set_words):
            if any(c in sw for c in comp):
                r["Trial"] = i + 1
                break

        # C - flag rows found only through a neighbour spelling
        # Marking them VARIANT so the word is confirmed by ear, and giving them
        # the pair of the set they matched when the vocabulary gave none.
        r["LabelReview"] = ""
        if not any(c in core_all for c in comp):
            r["LabelReview"] = "VARIANT"
            if r["Trial"] > 0 and not r["Pair"]:
                r["Pair"] = set_names[r["Trial"] - 1]

        # D - flag rows whose word was found inside a longer token
        # The timestamps are that longer token's, so the word and vowel
        # boundaries need checking against the audio before the row is used.
        r["HeardAs"] = r.get("HeardAs") or ""
        r["Boundaries"] = "PARTIAL" if r["HeardAs"] else ""

        # E - flag rows that fall inside a scheduled black screen
        r["BlackScreen"] = ""
        if blackscreen and blackscreen.get("every"):
            first = blackscreen.get("first", 0)
            if (r["Onset"] >= first and
                    (r["Onset"] - first) % blackscreen["every"]
                    < blackscreen.get("dur", 15)):
                r["BlackScreen"] = "BS"

    # F - number each speaker's productions within a trial, in time order
    for r in results:
        r["Production_Confederate"] = None
        r["Production_Participant"] = None
    for t in sorted({r["Trial"] for r in results if r["Trial"] > 0}):
        rows = sorted((r for r in results if r["Trial"] == t),
                      key=lambda r: r["Onset"])
        c_cnt = p_cnt = 0
        for r in rows:
            if r["Speaker"] == speaker_a:
                c_cnt += 1
                r["Production_Confederate"] = c_cnt
            elif r["Speaker"] == speaker_b:
                p_cnt += 1
                r["Production_Participant"] = p_cnt

    # G - number the segments: a gap longer than segment_gap starts a new one
    for r in results:
        r["Segment"] = 0
    for t in sorted({r["Trial"] for r in results if r["Trial"] > 0}):
        rows = sorted((r for r in results if r["Trial"] == t),
                      key=lambda r: r["Onset"])
        seg = 1
        for i, r in enumerate(rows):
            if i > 0 and r["Onset"] - rows[i - 1]["Onset"] > segment_gap:
                seg += 1
            r["Segment"] = seg

    results.sort(key=lambda r: r["Onset"])
    return results


def write_excel(results, out_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(COLUMN_ORDER)
    for c in ws[1]:
        c.font = Font(bold=True)
    for r in results:
        ws.append([r.get(col) for col in COLUMN_ORDER])
    wb.save(out_path)
    print(f"\nDone. {len(results)} token(s) -> {out_path}")
