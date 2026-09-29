#!/usr/bin/env python3
"""Generate Praat TextGrids (one per speaker) from the system's Excel output,
in the usual manual-annotation format: two IntervalTiers
'vowel' and 'word', UTF-16.

  vowel tier: interval [VowelStart, VowelEnd] labeled with the vowel symbol
  word  tier: interval [Onset, Offset]        labeled with the word

Usage: python3 build_textgrids.py ALL_sets.xlsx OUT_DIR
"""
import sys, os, wave, contextlib
import openpyxl

def _wav_duration(path):
    try:
        with contextlib.closing(wave.open(path, 'rb')) as w:
            return w.getnframes() / w.getframerate()
    except Exception:
        return None

def _build_tier(name, spans, xmax):
    """Builds one labelled layer of a TextGrid.

    Takes a list of (start, end, label) and fills the time between them with
    empty intervals, which is what Praat expects.
    """
    spans = sorted((s, e, t) for s, e, t in spans if s is not None and e is not None and e > s)
    ivs, cur = [], 0.0
    for s, e, t in spans:
        # avoid overlaps
        s = max(s, cur)
        if e <= s:
            continue
        if s > cur:
            ivs.append((cur, s, ""))
        ivs.append((s, e, t))
        cur = e
    if cur < xmax:
        ivs.append((cur, xmax, ""))
    out = [f'\t\tclass = "IntervalTier" ', f'\t\tname = "{name}" ',
           f'\t\txmin = 0 ', f'\t\txmax = {xmax} ',
           f'\t\tintervals: size = {len(ivs)} ']
    for i, (s, e, t) in enumerate(ivs, 1):
        out += [f'\t\tintervals [{i}]:', f'\t\t\txmin = {s} ',
                f'\t\t\txmax = {e} ', f'\t\t\ttext = "{t}" ']
    return out, len(ivs)

def _write_textgrid(path, xmax, vowel_spans, word_spans):
    vt, _ = _build_tier("vowel", vowel_spans, xmax)
    wt, _ = _build_tier("word",  word_spans,  xmax)
    lines = ['File type = "ooTextFile"', 'Object class = "TextGrid"', '',
             'xmin = 0 ', f'xmax = {xmax} ', 'tiers? <exists> ', 'size = 2 ',
             'item []: ', '\titem [1]:'] + vt + ['\titem [2]:'] + wt
    with open(path, 'w', encoding='utf-16') as f:
        f.write('\n'.join(lines) + '\n')

def main():
    if len(sys.argv) != 3:
        sys.exit("Usage: python3 build_textgrids.py ALL_sets.xlsx OUT_DIR")
    xlsx, outdir = sys.argv[1], sys.argv[2]
    if not os.path.isfile(xlsx):
        sys.exit(f"ERROR: '{xlsx}' not found.")
    os.makedirs(outdir, exist_ok=True)
    ws = openpyxl.load_workbook(xlsx, data_only=True).active
    hdr = [c.value for c in ws[1]]
    ix = {n: i for i, n in enumerate(hdr)}
    need = ["Speaker", "AudioFile", "Onset", "Offset", "VowelStart", "VowelEnd", "Vowel", "Word"]
    for n in need:
        if n not in ix:
            sys.exit(f"Column {n} missing in {xlsx}")

    # audiofile -> (speaker, [rows])
    by_audio = {}
    for r in range(2, ws.max_row + 1):
        row = [ws.cell(r, c + 1).value for c in range(len(hdr))]
        if row[ix["Onset"]] is None:
            continue
        af = row[ix["AudioFile"]]
        by_audio.setdefault(af, (row[ix["Speaker"]], []))[1].append(row)

    for af, (spk, rows) in by_audio.items():
        dur = _wav_duration(af) or (max(float(r[ix["Offset"]] or r[ix["Onset"]]) for r in rows) + 1)
        base = os.path.splitext(os.path.basename(af))[0]
        out = os.path.join(outdir, f"{base}_SYSTEM.TextGrid")
        vowel = [(r[ix["VowelStart"]], r[ix["VowelEnd"]], str(r[ix["Vowel"]] or "")) for r in rows]
        word  = [(r[ix["Onset"]],       r[ix["Offset"]],   str(r[ix["Word"]]  or "")) for r in rows]
        _write_textgrid(out, dur, vowel, word)
        print(f"{spk:12} {len(rows):4d} tokens -> {out}  (xmax={dur:.1f}s)")

if __name__ == "__main__":
    main()
