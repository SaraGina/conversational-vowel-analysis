"""Reads word timestamps from an annotation.

The pipeline's first three stages exist only to produce a list of words with
their times and their speaker. Where that list already exists, this module
reads it instead and the measurement carries on from stage 4 with the same
code, so a measurement made this way and one made from the recordings are
directly comparable.

Four shapes are read: a Praat TextGrid, a spreadsheet, a delimited text file
with a header row, and the label file Audacity writes.
"""
import csv
import io
import os

import parselmouth
from parselmouth.praat import call

# how long a word is taken to be when the annotation gives only its onset;
# the boundaries are then refined by silence detection inside that window
ONSET_ONLY_WINDOW = 0.6

_WORD = ("word", "trial_word", "intended_word", "target", "token", "label",
         "text", "orthography")
_ONSET = ("onset", "word_start", "start", "tstart", "begin", "start_time",
          "tmin", "xmin")
_OFFSET = ("offset", "word_end", "end", "tend", "stop", "end_time", "tmax",
           "xmax")
_SPEAKER = ("speaker", "participant", "talker", "tier")

SHEET = (".xlsx", ".xlsm")
DELIMITED = (".csv", ".tsv", ".txt")
TEXTGRID = (".textgrid",)
READABLE = SHEET + DELIMITED + TEXTGRID


def _key(cell):
    return str(cell or "").strip().lower().replace(" ", "_")


def _column(header, names):
    for n in names:
        if n in header:
            return header[n]
    return None


def _number(v):
    if v is None or str(v).strip() == "":
        return None
    try:
        return float(str(v).strip().replace(",", "."))
    except ValueError:
        return None


def _from_textgrid(path, want_tier=None):
    """Every labelled interval of one tier, as (word, onset, end, tier name).

    The tier is the one named in the config, or else the first interval tier
    that has any labelled interval - which, in a TextGrid this pipeline
    wrote, is the word tier.
    """
    tg = parselmouth.read(path)
    n_tiers = int(call(tg, "Get number of tiers"))
    names = []
    for t in range(1, n_tiers + 1):
        if not call(tg, "Is interval tier", t):
            continue
        name = call(tg, "Get tier name", t)
        names.append(name)
        if want_tier and _key(name) != _key(want_tier):
            continue
        found = []
        for k in range(1, int(call(tg, "Get number of intervals", t)) + 1):
            label = str(call(tg, "Get label of interval", t, k) or "").strip()
            if not label:
                continue
            found.append((label,
                          call(tg, "Get start time of interval", t, k),
                          call(tg, "Get end time of interval", t, k),
                          name))
        if found:
            return found, name
    if want_tier:
        raise RuntimeError(
            f"{os.path.basename(path)} has no interval tier called "
            f"'{want_tier}'. Its interval tiers are: {', '.join(names) or 'none'}.")
    raise RuntimeError(
        f"{os.path.basename(path)} has no labelled interval on any interval "
        "tier.")


def _from_delimited(path):
    """Rows of a .csv/.tsv/.txt, with a header row or in Audacity's shape."""
    with open(path, encoding="utf-8-sig", newline="") as f:
        text = f.read()
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel_tab if "\t" in sample else csv.excel
    table = [r for r in csv.reader(io.StringIO(text), dialect) if any(r)]
    if not table:
        return []

    # Audacity writes "start <tab> end <tab> label" with no header
    if _number(table[0][0]) is not None:
        out = []
        for r in table:
            start, end = _number(r[0]), _number(r[1]) if len(r) > 2 else None
            label = (r[2] if len(r) > 2 else r[-1]).strip() if len(r) > 1 else ""
            if start is not None and label:
                out.append((label, start, end, None))
        return out
    return _rows_from_table(table)


def _rows_from_table(table):
    """Rows of a table whose first line names its columns."""
    header = {}
    for i, cell in enumerate(table[0]):
        header.setdefault(_key(cell), i)
    i_word, i_on = _column(header, _WORD), _column(header, _ONSET)
    if i_word is None or i_on is None:
        return []
    i_off, i_spk = _column(header, _OFFSET), _column(header, _SPEAKER)
    out = []
    for raw in table[1:]:
        get = lambda i: (None if i is None or i >= len(raw) else raw[i])
        word = str(get(i_word) or "").strip()
        onset = _number(get(i_on))
        if not word or onset is None:
            continue
        spk = str(get(i_spk) or "").strip() or None
        out.append((word, onset, _number(get(i_off)), spk))
    return out


def _from_sheet(path):
    """Rows of the first sheet that names a word column and an onset column."""
    from openpyxl import load_workbook
    wb = load_workbook(path, data_only=True)
    for ws in wb.worksheets:
        table = [list(r) for r in ws.iter_rows(values_only=True)]
        rows = _rows_from_table(table) if table else []
        if rows:
            return rows
    return []


def read_annotations(path, audio_by_speaker, default_speaker, tier=None):
    """Rows ready for measurement, from whichever shape the file is in.

    A word and an onset are required; an end is used where it is there, and
    where it is not the row is given a short window from its onset and marked
    so the output says which rows were treated that way.
    """
    if not os.path.isfile(path):
        raise FileNotFoundError(f"annotation file not found: {path}")
    ext = os.path.splitext(path)[1].lower()
    name = os.path.basename(path)
    source = ext.lstrip(".")

    # a tier name is a hint about the speaker, never a claim: where it does
    # not match a label in the config it is simply not one
    tier_is_hint = ext in TEXTGRID
    if ext in TEXTGRID:
        found, tier_name = _from_textgrid(path, tier)
        source = f"TextGrid tier '{tier_name}'"
    elif ext in DELIMITED:
        found = _from_delimited(path)
    elif ext in SHEET:
        found = _from_sheet(path)
    else:
        raise RuntimeError(
            f"{name}: this is not a kind of annotation the pipeline reads. "
            f"It reads {', '.join(READABLE)}.")

    if not found:
        raise RuntimeError(
            f"{name} gave no usable rows. A sheet or delimited file needs a "
            f"column naming the word ({', '.join(_WORD[:4])}...) and one "
            f"giving its onset in seconds ({', '.join(_ONSET[:4])}...).")

    known = {str(k).strip().lower(): k for k in audio_by_speaker}
    out, unknown = [], set()
    for word, onset, end, spk in found:
        speaker = default_speaker
        if spk:
            if spk.lower() in known:
                speaker = known[spk.lower()]
            elif not tier_is_hint:
                unknown.add(spk)
                continue
        given = end is not None and end > onset
        out.append({
            "Word": word,
            "Speaker": speaker,
            "AudioFile": audio_by_speaker[speaker],
            "tStart": onset,
            "tEnd": end if given else onset + ONSET_ONLY_WINDOW,
            "Boundaries": "" if given else "FROM ONSET",
            "WordCheck": "", "EchoCheck": "", "HeardAs": "",
            "LevelDiff_dB": None,
        })

    if unknown and not out:
        raise RuntimeError(
            "the annotation names speakers this config does not know: "
            f"{', '.join(sorted(unknown))}. The labels available are "
            f"{', '.join(audio_by_speaker)}.")
    if not out:
        raise RuntimeError(f"{name} gave no usable rows.")

    print(f"Read {len(out)} annotated word(s) from {name} ({source}).")
    n_onset_only = sum(1 for r in out if r["Boundaries"])
    if n_onset_only:
        print(f"  {n_onset_only} of them gave an onset but no end; their "
              'boundaries come from silence detection and are marked '
              '"FROM ONSET".')
    if unknown:
        print(f"  rows skipped for naming an unknown speaker: "
              f"{', '.join(sorted(unknown))}.")
    return out
