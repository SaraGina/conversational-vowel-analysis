"""Finds the target words in the transcripts.

Each one is also searched for under the spellings a near-miss would produce:
same consonants around the vowel, and a vowel close to the intended one. That
keeps "pole" as a possible "pool" or "pull", while leaving out "peel".

The distance between vowels is by default set to 1, but it is just adjustable in line 36.
"""
import os
import re

_CLEAN = re.compile(r"[^a-z0-9æøåäöüéèêàç']")


def clean(s):
    return _CLEAN.sub("", str(s).lower().strip())

# A- Find words 
def find_words(tokens, word_list):
    search = {clean(w) for w in word_list if clean(w)}
    if not search:
        raise ValueError("No valid search words given.")
    matches = [t for t in tokens if clean(t["word"]) in search]
    print(f"Found {len(matches)} occurrence(s) of "
          f"[{', '.join(sorted(search))}].")
    return matches


# B- Expand words 
# Vowel coordinates [height, backness]; wide diphthongs AY/AW/OY excluded.
# as english_us_arpa.dict expects
_VC = {"IY": (3, 1), "IH": (2.5, 1), "EH": (2, 1), "EY": (2, 1), "AE": (1, 1),
       "AH": (2, 2), "ER": (2, 2), "AA": (1, 3), "AO": (1.5, 3), "OW": (2, 3),
       "UH": (2.5, 3), "UW": (3, 3)}
# Distance between vowels to create new words
_THR = 1.0
_ALPHA = re.compile(r"^[A-Z]")
_DIGIT = re.compile(r"\d")


def _vowel_distance(a, b):
    (h1, b1), (h2, b2) = _VC[a], _VC[b]
    return abs(h1 - h2) + abs(b1 - b2)

# C- Default dictionary path 
# New dictionaries can be added here!
def default_dict_path(scripts_dir):

    return os.path.join(os.path.dirname(scripts_dir), "Input",
                        "english_us_arpa.dict")


def expand_words(words, dict_path):
    words = sorted({clean(w) for w in words if clean(w)})
    cand = {w: {w} for w in words}
    if not os.path.isfile(dict_path):
        print(f"WARNING: pronunciation dictionary not found ({dict_path}); "
              "neighbour expansion skipped.")
        return {w: sorted(v) for w, v in cand.items()}

    # (clean word, [phonemes stress-stripped])
    entries = []
    with open(dict_path, encoding="utf-8") as f:
        for line in f:
            tok = line.split()
            if len(tok) < 2:
                continue
            ph = [_DIGIT.sub("", p) for p in tok[1:] if _ALPHA.match(p)]
            if ph:
                entries.append((clean(tok[0]), ph))

    # frames of the target words: blanked-vowel key -> [(word, vowel)]
    frames = {}
    targets = set(words)
    for w, ph in entries:
        if w not in targets:
            continue
        for i, p in enumerate(ph):
            if p in _VC:
                key = " ".join(ph[:i] + ["_"] + ph[i + 1:])
                frames.setdefault(key, []).append((w, p))

    # scan all words; frame match + proximity-close vowel 
    for w, ph in entries:
        for i, p in enumerate(ph):
            if p not in _VC:
                continue
            key = " ".join(ph[:i] + ["_"] + ph[i + 1:])
            for tw, tv in frames.get(key, ()):
                if p == tv or _vowel_distance(p, tv) <= _THR:
                    cand[tw].add(w)
    return {w: sorted(v) for w, v in cand.items()}
