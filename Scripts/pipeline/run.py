"""Runs the whole pipeline from one config file.

This is what `./run_dyad my_dyad.yaml` executes, from the Scripts folder.

Steps: 
1) transcribe both wavs if needed (faster-whisper), 
2) import the transcripts, 
3) find the target words and their phonetic neighbours, 
4) assign each one to a speaker, 
5) measure with parselmouth, 
6) write the combined Excel, and
7) optionally build the comparison against a manual annotation plus the Praat
TextGrids.
"""
import hashlib
import os
import subprocess
import sys

import yaml

from .importer import import_transcript
from .words import (clean, find_words, expand_words, default_dict_path,
                    NO_WORD_SPACING,
                    LANGUAGES)
from .annotations import read_annotations
from .speaker import assign_speaker
from .measure import run_measurement
from .analyze import annotate, load_vocab, write_excel

SCRIPTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(SCRIPTS)
INPUT = os.path.join(ROOT, "Input")
OUTPUT = os.path.join(ROOT, "Output")
AUDIO_DIRS = [INPUT]


def _find_file(name, dirs):
    if os.path.isabs(name) and os.path.isfile(name):
        return name
    for d in dirs:
        p = os.path.join(d, name)
        if os.path.isfile(p):
            return p
    raise FileNotFoundError(f"'{name}' not found in: {', '.join(dirs)}")


def _file_fingerprint(path, window=4 * 1024 * 1024):
    """Turns one file into a short code, reading only a little from its
    start, its middle and its end."""
    size = os.path.getsize(path)
    h = hashlib.blake2b(digest_size=16)
    with open(path, "rb") as fh:
        for start in (0, max(0, size // 2 - window // 2), max(0, size - window)):
            fh.seek(start)
            h.update(fh.read(window))
    return h.digest()


def _same_recording(a, b):
    """Checks whether two files hold the same audio, whatever they are named.
    """
    if os.path.realpath(a) == os.path.realpath(b):
        return True
    if os.path.getsize(a) != os.path.getsize(b):
        return False
    return _file_fingerprint(a) == _file_fingerprint(b)


def _transcript_for(audio_path, cfg_spk, language="en"):
    """Finds this speaker's transcript, creating it first if it is not there
    yet.

    The language is part of the file name, so that changing it does not reuse
    a transcript made in the other one. English keeps the older name.
    """
    if cfg_spk.get("transcript"):
        return _find_file(cfg_spk["transcript"], [INPUT])
    stem = os.path.splitext(os.path.basename(audio_path))[0]
    suffix = "_fw.json" if language == "en" else f"_fw_{language}.json"
    json_path = os.path.join(INPUT, stem + suffix)
    if not os.path.isfile(json_path):
        print(f"\nTranscribing {stem} with faster-whisper "
              "(the long step: ~10 min per 50-min recording)...", flush=True)
        # stream the transcriber's output through our own stdout so a live
        # log (e.g. the browser app) can show its progress
        proc = subprocess.Popen(
            [sys.executable, os.path.join(SCRIPTS, "transcribe_fw.py"),
             audio_path, json_path, "--language", language],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for chunk in iter(lambda: proc.stdout.read(64), ""):
            print(chunk, end="", flush=True)
        if proc.wait() != 0:
            raise RuntimeError(f"Transcription of {stem} failed.")
    return json_path


def _parse_pairs(pairs):
    """(name, [word, word], ceiling or None) for every pair in the config.

    A pair is written either as  name: [word, word]  or, when it needs its
    own formant ceiling,  name: {words: [word, word], max_formant: 4000}.
    """
    out = []
    for name, spec in pairs.items():
        if isinstance(spec, dict):
            out.append((name, [str(w) for w in spec.get("words") or []],
                        spec.get("max_formant")))
        else:
            out.append((name, [str(w) for w in spec or []], None))
    return out


def _config_problem(cfg):
    """Describes what is wrong with a config, or returns None if it is fine.

    """
    # the annotation route measures words that are already located, so one
    # recording is enough and there is nothing to compare between microphones
    needed = (("speaker_A",) if cfg.get("annotations")
              else ("speaker_A", "speaker_B"))
    for key in needed:
        block = cfg.get(key)
        if not isinstance(block, dict):
            return (f"'{key}' is missing or was not read as a set of settings. "
                    "Check that each line under it has a space after its colon.")
        if not block.get("audio"):
            return f"'{key}' has no 'audio' line naming its recording."
        if not block.get("label"):
            return f"'{key}' has no 'label' line naming its speaker."
    lang = str(cfg.get("language", "en")).lower()
    if lang not in LANGUAGES:
        return (f"'language: {lang}' is not one of the languages this copy "
                f"knows: {', '.join(sorted(LANGUAGES))}.")
    pairs = cfg.get("pairs")
    if cfg.get("annotations") and not pairs:
        return None          # the words come from the annotation instead
    if not isinstance(pairs, dict) or not pairs:
        return ("'pairs' is missing or was not read as a list of word pairs. "
                "Each line should look like  sheep_ship: [sheep, ship]  "
                "- note the space after the colon.")
    for pair_name, words, ceiling in _parse_pairs(pairs):
        if len(words) != 2:
            return (f"pair '{pair_name}' should name exactly two words, "
                    "as in  sheep_ship: [sheep, ship]")
        if ceiling is not None:
            try:
                float(ceiling)
            except (TypeError, ValueError):
                return (f"pair '{pair_name}' has a 'max_formant' that is not "
                        "a number.")
    return None


def main():
    if len(sys.argv) != 2:
        sys.exit("Usage: ./run_dyad CONFIG.yaml")
    cfg_path = sys.argv[1]
    if not os.path.isfile(cfg_path):
        cfg_path = os.path.join(SCRIPTS, sys.argv[1])
    try:
        with open(cfg_path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
    except yaml.YAMLError as exc:
        where = getattr(exc, "problem_mark", None)
        line = f" (line {where.line + 1})" if where else ""
        sys.exit(f"ERROR: {os.path.basename(cfg_path)} could not be read as a "
                 f"config file{line}. Check that every setting has a space "
                 "after its colon, and that the indentation uses spaces, not "
                 "tabs.")
    name = os.path.basename(cfg_path)
    if not isinstance(cfg, dict):
        sys.exit(f"ERROR: {name} is empty or does not contain settings. "
                 "Copy example_dyad.yaml and edit it.")
    problem = _config_problem(cfg)
    if problem:
        sys.exit(f"ERROR: {name}: {problem}")

    try:
        run_config(cfg)
    except (RuntimeError, FileNotFoundError) as exc:
        sys.exit(f"ERROR: {exc}")


def run_annotations(cfg):
    """Measures the words an annotation Excel already locates.

    Stages 1-3 exist only to produce a list of words with their times and
    their speaker. Here that list is read instead, and everything from the
    measurement on is the same code, so a result from this route and one from
    the recordings can be compared directly.

    The boundaries given are kept as they are. Each word is also measured a
    second time with the boundaries refined, under F1_refined and F2_refined,
    so the effect of where the word was cut can be seen rather than assumed.

    Gives back the path of the Excel it wrote.
    """
    A = cfg["speaker_A"]
    label_a = str(A["label"])
    audio_by_speaker = {label_a: _find_file(A["audio"], AUDIO_DIRS)}
    max_formant = {label_a: A.get("max_formant", 5500)}
    B = cfg.get("speaker_B")
    label_b = label_a
    if isinstance(B, dict) and B.get("audio") and B.get("label"):
        label_b = str(B["label"])
        audio_by_speaker[label_b] = _find_file(B["audio"], AUDIO_DIRS)
        max_formant[label_b] = B.get("max_formant", 5500)

    path = _find_file(str(cfg["annotations"]), [INPUT, OUTPUT])
    inst = read_annotations(path, audio_by_speaker, label_a)

    parsed = _parse_pairs(cfg.get("pairs") or {})
    sets = [(name, ws) for name, ws, _ in parsed]
    set_words = [{clean(w) for w in ws} for _, ws, _ in parsed]
    for r in inst:
        word = clean(r["Word"])
        for sw, (_, _, mf) in zip(set_words, parsed):
            if mf is not None and word in sw:
                r["MaxFormant"] = float(mf)
                break

    # every word here was named by hand, so none of them is a spelling the
    # search had to guess at: nothing on this route is a VARIANT
    core_all = ({clean(r["Word"]) for r in inst}
                | {w for sw in set_words for w in sw})

    results = run_measurement(inst, max_formant, refine=False,
                              also_refined=True)
    vocab = load_vocab(os.path.join(INPUT, "master_vocab.csv"))
    results = annotate(results, sets, set_words, core_all, vocab,
                       label_a, label_b,
                       segment_gap=cfg.get("segment_gap", 45),
                       blackscreen=cfg.get("blackscreen"))
    out_xlsx = os.path.join(
        OUTPUT, os.path.splitext(os.path.basename(path))[0] + "_measured.xlsx")
    write_excel(results, out_xlsx)
    return out_xlsx


def run_config(cfg):
    """Runs the whole pipeline once the settings are known.

    Both ways of starting it end up here: the ./run_dyad command, after
    reading the .yaml file, and the browser app, after reading the form.
    Either way, the processing from here on is the same.

    Gives back the path of the Excel it wrote.
    """
    # make the Output folder if it is not there yet
    os.makedirs(OUTPUT, exist_ok=True)

    # an annotation that already locates the words skips the first three
    # stages and goes straight to the measurement
    if cfg.get("annotations"):
        return run_annotations(cfg)

    A, B = cfg["speaker_A"], cfg["speaker_B"]
    audio_a = _find_file(A["audio"], AUDIO_DIRS)
    audio_b = _find_file(B["audio"], AUDIO_DIRS)
    label_a, label_b = str(A["label"]), str(B["label"])

    # The pipeline compares the two microphones against each other. It stops
    # if the user has given the same audio twice.
    if _same_recording(audio_a, audio_b):
        raise RuntimeError(
            "speaker_A and speaker_B are the same recording "
            f"({os.path.basename(audio_a)} and {os.path.basename(audio_b)} "
            "hold identical audio). The pipeline needs the two separate "
            "microphone recordings of one conversation, one per speaker.")

    # Transcription with faster-whisper, if it has not been done already
    language = str(cfg.get("language", "en")).lower()
    ts_a = _transcript_for(audio_a, A, language)
    ts_b = _transcript_for(audio_b, B, language)

    # A- import transcripts + word search 
    tokens = (import_transcript(ts_a, label_a)
              + import_transcript(ts_b, label_b))

    parsed = _parse_pairs(cfg["pairs"])
    sets = [(name, ws) for name, ws, _ in parsed]
    set_ceilings = [mf for _, _, mf in parsed]
    # the words exactly as declared: anything found outside this set was
    # reached through a neighbour spelling, and gets flagged VARIANT
    core_all = {clean(w) for _, ws in sets for w in ws}
    cand = expand_words([w for _, ws in sets for w in ws],
                        default_dict_path(SCRIPTS, language), language)
    set_words = []
    for name, ws in sets:
        expanded = set()
        for w in ws:
            expanded.update(cand.get(clean(w), [clean(w)]))
        set_words.append(expanded)
        print(f'Set "{name}": searching {", ".join(sorted(expanded))}')
    all_words = sorted(set().union(*set_words))

    # where words are not separated by spaces, a token may hold more than
    # the target word; those hits are kept and flagged PARTIAL
    matches = find_words(tokens, all_words,
                         partial=language in NO_WORD_SPACING)

    # optional analysis window: keep only tokens inside [start, end] seconds
    # (e.g. exclude pre-conversation warm-up that the annotators also exclude)
    w0 = float(cfg.get("analysis_start") or 0)
    w1 = float(cfg.get("analysis_end") or 0)
    if w0 or w1:
        hi = w1 if w1 > 0 else float("inf")
        before = len(matches)
        matches = [m for m in matches if w0 <= m["tStart"] <= hi]
        print(f"Analysis window {w0:.0f}-{'end' if hi == float('inf') else int(hi)} s: "
              f"kept {len(matches)} of {before} occurrences.")
    if not matches:
        raise RuntimeError(
            "None of the words you asked for were found in the transcripts. "
            "Check the spelling of the pairs, and the analysis window if you "
            "set one.")

    # B- speaker assignment + acoustic measurement 
    inst = assign_speaker(matches, audio_a, audio_b, label_a, label_b)
    # a pair that declared its own ceiling passes it to its own tokens
    for r in inst:
        comp = {clean(w) for w in str(r["Word"]).split("/")}
        for sw, mf in zip(set_words, set_ceilings):
            if mf is not None and comp & sw:
                r["MaxFormant"] = float(mf)
                break
    max_formant = {label_a: A.get("max_formant", 5500),
                   label_b: B.get("max_formant", 5500)}
    results = run_measurement(inst, max_formant)

    # C- annotate + write combined Excel 
    vocab = load_vocab(os.path.join(INPUT, "master_vocab.csv"))
    results = annotate(results, sets, set_words, core_all, vocab,
                       label_a, label_b,
                       segment_gap=cfg.get("segment_gap", 45),
                       blackscreen=cfg.get("blackscreen"))
    stem = os.path.splitext(os.path.basename(ts_a))[0]
    out_xlsx = os.path.join(OUTPUT, stem + "_ALL_sets_analysis.xlsx")
    write_excel(results, out_xlsx)

    # --- optional: comparison vs human annotation + TextGrids ---------------
    if cfg.get("human_excel"):
        print("\nBuilding comparison vs human annotation + TextGrids ...")
        hum = os.path.join(OUTPUT, cfg["human_excel"])
        ref = os.path.join(
            OUTPUT, os.path.splitext(cfg["human_excel"])[0] + "_REF.xlsx")
        comp = os.path.join(OUTPUT, "COMPARISON_system_vs_human.xlsx")
        # In case this run fails halfway, we delete the previous Excel file
        # first, so that an old comparison cannot be mistaken for a new one.
        if os.path.isfile(comp):
            os.remove(comp)
        py = sys.executable
        steps = [
            ("reading the human annotation Excel",
             [py, os.path.join(SCRIPTS, "extract_human_reference.py"),
              hum, os.path.join(INPUT, "master_vocab.csv"), ref]),
            ("building the colored comparison",
             [py, os.path.join(SCRIPTS, "build_comparison_excel.py"),
              out_xlsx, ref, comp]),
            ("writing the TextGrids",
             [py, os.path.join(SCRIPTS, "build_textgrids.py"),
              out_xlsx, os.path.join(OUTPUT, "TextGrids_SYSTEM")]),
        ]
        # a comparison failure DOES NOT invalidate the analysis
        for what, cmd in steps:
            res = subprocess.run(cmd, capture_output=True, text=True)
            print(res.stdout, end="")
            if res.returncode != 0:
                print("\nWARNING: the comparison could not be built "
                      f"(failed while {what}). The analysis Excel above "
                      "is still valid. Reason:")
                print((res.stderr or res.stdout).strip())
                break
        else:
            print("Done. See Output/COMPARISON_system_vs_human.xlsx "
                  "(Summary tab for the numbers).")
    else:
        print("\n(no human_excel in the config - skipping the comparison step)")
    return out_xlsx


if __name__ == "__main__":
    main()
