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
from .words import clean, find_words, expand_words, default_dict_path
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


def _transcript_for(audio_path, cfg_spk):
    """Finds this speaker's transcript, creating it first if it is not there
    yet."""
    if cfg_spk.get("transcript"):
        return _find_file(cfg_spk["transcript"], [INPUT])
    stem = os.path.splitext(os.path.basename(audio_path))[0]
    json_path = os.path.join(INPUT, stem + "_fw.json")
    if not os.path.isfile(json_path):
        print(f"\nTranscribing {stem} with faster-whisper "
              "(the long step: ~10 min per 50-min recording)...", flush=True)
        # stream the transcriber's output through our own stdout so a live
        # log (e.g. the browser app) can show its progress
        proc = subprocess.Popen(
            [sys.executable, os.path.join(SCRIPTS, "transcribe_fw.py"),
             audio_path, json_path],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for chunk in iter(lambda: proc.stdout.read(64), ""):
            print(chunk, end="", flush=True)
        if proc.wait() != 0:
            raise RuntimeError(f"Transcription of {stem} failed.")
    return json_path


def _config_problem(cfg):
    """Describes what is wrong with a config, or returns None if it is fine.

    """
    for key in ("speaker_A", "speaker_B"):
        block = cfg.get(key)
        if not isinstance(block, dict):
            return (f"'{key}' is missing or was not read as a set of settings. "
                    "Check that each line under it has a space after its colon.")
        if not block.get("audio"):
            return f"'{key}' has no 'audio' line naming its recording."
        if not block.get("label"):
            return f"'{key}' has no 'label' line naming its speaker."
    pairs = cfg.get("pairs")
    if not isinstance(pairs, dict) or not pairs:
        return ("'pairs' is missing or was not read as a list of word pairs. "
                "Each line should look like  sheep_ship: [sheep, ship]  "
                "- note the space after the colon.")
    for pair_name, words in pairs.items():
        if not isinstance(words, list) or len(words) != 2:
            return (f"pair '{pair_name}' should name exactly two words, "
                    "as in  sheep_ship: [sheep, ship]")
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


def run_config(cfg):
    """Runs the whole pipeline once the settings are known.

    Both ways of starting it end up here: the ./run_dyad command, after
    reading the .yaml file, and the browser app, after reading the form.
    Either way, the processing from here on is the same.

    Gives back the path of the Excel it wrote.
    """
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
    ts_a = _transcript_for(audio_a, A)
    ts_b = _transcript_for(audio_b, B)

    # A- import transcripts + word search 
    tokens = (import_transcript(ts_a, label_a)
              + import_transcript(ts_b, label_b))

    sets = [(name, [str(w) for w in ws]) for name, ws in cfg["pairs"].items()]
    # the words exactly as declared: anything found outside this set was
    # reached through a neighbour spelling, and gets flagged VARIANT
    core_all = {clean(w) for _, ws in sets for w in ws}
    cand = expand_words([w for _, ws in sets for w in ws],
                        default_dict_path(SCRIPTS))
    set_words = []
    for name, ws in sets:
        expanded = set()
        for w in ws:
            expanded.update(cand.get(clean(w), [clean(w)]))
        set_words.append(expanded)
        print(f'Set "{name}": searching {", ".join(sorted(expanded))}')
    all_words = sorted(set().union(*set_words))

    matches = find_words(tokens, all_words)

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
